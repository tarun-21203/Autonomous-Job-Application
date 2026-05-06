from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.domain import JobEvaluationRequest, JobEvaluationResponse
from backend.app.services.workflow import job_evaluation_workflow


router = APIRouter()


@router.post("/evaluate", response_model=JobEvaluationResponse)
def evaluate_jobs(request: JobEvaluationRequest) -> JobEvaluationResponse:
    try:
        return job_evaluation_workflow.run(profile_id=request.profile_id, jobs=request.jobs)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
