from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from backend.app.core.config import _load_env_file
from backend.app.schemas.domain import (
    ExecutionTaskRequest,
    JobPosting,
    OrchestratorRunRequest,
    SavedSearch,
    SavedSearchCreateRequest,
    SearchOverride,
)
from backend.app.services.execution_service import ExecutionService
from backend.app.services.job_sources import _rank_jobs_for_search, _search_matches_job
from backend.app.services.memory_store import MemoryStore
from backend.app.services.orchestration_store import OrchestrationStore
from backend.app.services.orchestrator_service import OrchestratorService
from backend.app.services.resume_parser import build_profile, extract_resume_text
from backend.app.services.search_service import SearchService
from backend.app.services.workflow import JobEvaluationWorkflow


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "agent.db"
        self.store = MemoryStore(self.database_path)
        self.workflow = JobEvaluationWorkflow(store=self.store)
        self.search_service = SearchService(store=self.store)
        self.execution_service = ExecutionService(store=self.store)
        self.run_store = OrchestrationStore(self.database_path)
        self.orchestrator_service = OrchestratorService(
            store=self.store,
            search=self.search_service,
            run_store=self.run_store,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_evaluation_is_persisted_and_duplicate_detection_kicks_in(self) -> None:
        profile = build_profile(
            resume_text="Python FastAPI SQL Docker improved API latency by 32 percent.",
            target_roles=["Backend Engineer"],
            preferred_locations=["Remote"],
            name="Test Candidate",
        )
        self.store.save_profile(profile)

        job = JobPosting(
            job_id="job-1",
            title="Backend Engineer",
            company="Acme",
            description="Build APIs",
            location="Remote",
            required_skills=["Python", "FastAPI", "SQL"],
            preferred_skills=["Docker"],
        )

        first_result = self.workflow.run(profile.profile_id, [job])
        second_result = self.workflow.run(profile.profile_id, [job])

        self.assertEqual(len(first_result.evaluations), 1)
        self.assertFalse(first_result.evaluations[0].duplicate)
        self.assertIsNotNone(first_result.evaluations[0].application_id)

        self.assertEqual(len(second_result.evaluations), 1)
        self.assertTrue(second_result.evaluations[0].duplicate)

        applications = self.store.list_applications(profile.profile_id)
        self.assertEqual(len(applications), 1)
        self.assertEqual(applications[0].status, "evaluated")

    def test_application_status_transition_is_saved(self) -> None:
        profile = build_profile(
            resume_text="Python SQL built data services with 25 percent cost savings.",
            target_roles=["Backend Engineer"],
            preferred_locations=[],
        )
        self.store.save_profile(profile)
        job = JobPosting(
            job_id="job-2",
            title="Backend Engineer",
            company="Beta",
            description="Own services",
            required_skills=["Python", "SQL"],
            preferred_skills=[],
        )

        result = self.workflow.run(profile.profile_id, [job])
        application_id = result.evaluations[0].application_id
        updated = self.store.update_application_status(application_id, "approved", "Human approved shortlist.")

        self.assertEqual(updated.status, "approved")

    def test_docx_resume_text_can_be_extracted(self) -> None:
        docx_bytes = self._make_docx("Python engineer\nBuilt APIs")
        extracted = extract_resume_text("resume.docx", docx_bytes)
        self.assertIn("Python engineer", extracted)
        self.assertIn("Built APIs", extracted)

    def test_env_file_loader_sets_missing_values_without_overriding_environment(self) -> None:
        env_file = Path(self.temp_dir.name) / ".env"
        env_file.write_text(
            "\n".join(
                [
                    "APP_NAME='Loaded App'",
                    "SERPAPI_API_KEY=from-file # local development key",
                    "EXISTING_VALUE=from-file",
                ]
            ),
            encoding="utf-8",
        )

        with patch.dict(os.environ, {"EXISTING_VALUE": "from-environment"}, clear=True):
            _load_env_file(env_file)

            self.assertEqual(os.environ["APP_NAME"], "Loaded App")
            self.assertEqual(os.environ["SERPAPI_API_KEY"], "from-file")
            self.assertEqual(os.environ["EXISTING_VALUE"], "from-environment")

    def test_saved_search_can_fetch_and_evaluate_jobs(self) -> None:
        profile = build_profile(
            resume_text="Python FastAPI SQL Docker built APIs with 40 percent lower latency.",
            target_roles=["Backend Engineer"],
            preferred_locations=["Remote"],
        )
        self.store.save_profile(profile)

        search = self.search_service.create_search(
            SavedSearchCreateRequest(
                profile_id=profile.profile_id,
                name="Backend remote roles",
                target_roles=["Backend Engineer"],
                locations=["Remote"],
                required_skills=["Python", "FastAPI", "SQL"],
                preferred_skills=["Docker"],
                sources=["mock"],
            )
        )

        result = self.search_service.run_search(search.search_id, evaluate_jobs=True, limit=5)

        self.assertEqual(result.search.search_id, search.search_id)
        self.assertGreaterEqual(len(result.jobs), 1)
        self.assertEqual(len(result.jobs), len(result.evaluations))
        self.assertEqual(result.run.fetched_count, len(result.jobs))
        self.assertEqual(result.run.sources, ["mock"])

        applications = self.store.list_applications(profile.profile_id)
        self.assertGreaterEqual(len(applications), 1)

    def test_job_search_tolerates_misspelled_role_and_location(self) -> None:
        search = SavedSearch(
            search_id="search-typo",
            profile_id="profile-1",
            name="Typo search",
            target_roles=["sofware enginer"],
            locations=["toranto"],
            keywords=["python"],
            created_at="now",
            updated_at="now",
        )
        job = JobPosting(
            job_id="job-typo-match",
            title="Software Engineer",
            company="Northstar",
            description="Build Python APIs for customer products.",
            location="Toronto, ON",
            required_skills=["Python"],
        )

        self.assertTrue(_search_matches_job(job, search))

    def test_job_search_returns_nearest_related_jobs_when_exact_role_is_missing(self) -> None:
        search = SavedSearch(
            search_id="search-related",
            profile_id="profile-1",
            name="Related search",
            target_roles=["Data Scientist"],
            locations=["Toronto"],
            keywords=["python"],
            created_at="now",
            updated_at="now",
        )
        related_job = JobPosting(
            job_id="job-related",
            title="Machine Learning Engineer",
            company="SignalWorks",
            description="Use Python to build ML models and data products.",
            location="Canada",
            required_skills=["Python", "Machine Learning"],
        )
        unrelated_job = JobPosting(
            job_id="job-unrelated",
            title="Retail Store Manager",
            company="ShopsCo",
            description="Manage store operations and scheduling.",
            location="Toronto, ON",
            required_skills=[],
        )

        jobs, warnings = _rank_jobs_for_search([unrelated_job, related_job], search, limit=2)

        self.assertEqual(jobs[0].job_id, "job-related")
        self.assertTrue(any("nearest related" in warning for warning in warnings))

    def test_feedback_summary_influences_future_scoring_and_skill_recommendations(self) -> None:
        profile = build_profile(
            resume_text="Python SQL FastAPI built backend services with 30 percent lower latency.",
            target_roles=["Backend Engineer"],
            preferred_locations=["Remote"],
        )
        self.store.save_profile(profile)

        successful_job = JobPosting(
            job_id="job-success",
            title="Backend Engineer",
            company="SuccessCo",
            description="Build backend APIs",
            location="Remote",
            required_skills=["Python", "SQL", "FastAPI"],
            preferred_skills=["Docker"],
        )
        success_result = self.workflow.run(profile.profile_id, [successful_job])
        self.store.update_application_status(
            success_result.evaluations[0].application_id,
            "approved",
            "Human approved the application.",
        )
        self.store.update_application_status(
            success_result.evaluations[0].application_id,
            "applied",
            "Application submitted.",
        )
        self.store.update_application_status(
            success_result.evaluations[0].application_id,
            "interviewing",
            "Recruiter moved the candidate forward.",
        )

        gap_job = JobPosting(
            job_id="job-gap",
            title="Platform Engineer",
            company="GapCo",
            description="Own platform systems",
            location="Remote",
            required_skills=["Python", "Kubernetes"],
            preferred_skills=["Terraform"],
        )
        gap_result = self.workflow.run(profile.profile_id, [gap_job])
        self.store.update_application_status(
            gap_result.evaluations[0].application_id,
            "skipped",
            "Skipped because Kubernetes experience is missing.",
        )

        follow_up_job = JobPosting(
            job_id="job-followup",
            title="Backend Engineer",
            company="FutureCo",
            description="Backend APIs and services",
            location="Remote",
            required_skills=["Python", "SQL", "Kubernetes"],
            preferred_skills=["Docker"],
        )
        follow_up_result = self.workflow.run(profile.profile_id, [follow_up_job])
        evaluation = follow_up_result.evaluations[0]

        summary = self.store.get_feedback_summary(profile.profile_id)
        self.assertGreaterEqual(summary.total_applications, 2)
        self.assertEqual(summary.successful_roles[0].role, "Backend Engineer")
        self.assertTrue(any(skill.skill == "Kubernetes" for skill in summary.recurring_missing_skills))
        self.assertTrue(
            any("Past positive outcomes suggest this role family performs well" in reason for reason in evaluation.rationale)
        )
        self.assertTrue(
            any("repeated gap" in recommendation.reason.lower() for recommendation in evaluation.skill_recommendations)
        )

    def test_execution_queue_requires_human_approval_and_submission_confirmation(self) -> None:
        profile = build_profile(
            resume_text="Python FastAPI SQL built internal tools that saved 20 hours per week.",
            target_roles=["Backend Engineer"],
            preferred_locations=["Remote"],
            name="Queue Tester",
        )
        self.store.save_profile(profile)

        job = JobPosting(
            job_id="job-exec",
            title="Backend Engineer",
            company="QueueCo",
            description="Build internal tooling",
            location="Remote",
            required_skills=["Python", "FastAPI", "SQL"],
            preferred_skills=["Docker"],
        )

        evaluation = self.workflow.run(profile.profile_id, [job]).evaluations[0]
        self.store.update_application_status(
            evaluation.application_id,
            "approved",
            "Human approved this application for execution.",
        )

        task = self.execution_service.create_task(
            evaluation.application_id,
            ExecutionTaskRequest(
                execution_type="manual_browser",
                dry_run=True,
                channel_target="https://example.com/apply",
                note="Prepare the manual browser flow.",
            ),
        )
        self.assertEqual(task.status, "approval_required")

        approved_task = self.execution_service.approve_task(task.task_id, note="Looks good to queue.")
        self.assertEqual(approved_task.status, "queued")
        self.assertTrue(approved_task.human_approved)

        processed_tasks = self.execution_service.process_queue(limit=5)
        self.assertEqual(len(processed_tasks), 1)
        self.assertEqual(processed_tasks[0].status, "completed")
        application_before_confirmation = self.store.get_application(evaluation.application_id)
        self.assertEqual(application_before_confirmation.status, "approved")

        confirmed_task = self.execution_service.confirm_submission(
            task.task_id,
            note="Human confirmed the final submission happened.",
        )
        self.assertEqual(confirmed_task.status, "completed")
        application_after_confirmation = self.store.get_application(evaluation.application_id)
        self.assertEqual(application_after_confirmation.status, "applied")

        events = self.store.list_execution_events(task.task_id)
        event_types = [event.event_type for event in events]
        self.assertIn("created", event_types)
        self.assertIn("approved", event_types)
        self.assertIn("started", event_types)
        self.assertIn("completed", event_types)
        self.assertIn("submission_confirmed", event_types)

    def test_orchestrator_run_persists_plan_steps_and_outputs(self) -> None:
        profile = build_profile(
            resume_text="Python FastAPI SQL Docker AWS built backend systems with 99.9 uptime.",
            target_roles=["Backend Engineer"],
            preferred_locations=["Remote"],
            name="Agent Core Tester",
        )
        self.store.save_profile(profile)

        response = self.orchestrator_service.run(
            OrchestratorRunRequest(
                profile_id=profile.profile_id,
                goal="I want a backend job in Canada with strong Python API work.",
                limit=5,
                search_override=SearchOverride(
                    name="Canada backend roles",
                    target_roles=["Backend Engineer"],
                    locations=["Remote", "Canada"],
                    required_skills=["Python", "FastAPI", "SQL"],
                    preferred_skills=["Docker", "AWS"],
                    sources=["mock"],
                ),
            )
        )

        self.assertIn(response.run.status, {"completed", "needs_review"})
        self.assertEqual(response.run.profile_id, profile.profile_id)
        self.assertGreaterEqual(len(response.run.plan), 1)
        self.assertGreaterEqual(len(response.steps), 1)
        self.assertGreaterEqual(len(response.run.evaluations), 1)
        self.assertIsNotNone(response.run.skill_roadmap)
        self.assertIsNotNone(response.run.evaluation_bundle)
        self.assertGreaterEqual(response.run.evaluation_bundle.overall_confidence, 0.0)

        persisted = self.run_store.get_run(response.run.run_id)
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.goal, response.run.goal)
        self.assertEqual(len(self.run_store.list_steps(response.run.run_id)), len(response.steps))

    def _make_docx(self, body_text: str) -> bytes:
        document = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>"
        )
        for line in body_text.splitlines():
            document += f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>"
        document += "</w:body></w:document>"

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("word/document.xml", document)
        return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
