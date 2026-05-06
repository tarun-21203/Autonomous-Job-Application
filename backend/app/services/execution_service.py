from __future__ import annotations

from backend.app.schemas.domain import (
    ExecutionTaskRecord,
    ExecutionTaskRequest,
)
from backend.app.services.memory_store import InvalidStatusTransitionError, MemoryStore, memory_store


class ExecutionService:
    queueable_application_statuses = {"approved", "tailored"}

    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store or memory_store

    def create_task(self, application_id: str, request: ExecutionTaskRequest) -> ExecutionTaskRecord:
        application = self.store.get_application(application_id)
        if application is None:
            raise ValueError(f"Unknown application_id: {application_id}")
        if application.status not in self.queueable_application_statuses:
            raise InvalidStatusTransitionError(
                "Execution tasks can only be created for applications in approved or tailored status."
            )

        profile = self.store.get_profile(application.profile_id)
        payload = {
            "job_title": application.job.title,
            "company": application.job.company,
            "job_url": application.job.url,
            "resume_summary": application.resume_recommendation.summary,
            "recommended_bullets": application.resume_recommendation.bullet_suggestions,
            "evidence_used": application.resume_recommendation.evidence_used,
            "channel_target": request.channel_target,
            "candidate_name": profile.name if profile else None,
        }
        return self.store.create_execution_task(
            application_id=application_id,
            execution_type=request.execution_type,
            dry_run=request.dry_run,
            channel_target=request.channel_target,
            note=request.note,
            payload=payload,
        )

    def list_tasks(self, application_id: str) -> list[ExecutionTaskRecord]:
        if self.store.get_application(application_id) is None:
            raise ValueError(f"Unknown application_id: {application_id}")
        return self.store.list_execution_tasks(application_id)

    def approve_task(self, task_id: str, note: str | None = None) -> ExecutionTaskRecord:
        return self.store.approve_execution_task(task_id, note=note)

    def process_queue(self, limit: int) -> list[ExecutionTaskRecord]:
        processed: list[ExecutionTaskRecord] = []
        queued_tasks = self.store.list_queued_execution_tasks(limit)

        for queued_task in queued_tasks:
            self.store.update_execution_task(
                queued_task.task_id,
                status="running",
                note=queued_task.note,
            )
            self.store.log_execution_event(
                queued_task.task_id,
                event_type="started",
                message="Queue worker started processing the execution task.",
                details={"execution_type": queued_task.execution_type},
            )

            try:
                result = self._execute_task(queued_task.task_id)
                completed_task = self.store.update_execution_task(
                    queued_task.task_id,
                    status="completed",
                    result=result,
                    note=queued_task.note,
                )
                self.store.log_execution_event(
                    queued_task.task_id,
                    event_type="completed",
                    message="Execution task completed successfully.",
                    details=result,
                )
                self.store.log_execution_event(
                    queued_task.task_id,
                    event_type="awaiting_submission_confirmation",
                    message="Execution output is ready; human confirmation is still required before marking the application as submitted.",
                    details={"application_id": completed_task.application_id},
                )
                processed.append(completed_task)
            except Exception as error:
                failed_task = self.store.update_execution_task(
                    queued_task.task_id,
                    status="failed",
                    result={"error": str(error)},
                    note=queued_task.note,
                )
                self.store.log_execution_event(
                    queued_task.task_id,
                    event_type="failed",
                    message="Execution task failed during processing.",
                    details={"error": str(error)},
                )
                processed.append(failed_task)

        return processed

    def confirm_submission(self, task_id: str, note: str | None = None) -> ExecutionTaskRecord:
        task = self.store.get_execution_task(task_id)
        if task is None:
            raise ValueError(f"Unknown task_id: {task_id}")
        if task.status != "completed":
            raise InvalidStatusTransitionError(
                "Only completed execution tasks can be confirmed as submitted."
            )

        application = self.store.get_application(task.application_id)
        if application is None:
            raise ValueError(f"Unknown application for task {task_id}")
        if application.status not in self.queueable_application_statuses and application.status != "applied":
            raise InvalidStatusTransitionError(
                "The application is not in a confirmable status for submission."
            )

        if application.status != "applied":
            self.store.update_application_status(
                application.application_id,
                "applied",
                note=note or f"Human confirmed submission after execution task {task_id}.",
            )

        self.store.log_execution_event(
            task_id,
            event_type="submission_confirmed",
            message="Human confirmed that the application was submitted.",
            details={"note": note or ""},
        )
        refreshed = self.store.get_execution_task(task_id)
        if refreshed is None:
            raise ValueError(f"Unknown task_id: {task_id}")
        return refreshed

    def _execute_task(self, task_id: str) -> dict[str, object]:
        task = self.store.get_execution_task(task_id)
        if task is None:
            raise ValueError(f"Unknown task_id: {task_id}")

        application = self.store.get_application(task.application_id)
        if application is None:
            raise ValueError(f"Unknown application for task {task_id}")

        if task.execution_type == "manual_browser":
            return {
                "mode": "dry_run" if task.dry_run else "live_stub",
                "submission_ready": True,
                "steps": [
                    f"Open the job page for {application.job.title} at {application.job.company}.",
                    "Review the tailored resume bullets before filling any form.",
                    "Pause for the human to confirm submission before the final click.",
                ],
            }
        if task.execution_type == "email_draft":
            return {
                "mode": "dry_run" if task.dry_run else "live_stub",
                "submission_ready": True,
                "subject": f"Application for {application.job.title} - {application.job.company}",
                "body": (
                    f"Hello,\n\nI am interested in the {application.job.title} role at "
                    f"{application.job.company}. I have attached a tailored resume based on the role.\n"
                ),
            }
        if task.execution_type == "api_stub":
            return {
                "mode": "dry_run" if task.dry_run else "live_stub",
                "submission_ready": True,
                "payload_preview": {
                    "job_id": application.job.job_id,
                    "company": application.job.company,
                    "title": application.job.title,
                    "resume_summary": application.resume_recommendation.summary,
                },
                "warning": "External submission adapters are not implemented yet; this is a controlled stub.",
            }

        raise ValueError(f"Unsupported execution type: {task.execution_type}")


execution_service = ExecutionService()
