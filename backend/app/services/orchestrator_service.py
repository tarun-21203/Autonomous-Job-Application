from __future__ import annotations

from datetime import UTC, datetime

from backend.app.agents.writing_agent import WritingAgent
from backend.app.schemas.domain import (
    CandidateProfile,
    JobEvaluation,
    OrchestratorRunRequest,
    OrchestratorRunResponse,
    SavedSearchCreateRequest,
)
from backend.app.services.evaluation_service import EvaluationService, evaluation_service
from backend.app.services.memory_store import MemoryStore, memory_store
from backend.app.services.orchestration_store import OrchestrationStore, orchestration_store
from backend.app.services.search_service import SearchService, search_service
from backend.app.services.skill_roadmap_service import SkillRoadmapService, skill_roadmap_service
from backend.app.services.vector_memory import (
    FaissVectorMemory,
    VectorMemoryUnavailableError,
)
from backend.app.services.workflow import JobEvaluationWorkflow


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class OrchestratorService:
    def __init__(
        self,
        store: MemoryStore | None = None,
        search: SearchService | None = None,
        run_store: OrchestrationStore | None = None,
        evaluator: EvaluationService | None = None,
        roadmap: SkillRoadmapService | None = None,
    ) -> None:
        self.store = store or memory_store
        self.search_service = search or search_service
        self.run_store = run_store or orchestration_store
        self.workflow = JobEvaluationWorkflow(store=self.store)
        self.writing_agent = WritingAgent()
        self.evaluator = evaluator or evaluation_service
        self.roadmap_service = roadmap or skill_roadmap_service

    def run(self, request: OrchestratorRunRequest) -> OrchestratorRunResponse:
        profile = self.store.get_profile(request.profile_id)
        if profile is None:
            raise ValueError(f"Unknown profile_id: {request.profile_id}")

        plan = [
            "plan_goal",
            "search_jobs",
            "semantic_rank_jobs",
            "build_skill_roadmap",
            "tailor_resume",
            "evaluate_outputs",
            "reflect_and_finish",
        ]
        run = self.run_store.create_run(request.profile_id, request.goal, plan)
        self.run_store.update_run(run.run_id, status="running", observations=["Run initialized."])

        observations = ["Run initialized."]
        try:
            search_id = self._resolve_search_id(request, profile)
            self._run_step(run.run_id, "plan_goal", {"goal": request.goal}, {"plan": plan}, "Created a lean multi-agent plan.")

            search_result = self._run_search_step(run.run_id, search_id, request.limit, observations)
            job_fit_scores = {
                evaluation.job.job_id: evaluation.fit_score for evaluation in search_result.evaluations
            }
            ranked_jobs = self._rank_jobs_step(
                run.run_id,
                profile.profile_id,
                request.goal,
                search_result.jobs,
                job_fit_scores,
                observations,
            )
            selected_job = ranked_jobs[0].job if ranked_jobs else (search_result.jobs[0] if search_result.jobs else None)

            roadmap = self._roadmap_step(run.run_id, profile, [item.job for item in ranked_jobs] or search_result.jobs, observations)
            resume_recommendation = self._tailor_resume_step(
                run.run_id,
                profile,
                selected_job,
                observations,
            )
            evaluation_bundle = self._evaluate_step(
                run.run_id,
                search_result.evaluations,
                resume_recommendation,
                roadmap,
                observations,
            )

            final_status = "needs_review" if evaluation_bundle.needs_human_review else "completed"
            reflection = self._reflect_step(
                run.run_id,
                evaluation_bundle,
                selected_job,
                observations,
            )

            run = self.run_store.update_run(
                run.run_id,
                status=final_status,
                observations=observations,
                selected_job=selected_job,
                ranked_jobs=ranked_jobs,
                evaluations=search_result.evaluations,
                skill_roadmap=roadmap,
                resume_recommendation=resume_recommendation,
                evaluation_bundle=evaluation_bundle,
                needs_human_review=evaluation_bundle.needs_human_review,
            )
        except Exception as error:
            run = self.run_store.update_run(
                run.run_id,
                status="failed",
                observations=observations + [f"Run failed: {error}"],
                needs_human_review=True,
            )
            raise

        steps = self.run_store.list_steps(run.run_id)
        return OrchestratorRunResponse(run=run, steps=steps)

    def get_run(self, run_id: str) -> OrchestratorRunResponse:
        run = self.run_store.get_run(run_id)
        if run is None:
            raise ValueError(f"Unknown run_id: {run_id}")
        steps = self.run_store.list_steps(run_id)
        return OrchestratorRunResponse(run=run, steps=steps)

    def list_runs(self, profile_id: str) -> list:
        if self.store.get_profile(profile_id) is None:
            raise ValueError(f"Unknown profile_id: {profile_id}")
        return self.run_store.list_runs(profile_id)

    def _resolve_search_id(self, request: OrchestratorRunRequest, profile: CandidateProfile) -> str:
        if request.search_id:
            return request.search_id
        if request.search_override:
            created = self.search_service.create_search(
                SavedSearchCreateRequest(
                    profile_id=profile.profile_id,
                    name=request.search_override.name,
                    keywords=request.search_override.keywords,
                    target_roles=request.search_override.target_roles,
                    locations=request.search_override.locations,
                    remote_only=request.search_override.remote_only,
                    salary_min=request.search_override.salary_min,
                    companies_include=request.search_override.companies_include,
                    companies_exclude=request.search_override.companies_exclude,
                    required_skills=request.search_override.required_skills,
                    preferred_skills=request.search_override.preferred_skills,
                    sources=request.search_override.sources,
                )
            )
            return created.search_id

        searches = self.search_service.list_searches(profile.profile_id)
        if not searches:
            raise ValueError("No saved search available. Provide search_id or search_override in the orchestrator request.")
        return searches[0].search_id

    def _run_step(
        self,
        run_id: str,
        name: str,
        input_payload: dict[str, object],
        output_payload: dict[str, object],
        reflection: str,
    ) -> None:
        step = self.run_store.create_step(run_id, name, input_payload)
        self.run_store.update_step(step.step_id, status="running", started_at=_utc_now())
        self.run_store.update_step(
            step.step_id,
            status="completed",
            output_payload=output_payload,
            reflection=reflection,
            completed_at=_utc_now(),
        )

    def _run_search_step(self, run_id: str, search_id: str, limit: int, observations: list[str]):
        step = self.run_store.create_step(run_id, "search_jobs", {"search_id": search_id, "limit": limit})
        self.run_store.update_step(step.step_id, status="running", started_at=_utc_now())

        try:
            result = self.search_service.run_search(search_id, evaluate_jobs=True, limit=limit)
            reflection = f"Fetched {len(result.jobs)} jobs and evaluated {len(result.evaluations)} of them."
            self.run_store.update_step(
                step.step_id,
                status="completed",
                output_payload={
                    "jobs_count": len(result.jobs),
                    "evaluations_count": len(result.evaluations),
                    "warnings": result.run.warnings,
                },
                reflection=reflection,
                completed_at=_utc_now(),
            )
            observations.append(reflection)
            return result
        except Exception as error:
            self.run_store.update_step(
                step.step_id,
                status="failed",
                output_payload={"error": str(error)},
                reflection="Search step failed and needs human inspection.",
                completed_at=_utc_now(),
            )
            raise

    def _rank_jobs_step(
        self,
        run_id: str,
        profile_id: str,
        goal: str,
        jobs: list,
        job_fit_scores: dict[str, float],
        observations: list[str],
    ) -> list:
        step = self.run_store.create_step(run_id, "semantic_rank_jobs", {"job_count": len(jobs), "goal": goal})
        self.run_store.update_step(step.step_id, status="running", started_at=_utc_now())

        ranked_jobs = []
        ranking_reflection = ""
        try:
            vector_memory = FaissVectorMemory()
            vector_memory.index_jobs(profile_id, jobs)
            ranked_jobs = vector_memory.rank_jobs(
                profile_id,
                goal,
                job_fit_scores=job_fit_scores,
                limit=len(jobs),
            )
            ranking_reflection = (
                f"Ranked {len(ranked_jobs)} jobs with FAISS semantic memory and fit-score blending."
            )
        except VectorMemoryUnavailableError:
            ranking_reflection = "FAISS unavailable, so ranking fell back to fit scores only."
            ranked_jobs = []
        except Exception as error:
            ranking_reflection = f"Semantic ranking failed with {error}; fell back to fit-score ordering."
            ranked_jobs = []

        if not ranked_jobs:
            sorted_jobs = sorted(jobs, key=lambda item: job_fit_scores.get(item.job_id, 0.0), reverse=True)
            ranked_jobs = [
                {
                    "job": job,
                    "semantic_score": float(job_fit_scores.get(job.job_id, 0.0)),
                    "fit_score": job_fit_scores.get(job.job_id),
                    "combined_score": float(job_fit_scores.get(job.job_id, 0.0)),
                    "reason": "Fallback ranking used current fit scores because semantic memory was unavailable.",
                }
                for job in sorted_jobs
            ]
            from backend.app.schemas.domain import RankedJobInsight

            ranked_jobs = [RankedJobInsight.model_validate(item) for item in ranked_jobs]

        self.run_store.update_step(
            step.step_id,
            status="completed",
            output_payload={"top_jobs": [item.job.job_id for item in ranked_jobs]},
            reflection=ranking_reflection,
            completed_at=_utc_now(),
        )
        observations.append(ranking_reflection)
        return ranked_jobs

    def _roadmap_step(self, run_id: str, profile: CandidateProfile, jobs: list, observations: list[str]):
        step = self.run_store.create_step(run_id, "build_skill_roadmap", {"job_count": len(jobs)})
        self.run_store.update_step(step.step_id, status="running", started_at=_utc_now())
        roadmap = self.roadmap_service.build(profile, jobs)
        reflection = (
            f"Roadmap generated with {len(roadmap.steps)} prioritized learning steps."
        )
        self.run_store.update_step(
            step.step_id,
            status="completed",
            output_payload={"steps": len(roadmap.steps)},
            reflection=reflection,
            completed_at=_utc_now(),
        )
        observations.append(reflection)
        return roadmap

    def _tailor_resume_step(
        self,
        run_id: str,
        profile: CandidateProfile,
        selected_job,
        observations: list[str],
    ):
        step = self.run_store.create_step(
            run_id,
            "tailor_resume",
            {"selected_job_id": selected_job.job_id if selected_job else None},
        )
        self.run_store.update_step(step.step_id, status="running", started_at=_utc_now())

        if selected_job is None:
            reflection = "No job was selected, so resume tailoring could not proceed."
            self.run_store.update_step(
                step.step_id,
                status="skipped",
                output_payload={},
                reflection=reflection,
                completed_at=_utc_now(),
            )
            observations.append(reflection)
            return None

        recommendation = self.writing_agent.recommend(profile, selected_job)
        reflection = "Resume recommendation was tailored against the strongest-ranked job."
        self.run_store.update_step(
            step.step_id,
            status="completed",
            output_payload={"missing_keywords": recommendation.missing_keywords},
            reflection=reflection,
            completed_at=_utc_now(),
        )
        observations.append(reflection)
        return recommendation

    def _evaluate_step(
        self,
        run_id: str,
        evaluations: list[JobEvaluation],
        resume_recommendation,
        roadmap,
        observations: list[str],
    ):
        step = self.run_store.create_step(run_id, "evaluate_outputs", {"evaluations_count": len(evaluations)})
        self.run_store.update_step(step.step_id, status="running", started_at=_utc_now())
        bundle = self.evaluator.evaluate(evaluations, resume_recommendation, roadmap)
        reflection = f"Evaluation confidence is {bundle.overall_confidence}."
        self.run_store.update_step(
            step.step_id,
            status="completed",
            output_payload={"overall_confidence": bundle.overall_confidence},
            reflection=reflection,
            completed_at=_utc_now(),
        )
        observations.append(reflection)
        return bundle

    def _reflect_step(self, run_id: str, bundle, selected_job, observations: list[str]) -> str:
        step = self.run_store.create_step(
            run_id,
            "reflect_and_finish",
            {"selected_job_id": selected_job.job_id if selected_job else None},
        )
        self.run_store.update_step(step.step_id, status="running", started_at=_utc_now())
        reflection = (
            bundle.reflection
            if selected_job is not None
            else "No candidate job survived the loop strongly enough, so the run should be reviewed and re-planned."
        )
        self.run_store.update_step(
            step.step_id,
            status="completed",
            output_payload={"needs_human_review": bundle.needs_human_review},
            reflection=reflection,
            completed_at=_utc_now(),
        )
        observations.append(reflection)
        return reflection


orchestrator_service = OrchestratorService()
