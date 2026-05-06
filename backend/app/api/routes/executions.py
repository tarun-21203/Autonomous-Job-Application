from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.domain import (
    ExecutionApprovalRequest,
    ExecutionEventListResponse,
    ExecutionQueueProcessRequest,
    ExecutionQueueProcessResponse,
    ExecutionSubmissionConfirmationRequest,
    ExecutionTaskListResponse,
    ExecutionTaskRequest,
    ExecutionTaskResponse,
)
from backend.app.services.execution_service import execution_service
from backend.app.services.memory_store import InvalidStatusTransitionError, memory_store


router = APIRouter()


@router.post("/applications/{application_id}", response_model=ExecutionTaskResponse)
def create_execution_task(
    application_id: str,
    request: ExecutionTaskRequest,
) -> ExecutionTaskResponse:
    try:
        task = execution_service.create_task(application_id, request)
    except InvalidStatusTransitionError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return ExecutionTaskResponse(
        task=task,
        message="Execution task created and is waiting for human approval.",
    )


@router.get("/applications/{application_id}", response_model=ExecutionTaskListResponse)
def list_execution_tasks(application_id: str) -> ExecutionTaskListResponse:
    try:
        tasks = execution_service.list_tasks(application_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return ExecutionTaskListResponse(application_id=application_id, tasks=tasks)


@router.get("/{task_id}/events", response_model=ExecutionEventListResponse)
def list_execution_events(task_id: str) -> ExecutionEventListResponse:
    if memory_store.get_execution_task(task_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown task_id: {task_id}")
    events = memory_store.list_execution_events(task_id)
    return ExecutionEventListResponse(task_id=task_id, events=events)


@router.post("/{task_id}/approve", response_model=ExecutionTaskResponse)
def approve_execution_task(
    task_id: str,
    request: ExecutionApprovalRequest,
) -> ExecutionTaskResponse:
    try:
        task = execution_service.approve_task(task_id, note=request.note)
    except InvalidStatusTransitionError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return ExecutionTaskResponse(
        task=task,
        message="Execution task approved and queued for processing.",
    )


@router.post("/{task_id}/confirm-submitted", response_model=ExecutionTaskResponse)
def confirm_submitted_execution_task(
    task_id: str,
    request: ExecutionSubmissionConfirmationRequest,
) -> ExecutionTaskResponse:
    try:
        task = execution_service.confirm_submission(task_id, note=request.note)
    except InvalidStatusTransitionError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return ExecutionTaskResponse(
        task=task,
        message="Application submission confirmed by the human reviewer.",
    )


@router.post("/process", response_model=ExecutionQueueProcessResponse)
def process_execution_queue(request: ExecutionQueueProcessRequest) -> ExecutionQueueProcessResponse:
    tasks = execution_service.process_queue(limit=request.limit)
    return ExecutionQueueProcessResponse(
        processed_count=len(tasks),
        tasks=tasks,
        message=f"Processed {len(tasks)} queued execution task(s).",
    )
