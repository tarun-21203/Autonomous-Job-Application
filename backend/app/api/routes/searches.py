from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.domain import (
    SavedSearch,
    SavedSearchCreateRequest,
    SavedSearchListResponse,
    SearchRunRequest,
    SearchRunResponse,
)
from backend.app.services.search_service import search_service


router = APIRouter()


@router.post("", response_model=SavedSearch)
def create_saved_search(request: SavedSearchCreateRequest) -> SavedSearch:
    try:
        return search_service.create_search(request)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/profiles/{profile_id}", response_model=SavedSearchListResponse)
def list_saved_searches(profile_id: str) -> SavedSearchListResponse:
    try:
        searches = search_service.list_searches(profile_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return SavedSearchListResponse(profile_id=profile_id, searches=searches)


@router.post("/{search_id}/run", response_model=SearchRunResponse)
def run_saved_search(search_id: str, request: SearchRunRequest) -> SearchRunResponse:
    try:
        return search_service.run_search(
            search_id=search_id,
            evaluate_jobs=request.evaluate_jobs,
            limit=request.limit,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
