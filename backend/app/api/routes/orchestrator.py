from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.domain import (
    OrchestratorRunListResponse,
    OrchestratorRunRequest,
    OrchestratorRunResponse,
)
from backend.app.services.orchestrator_service import orchestrator_service


router = APIRouter()


@router.post("/runs", response_model=OrchestratorRunResponse)
def run_orchestrator(request: OrchestratorRunRequest) -> OrchestratorRunResponse:
    try:
        return orchestrator_service.run(request)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/runs/{run_id}", response_model=OrchestratorRunResponse)
def get_orchestrator_run(run_id: str) -> OrchestratorRunResponse:
    try:
        return orchestrator_service.get_run(run_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/profiles/{profile_id}/runs", response_model=OrchestratorRunListResponse)
def list_orchestrator_runs(profile_id: str) -> OrchestratorRunListResponse:
    try:
        runs = orchestrator_service.list_runs(profile_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return OrchestratorRunListResponse(profile_id=profile_id, runs=runs)
