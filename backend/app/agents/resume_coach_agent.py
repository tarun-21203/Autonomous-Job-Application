from __future__ import annotations

from backend.app.schemas.domain import CandidateProfile, FeedbackSummary, JobPosting, SkillRecommendation
from backend.app.services.skill_gap import recommend_skill_gaps


class ResumeCoachAgent:
    def recommend_skills(
        self,
        profile: CandidateProfile,
        job: JobPosting,
        feedback_summary: FeedbackSummary | None = None,
    ) -> list[SkillRecommendation]:
        return recommend_skill_gaps(profile, job, feedback_summary=feedback_summary)
