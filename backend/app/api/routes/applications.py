from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.domain import (
    ApplicationListResponse,
    ApplicationStatusUpdateRequest,
    ApplicationStatusUpdateResponse,
)
from backend.app.services.memory_store import InvalidStatusTransitionError, memory_store


router = APIRouter()


@router.get("/profiles/{profile_id}", response_model=ApplicationListResponse)
def list_profile_applications(profile_id: str) -> ApplicationListResponse:
    if memory_store.get_profile(profile_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile_id: {profile_id}")
    applications = memory_store.list_applications(profile_id)
    return ApplicationListResponse(profile_id=profile_id, applications=applications)


@router.post("/{application_id}/status", response_model=ApplicationStatusUpdateResponse)
def update_application_status(
    application_id: str,
    request: ApplicationStatusUpdateRequest,
) -> ApplicationStatusUpdateResponse:
    try:
        application = memory_store.update_application_status(
            application_id=application_id,
            new_status=request.status,
            note=request.note,
        )
    except InvalidStatusTransitionError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return ApplicationStatusUpdateResponse(
        application=application,
        message=f"Application {application_id} moved to {request.status}.",
    )
