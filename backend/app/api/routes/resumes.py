from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.app.schemas.domain import CandidateProfile, ResumeUploadResponse
from backend.app.services.memory_store import memory_store
from backend.app.services.resume_parser import (
    ResumeParsingError,
    UnsupportedResumeFormatError,
    build_profile,
    extract_resume_text,
)


router = APIRouter()


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    target_roles: str | None = Form(default=None),
    preferred_locations: str | None = Form(default=None),
) -> ResumeUploadResponse:
    try:
        content = await file.read()
        resume_text = extract_resume_text(file.filename, content)
        profile = build_profile(
            resume_text=resume_text,
            target_roles=_split_csv(target_roles),
            preferred_locations=_split_csv(preferred_locations),
            name=name,
        )
        memory_store.save_profile(profile)
    except UnsupportedResumeFormatError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ResumeParsingError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    summary = (
        f"Resume uploaded for profile {profile.profile_id}. "
        f"Detected {len(profile.skills)} skills and {len(profile.achievements)} reusable achievements."
    )
    return ResumeUploadResponse(profile=profile, summary=summary)


@router.get("/{profile_id}", response_model=CandidateProfile)
def get_profile(profile_id: str) -> CandidateProfile:
    profile = memory_store.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile_id: {profile_id}")
    return profile
