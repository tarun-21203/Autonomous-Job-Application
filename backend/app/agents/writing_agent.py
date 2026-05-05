from __future__ import annotations

from backend.app.schemas.domain import CandidateProfile, JobPosting, ResumeRecommendation
from backend.app.services.rag_service import retrieve_relevant_evidence


class WritingAgent:
    def recommend(self, profile: CandidateProfile, job: JobPosting) -> ResumeRecommendation:
        evidence = retrieve_relevant_evidence(profile, job)
        owned = {skill.lower() for skill in profile.skills}
        missing_keywords = [
            skill
            for skill in job.required_skills + job.preferred_skills
            if skill.lower() not in owned
        ]

        bullet_suggestions = [
            f"Rewrite a resume bullet to emphasize {skill} using concrete outcomes from past work."
            for skill in job.required_skills[:2]
        ]

        summary = (
            f"Tailor the resume toward {job.title} at {job.company} by surfacing the strongest evidence "
            "for matching skills and adding keywords that the current resume underrepresents."
        )

        return ResumeRecommendation(
            summary=summary,
            bullet_suggestions=bullet_suggestions,
            missing_keywords=missing_keywords[:5],
            evidence_used=evidence,
        )
