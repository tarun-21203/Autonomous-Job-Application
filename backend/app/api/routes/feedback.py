from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.domain import FeedbackSummary
from backend.app.services.memory_store import memory_store


router = APIRouter()


@router.get("/profiles/{profile_id}/summary", response_model=FeedbackSummary)
def get_feedback_summary(profile_id: str) -> FeedbackSummary:
    if memory_store.get_profile(profile_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile_id: {profile_id}")
    return memory_store.get_feedback_summary(profile_id)
