from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import uuid

from backend.app.core.config import settings
from backend.app.db.database import get_connection, initialize_database
from backend.app.schemas.domain import (
    EvaluationBundle,
    JobEvaluation,
    JobPosting,
    OrchestratorRunRecord,
    OrchestratorRunStatus,
    OrchestratorStepRecord,
    OrchestratorStepStatus,
    RankedJobInsight,
    ResumeRecommendation,
    SkillRoadmap,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class OrchestrationStore:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path or settings.database_path)
        initialize_database(self.database_path)

    def create_run(self, profile_id: str, goal: str, plan: list[str]) -> OrchestratorRunRecord:
        run_id = str(uuid.uuid4())
        timestamp = _utc_now()
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO orchestrator_runs (
                    run_id, profile_id, goal, status, plan_json, observations_json, selected_job_json,
                    ranked_jobs_json, evaluations_json, skill_roadmap_json, resume_recommendation_json,
                    evaluation_bundle_json, needs_human_review, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    profile_id,
                    goal,
                    "created",
                    self._dump(plan),
                    self._dump([]),
                    None,
                    self._dump([]),
                    self._dump([]),
                    None,
                    None,
                    None,
                    1,
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                "SELECT * FROM orchestrator_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return self._run_from_row(row)

    def update_run(
        self,
        run_id: str,
        *,
        status: OrchestratorRunStatus | None = None,
        observations: list[str] | None = None,
        selected_job: JobPosting | None = None,
        ranked_jobs: list[RankedJobInsight] | None = None,
        evaluations: list[JobEvaluation] | None = None,
        skill_roadmap: SkillRoadmap | None = None,
        resume_recommendation: ResumeRecommendation | None = None,
        evaluation_bundle: EvaluationBundle | None = None,
        needs_human_review: bool | None = None,
    ) -> OrchestratorRunRecord:
        run = self.get_run(run_id)
        if run is None:
            raise ValueError(f"Unknown run_id: {run_id}")

        updated_run = run.model_copy(
            update={
                "status": status or run.status,
                "observations": observations if observations is not None else run.observations,
                "selected_job": selected_job if selected_job is not None else run.selected_job,
                "ranked_jobs": ranked_jobs if ranked_jobs is not None else run.ranked_jobs,
                "evaluations": evaluations if evaluations is not None else run.evaluations,
                "skill_roadmap": skill_roadmap if skill_roadmap is not None else run.skill_roadmap,
                "resume_recommendation": (
                    resume_recommendation if resume_recommendation is not None else run.resume_recommendation
                ),
                "evaluation_bundle": evaluation_bundle if evaluation_bundle is not None else run.evaluation_bundle,
                "needs_human_review": (
                    needs_human_review if needs_human_review is not None else run.needs_human_review
                ),
                "updated_at": _utc_now(),
            }
        )

        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                UPDATE orchestrator_runs
                SET status = ?, observations_json = ?, selected_job_json = ?, ranked_jobs_json = ?,
                    evaluations_json = ?, skill_roadmap_json = ?, resume_recommendation_json = ?,
                    evaluation_bundle_json = ?, needs_human_review = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (
                    updated_run.status,
                    self._dump(updated_run.observations),
                    updated_run.selected_job.model_dump_json() if updated_run.selected_job else None,
                    self._dump([item.model_dump() for item in updated_run.ranked_jobs]),
                    self._dump([item.model_dump() for item in updated_run.evaluations]),
                    updated_run.skill_roadmap.model_dump_json() if updated_run.skill_roadmap else None,
                    updated_run.resume_recommendation.model_dump_json() if updated_run.resume_recommendation else None,
                    updated_run.evaluation_bundle.model_dump_json() if updated_run.evaluation_bundle else None,
                    int(updated_run.needs_human_review),
                    updated_run.updated_at,
                    run_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM orchestrator_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return self._run_from_row(row)

    def get_run(self, run_id: str) -> OrchestratorRunRecord | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM orchestrator_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return self._run_from_row(row)

    def list_runs(self, profile_id: str) -> list[OrchestratorRunRecord]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM orchestrator_runs
                WHERE profile_id = ?
                ORDER BY updated_at DESC
                """,
                (profile_id,),
            ).fetchall()
        return [self._run_from_row(row) for row in rows]

    def create_step(
        self,
        run_id: str,
        name: str,
        input_payload: dict[str, object],
    ) -> OrchestratorStepRecord:
        step_id = str(uuid.uuid4())
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO orchestrator_steps (
                    step_id, run_id, name, status, input_payload_json, output_payload_json,
                    reflection, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step_id,
                    run_id,
                    name,
                    "pending",
                    self._dump(input_payload),
                    self._dump({}),
                    None,
                    None,
                    None,
                ),
            )
            row = connection.execute(
                "SELECT * FROM orchestrator_steps WHERE step_id = ?",
                (step_id,),
            ).fetchone()
        return self._step_from_row(row)

    def update_step(
        self,
        step_id: str,
        *,
        status: OrchestratorStepStatus,
        output_payload: dict[str, object] | None = None,
        reflection: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> OrchestratorStepRecord:
        step = self.get_step(step_id)
        if step is None:
            raise ValueError(f"Unknown step_id: {step_id}")

        updated = step.model_copy(
            update={
                "status": status,
                "output_payload": output_payload if output_payload is not None else step.output_payload,
                "reflection": reflection if reflection is not None else step.reflection,
                "started_at": started_at if started_at is not None else step.started_at,
                "completed_at": completed_at if completed_at is not None else step.completed_at,
            }
        )

        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                UPDATE orchestrator_steps
                SET status = ?, output_payload_json = ?, reflection = ?, started_at = ?, completed_at = ?
                WHERE step_id = ?
                """,
                (
                    updated.status,
                    self._dump(updated.output_payload),
                    updated.reflection,
                    updated.started_at,
                    updated.completed_at,
                    step_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM orchestrator_steps WHERE step_id = ?",
                (step_id,),
            ).fetchone()
        return self._step_from_row(row)

    def get_step(self, step_id: str) -> OrchestratorStepRecord | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM orchestrator_steps WHERE step_id = ?",
                (step_id,),
            ).fetchone()
        if row is None:
            return None
        return self._step_from_row(row)

    def list_steps(self, run_id: str) -> list[OrchestratorStepRecord]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM orchestrator_steps
                WHERE run_id = ?
                ORDER BY rowid ASC
                """,
                (run_id,),
            ).fetchall()
        return [self._step_from_row(row) for row in rows]

    def _run_from_row(self, row: object) -> OrchestratorRunRecord:
        return OrchestratorRunRecord(
            run_id=row["run_id"],
            profile_id=row["profile_id"],
            goal=row["goal"],
            status=row["status"],
            plan=self._load(row["plan_json"]),
            observations=self._load(row["observations_json"]),
            selected_job=JobPosting.model_validate_json(row["selected_job_json"]) if row["selected_job_json"] else None,
            ranked_jobs=[RankedJobInsight.model_validate(item) for item in self._load(row["ranked_jobs_json"])],
            evaluations=[JobEvaluation.model_validate(item) for item in self._load(row["evaluations_json"])],
            skill_roadmap=SkillRoadmap.model_validate_json(row["skill_roadmap_json"]) if row["skill_roadmap_json"] else None,
            resume_recommendation=(
                ResumeRecommendation.model_validate_json(row["resume_recommendation_json"])
                if row["resume_recommendation_json"]
                else None
            ),
            evaluation_bundle=(
                EvaluationBundle.model_validate_json(row["evaluation_bundle_json"])
                if row["evaluation_bundle_json"]
                else None
            ),
            needs_human_review=bool(row["needs_human_review"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _step_from_row(self, row: object) -> OrchestratorStepRecord:
        return OrchestratorStepRecord(
            step_id=row["step_id"],
            run_id=row["run_id"],
            name=row["name"],
            status=row["status"],
            input_payload=self._load(row["input_payload_json"]),
            output_payload=self._load(row["output_payload_json"]),
            reflection=row["reflection"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )

    def _dump(self, value: object) -> str:
        return json.dumps(value)

    def _load(self, payload: str) -> object:
        return json.loads(payload)


orchestration_store = OrchestrationStore()
