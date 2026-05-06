from __future__ import annotations

from datetime import datetime, UTC
import json
from pathlib import Path
import uuid

from backend.app.core.config import settings
from backend.app.db.database import get_connection, initialize_database
from backend.app.schemas.domain import (
    ApplicationRecord,
    ApplicationStatus,
    CandidateProfile,
    ExecutionEventRecord,
    ExecutionTaskRecord,
    ExecutionType,
    ExecutionStatus,
    FeedbackRoleInsight,
    FeedbackSkillInsight,
    FeedbackSummary,
    JobEvaluation,
    JobPosting,
    ResumeRecommendation,
    SavedSearch,
    SearchRunRecord,
    SkillRecommendation,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _fingerprint(job: JobPosting) -> str:
    parts = [
        job.company.strip().lower(),
        job.title.strip().lower(),
        (job.location or "").strip().lower(),
    ]
    return "|".join(parts)


class InvalidStatusTransitionError(ValueError):
    pass


class MemoryStore:
    allowed_transitions: dict[ApplicationStatus, set[ApplicationStatus]] = {
        "evaluated": {"approved", "skipped", "archived"},
        "approved": {"tailored", "applied", "skipped", "archived"},
        "tailored": {"approved", "applied", "archived"},
        "applied": {"interviewing", "rejected", "offer", "archived"},
        "interviewing": {"offer", "rejected", "archived"},
        "offer": {"archived"},
        "rejected": {"archived"},
        "skipped": {"evaluated", "archived"},
        "archived": set(),
    }

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path or settings.database_path)
        initialize_database(self.database_path)

    def save_profile(self, profile: CandidateProfile) -> CandidateProfile:
        created_at = _utc_now()
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO profiles (
                    profile_id, name, resume_text, target_roles_json, preferred_locations_json,
                    skills_json, achievements_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.profile_id,
                    profile.name,
                    profile.resume_text,
                    self._dump(profile.target_roles),
                    self._dump(profile.preferred_locations),
                    self._dump(profile.skills),
                    self._dump(profile.achievements),
                    created_at,
                ),
            )
        return profile

    def get_profile(self, profile_id: str) -> CandidateProfile | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM profiles WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()

        if row is None:
            return None
        return CandidateProfile(
            profile_id=row["profile_id"],
            name=row["name"],
            resume_text=row["resume_text"],
            target_roles=self._load(row["target_roles_json"]),
            preferred_locations=self._load(row["preferred_locations_json"]),
            skills=self._load(row["skills_json"]),
            achievements=self._load(row["achievements_json"]),
        )

    def save_search(self, search: SavedSearch) -> SavedSearch:
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO saved_searches (
                    search_id, profile_id, name, keywords_json, target_roles_json, locations_json,
                    remote_only, salary_min, companies_include_json, companies_exclude_json,
                    required_skills_json, preferred_skills_json, sources_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(search_id) DO UPDATE SET
                    name=excluded.name,
                    keywords_json=excluded.keywords_json,
                    target_roles_json=excluded.target_roles_json,
                    locations_json=excluded.locations_json,
                    remote_only=excluded.remote_only,
                    salary_min=excluded.salary_min,
                    companies_include_json=excluded.companies_include_json,
                    companies_exclude_json=excluded.companies_exclude_json,
                    required_skills_json=excluded.required_skills_json,
                    preferred_skills_json=excluded.preferred_skills_json,
                    sources_json=excluded.sources_json,
                    updated_at=excluded.updated_at
                """,
                (
                    search.search_id,
                    search.profile_id,
                    search.name,
                    self._dump(search.keywords),
                    self._dump(search.target_roles),
                    self._dump(search.locations),
                    int(search.remote_only),
                    search.salary_min,
                    self._dump(search.companies_include),
                    self._dump(search.companies_exclude),
                    self._dump(search.required_skills),
                    self._dump(search.preferred_skills),
                    self._dump(search.sources),
                    search.created_at,
                    search.updated_at,
                ),
            )
        return search

    def get_search(self, search_id: str) -> SavedSearch | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM saved_searches WHERE search_id = ?",
                (search_id,),
            ).fetchone()

        if row is None:
            return None
        return self._search_from_row(row)

    def list_searches(self, profile_id: str) -> list[SavedSearch]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM saved_searches
                WHERE profile_id = ?
                ORDER BY updated_at DESC
                """,
                (profile_id,),
            ).fetchall()

        return [self._search_from_row(row) for row in rows]

    def save_search_run(
        self,
        search_id: str,
        sources: list[str],
        fetched_count: int,
        warnings: list[str],
    ) -> SearchRunRecord:
        run_id = str(uuid.uuid4())
        created_at = _utc_now()
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO search_runs (
                    run_id, search_id, sources_json, fetched_count, warnings_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    search_id,
                    self._dump(sources),
                    fetched_count,
                    self._dump(warnings),
                    created_at,
                ),
            )

        return SearchRunRecord(
            run_id=run_id,
            search_id=search_id,
            sources=sources,
            fetched_count=fetched_count,
            warnings=warnings,
            created_at=created_at,
        )

    def list_applications(self, profile_id: str) -> list[ApplicationRecord]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT applications.*, jobs.*
                FROM applications
                JOIN jobs ON jobs.fingerprint = applications.job_fingerprint
                WHERE applications.profile_id = ?
                ORDER BY applications.updated_at DESC
                """,
                (profile_id,),
            ).fetchall()

        return [self._application_from_row(row) for row in rows]

    def get_application(self, application_id: str) -> ApplicationRecord | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT applications.*, jobs.*
                FROM applications
                JOIN jobs ON jobs.fingerprint = applications.job_fingerprint
                WHERE applications.application_id = ?
                """,
                (application_id,),
            ).fetchone()

        if row is None:
            return None
        return self._application_from_row(row)

    def get_feedback_summary(self, profile_id: str) -> FeedbackSummary:
        applications = self.list_applications(profile_id)
        status_counts: dict[str, int] = {}
        successful_role_counts: dict[str, int] = {}
        rejected_role_counts: dict[str, int] = {}
        successful_skill_counts: dict[str, int] = {}
        missing_skill_counts: dict[str, int] = {}

        positive_statuses = {"approved", "tailored", "applied", "interviewing", "offer"}
        negative_statuses = {"skipped", "rejected"}

        for application in applications:
            status_counts[application.status] = status_counts.get(application.status, 0) + 1

            normalized_role = application.job.title.strip()
            if application.status in positive_statuses:
                successful_role_counts[normalized_role] = successful_role_counts.get(normalized_role, 0) + 1
                for skill in application.job.required_skills + application.job.preferred_skills:
                    normalized_skill = skill.strip()
                    if normalized_skill:
                        successful_skill_counts[normalized_skill] = successful_skill_counts.get(normalized_skill, 0) + 1

            if application.status in negative_statuses or application.recommendation == "skip":
                rejected_role_counts[normalized_role] = rejected_role_counts.get(normalized_role, 0) + 1
                for skill in application.skill_recommendations:
                    normalized_skill = skill.skill.strip()
                    if normalized_skill:
                        missing_skill_counts[normalized_skill] = missing_skill_counts.get(normalized_skill, 0) + 1

        successful_roles = [
            FeedbackRoleInsight(role=role, count=count)
            for role, count in self._top_counts(successful_role_counts)
        ]
        recurring_rejected_roles = [
            FeedbackRoleInsight(role=role, count=count)
            for role, count in self._top_counts(rejected_role_counts)
        ]
        successful_skills = [
            FeedbackSkillInsight(
                skill=skill,
                count=count,
                reason="This skill shows up repeatedly in applications that progressed well.",
            )
            for skill, count in self._top_counts(successful_skill_counts)
        ]
        recurring_missing_skills = [
            FeedbackSkillInsight(
                skill=skill,
                count=count,
                reason="This skill keeps appearing as a gap in skipped or rejected opportunities.",
            )
            for skill, count in self._top_counts(missing_skill_counts)
        ]

        notes: list[str] = []
        if successful_roles:
            notes.append(f"Best-performing role family so far: {successful_roles[0].role}.")
        if recurring_missing_skills:
            notes.append(
                f"Most common improvement gap so far: {recurring_missing_skills[0].skill}."
            )

        return FeedbackSummary(
            profile_id=profile_id,
            total_applications=len(applications),
            status_counts=status_counts,
            successful_roles=successful_roles,
            recurring_rejected_roles=recurring_rejected_roles,
            successful_skills=successful_skills,
            recurring_missing_skills=recurring_missing_skills,
            notes=notes,
        )

    def find_application(self, profile_id: str, job: JobPosting) -> ApplicationRecord | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT applications.*, jobs.*
                FROM applications
                JOIN jobs ON jobs.fingerprint = applications.job_fingerprint
                WHERE applications.profile_id = ? AND applications.job_fingerprint = ?
                """,
                (profile_id, _fingerprint(job)),
            ).fetchone()

        if row is None:
            return None
        return self._application_from_row(row)

    def save_job(self, job: JobPosting) -> str:
        fingerprint = _fingerprint(job)
        timestamp = _utc_now()
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    fingerprint, job_id, title, company, description, location, source, url,
                    required_skills_json, preferred_skills_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    job_id=excluded.job_id,
                    title=excluded.title,
                    company=excluded.company,
                    description=excluded.description,
                    location=excluded.location,
                    source=excluded.source,
                    url=excluded.url,
                    required_skills_json=excluded.required_skills_json,
                    preferred_skills_json=excluded.preferred_skills_json,
                    updated_at=excluded.updated_at
                """,
                (
                    fingerprint,
                    job.job_id,
                    job.title,
                    job.company,
                    job.description,
                    job.location,
                    job.source,
                    job.url,
                    self._dump(job.required_skills),
                    self._dump(job.preferred_skills),
                    timestamp,
                    timestamp,
                ),
            )
        return fingerprint

    def save_evaluation(
        self,
        profile_id: str,
        evaluation: JobEvaluation,
        current_status: ApplicationStatus | None = None,
    ) -> ApplicationRecord:
        application_id = evaluation.application_id or str(uuid.uuid4())
        fingerprint = self.save_job(evaluation.job)
        created_at = _utc_now()
        status = current_status or "evaluated"

        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO applications (
                    application_id, profile_id, job_fingerprint, recommendation, status, fit_score,
                    rationale_json, resume_recommendation_json, skill_recommendations_json,
                    duplicate, requires_human_review, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_id, job_fingerprint) DO UPDATE SET
                    recommendation=excluded.recommendation,
                    fit_score=excluded.fit_score,
                    rationale_json=excluded.rationale_json,
                    resume_recommendation_json=excluded.resume_recommendation_json,
                    skill_recommendations_json=excluded.skill_recommendations_json,
                    duplicate=excluded.duplicate,
                    requires_human_review=excluded.requires_human_review,
                    updated_at=excluded.updated_at
                """,
                (
                    application_id,
                    profile_id,
                    fingerprint,
                    evaluation.recommendation,
                    status,
                    evaluation.fit_score,
                    self._dump(evaluation.rationale),
                    evaluation.resume_recommendation.model_dump_json(),
                    self._dump([item.model_dump() for item in evaluation.skill_recommendations]),
                    int(evaluation.duplicate),
                    int(evaluation.requires_human_review),
                    created_at,
                    created_at,
                ),
            )

            row = connection.execute(
                """
                SELECT applications.*, jobs.*
                FROM applications
                JOIN jobs ON jobs.fingerprint = applications.job_fingerprint
                WHERE applications.profile_id = ? AND applications.job_fingerprint = ?
                """,
                (profile_id, fingerprint),
            ).fetchone()

            event_exists = connection.execute(
                "SELECT 1 FROM application_events WHERE application_id = ? LIMIT 1",
                (row["application_id"],),
            ).fetchone()
            if event_exists is None:
                connection.execute(
                    """
                    INSERT INTO application_events (application_id, from_status, to_status, note, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (row["application_id"], None, status, "Initial evaluation created.", created_at),
                )

        return self._application_from_row(row)

    def update_application_status(
        self,
        application_id: str,
        new_status: ApplicationStatus,
        note: str | None = None,
    ) -> ApplicationRecord:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT applications.*, jobs.*
                FROM applications
                JOIN jobs ON jobs.fingerprint = applications.job_fingerprint
                WHERE applications.application_id = ?
                """,
                (application_id,),
            ).fetchone()

            if row is None:
                raise ValueError(f"Unknown application_id: {application_id}")

            current_status = row["status"]
            if new_status != current_status and new_status not in self.allowed_transitions[current_status]:
                raise InvalidStatusTransitionError(
                    f"Cannot move application from {current_status} to {new_status}."
                )

            updated_at = _utc_now()
            connection.execute(
                """
                UPDATE applications
                SET status = ?, updated_at = ?
                WHERE application_id = ?
                """,
                (new_status, updated_at, application_id),
            )
            connection.execute(
                """
                INSERT INTO application_events (application_id, from_status, to_status, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (application_id, current_status, new_status, note, updated_at),
            )
            updated_row = connection.execute(
                """
                SELECT applications.*, jobs.*
                FROM applications
                JOIN jobs ON jobs.fingerprint = applications.job_fingerprint
                WHERE applications.application_id = ?
                """,
                (application_id,),
            ).fetchone()

        return self._application_from_row(updated_row)

    def create_execution_task(
        self,
        application_id: str,
        execution_type: ExecutionType,
        dry_run: bool,
        channel_target: str | None,
        note: str | None,
        payload: dict[str, object],
    ) -> ExecutionTaskRecord:
        application = self.get_application(application_id)
        if application is None:
            raise ValueError(f"Unknown application_id: {application_id}")

        task_id = str(uuid.uuid4())
        timestamp = _utc_now()
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO execution_tasks (
                    task_id, application_id, profile_id, execution_type, status, dry_run,
                    human_approved, channel_target, note, payload_json, result_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    application_id,
                    application.profile_id,
                    execution_type,
                    "approval_required",
                    int(dry_run),
                    0,
                    channel_target,
                    note,
                    self._dump(payload),
                    self._dump({}),
                    timestamp,
                    timestamp,
                ),
            )
            self._insert_execution_event(
                connection,
                task_id=task_id,
                event_type="created",
                message="Execution task created and awaiting human approval.",
                details={"execution_type": execution_type, "dry_run": dry_run},
                created_at=timestamp,
            )

            row = connection.execute(
                "SELECT * FROM execution_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()

        return self._execution_task_from_row(row)

    def get_execution_task(self, task_id: str) -> ExecutionTaskRecord | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM execution_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()

        if row is None:
            return None
        return self._execution_task_from_row(row)

    def list_execution_tasks(self, application_id: str) -> list[ExecutionTaskRecord]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM execution_tasks
                WHERE application_id = ?
                ORDER BY updated_at DESC
                """,
                (application_id,),
            ).fetchall()

        return [self._execution_task_from_row(row) for row in rows]

    def list_execution_events(self, task_id: str) -> list[ExecutionEventRecord]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM execution_events
                WHERE task_id = ?
                ORDER BY event_id ASC
                """,
                (task_id,),
            ).fetchall()

        return [self._execution_event_from_row(row) for row in rows]

    def approve_execution_task(self, task_id: str, note: str | None = None) -> ExecutionTaskRecord:
        task = self.get_execution_task(task_id)
        if task is None:
            raise ValueError(f"Unknown task_id: {task_id}")
        if task.status not in {"approval_required", "queued"}:
            raise InvalidStatusTransitionError(
                f"Cannot approve execution task in status {task.status}."
            )

        timestamp = _utc_now()
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                UPDATE execution_tasks
                SET human_approved = 1, status = ?, note = ?, updated_at = ?
                WHERE task_id = ?
                """,
                ("queued", note or task.note, timestamp, task_id),
            )
            self._insert_execution_event(
                connection,
                task_id=task_id,
                event_type="approved",
                message="Human approved the execution task and moved it to the queue.",
                details={"note": note or task.note},
                created_at=timestamp,
            )
            row = connection.execute(
                "SELECT * FROM execution_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()

        return self._execution_task_from_row(row)

    def update_execution_task(
        self,
        task_id: str,
        status: ExecutionStatus,
        result: dict[str, object] | None = None,
        note: str | None = None,
    ) -> ExecutionTaskRecord:
        task = self.get_execution_task(task_id)
        if task is None:
            raise ValueError(f"Unknown task_id: {task_id}")

        timestamp = _utc_now()
        merged_result = task.result.copy()
        if result:
            merged_result.update(result)

        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                UPDATE execution_tasks
                SET status = ?, result_json = ?, note = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (status, self._dump(merged_result), note or task.note, timestamp, task_id),
            )
            row = connection.execute(
                "SELECT * FROM execution_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()

        return self._execution_task_from_row(row)

    def list_queued_execution_tasks(self, limit: int) -> list[ExecutionTaskRecord]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM execution_tasks
                WHERE status = 'queued' AND human_approved = 1
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [self._execution_task_from_row(row) for row in rows]

    def log_execution_event(
        self,
        task_id: str,
        event_type: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> ExecutionEventRecord:
        if self.get_execution_task(task_id) is None:
            raise ValueError(f"Unknown task_id: {task_id}")

        timestamp = _utc_now()
        with get_connection(self.database_path) as connection:
            self._insert_execution_event(
                connection,
                task_id=task_id,
                event_type=event_type,
                message=message,
                details=details or {},
                created_at=timestamp,
            )
            row = connection.execute(
                """
                SELECT * FROM execution_events
                WHERE task_id = ?
                ORDER BY event_id DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()

        return self._execution_event_from_row(row)

    def _application_from_row(self, row: object) -> ApplicationRecord:
        return ApplicationRecord(
            application_id=row["application_id"],
            profile_id=row["profile_id"],
            job=JobPosting(
                job_id=row["job_id"],
                title=row["title"],
                company=row["company"],
                description=row["description"],
                location=row["location"],
                source=row["source"],
                url=row["url"],
                required_skills=self._load(row["required_skills_json"]),
                preferred_skills=self._load(row["preferred_skills_json"]),
            ),
            recommendation=row["recommendation"],
            status=row["status"],
            fit_score=row["fit_score"],
            rationale=self._load(row["rationale_json"]),
            resume_recommendation=ResumeRecommendation.model_validate_json(row["resume_recommendation_json"]),
            skill_recommendations=[
                SkillRecommendation.model_validate(item)
                for item in self._load(row["skill_recommendations_json"])
            ],
            duplicate=bool(row["duplicate"]),
            requires_human_review=bool(row["requires_human_review"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _execution_task_from_row(self, row: object) -> ExecutionTaskRecord:
        return ExecutionTaskRecord(
            task_id=row["task_id"],
            application_id=row["application_id"],
            profile_id=row["profile_id"],
            execution_type=row["execution_type"],
            status=row["status"],
            dry_run=bool(row["dry_run"]),
            human_approved=bool(row["human_approved"]),
            channel_target=row["channel_target"],
            note=row["note"],
            payload=self._load(row["payload_json"]),
            result=self._load(row["result_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _execution_event_from_row(self, row: object) -> ExecutionEventRecord:
        return ExecutionEventRecord(
            event_id=row["event_id"],
            task_id=row["task_id"],
            event_type=row["event_type"],
            message=row["message"],
            details=self._load(row["details_json"]),
            created_at=row["created_at"],
        )

    def _search_from_row(self, row: object) -> SavedSearch:
        return SavedSearch(
            search_id=row["search_id"],
            profile_id=row["profile_id"],
            name=row["name"],
            keywords=self._load(row["keywords_json"]),
            target_roles=self._load(row["target_roles_json"]),
            locations=self._load(row["locations_json"]),
            remote_only=bool(row["remote_only"]),
            salary_min=row["salary_min"],
            companies_include=self._load(row["companies_include_json"]),
            companies_exclude=self._load(row["companies_exclude_json"]),
            required_skills=self._load(row["required_skills_json"]),
            preferred_skills=self._load(row["preferred_skills_json"]),
            sources=self._load(row["sources_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _dump(self, value: object) -> str:
        return json.dumps(value)

    def _load(self, payload: str) -> object:
        return json.loads(payload)

    def _top_counts(self, counts: dict[str, int], limit: int = 5) -> list[tuple[str, int]]:
        return sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]

    def _insert_execution_event(
        self,
        connection: object,
        task_id: str,
        event_type: str,
        message: str,
        details: dict[str, object],
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO execution_events (task_id, event_type, message, details_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, event_type, message, self._dump(details), created_at),
        )


memory_store = MemoryStore()
