from __future__ import annotations

from backend.app.schemas.domain import CandidateProfile, FeedbackSummary, JobPosting, SkillRecommendation


def recommend_skill_gaps(
    profile: CandidateProfile,
    job: JobPosting,
    feedback_summary: FeedbackSummary | None = None,
) -> list[SkillRecommendation]:
    owned = {skill.lower() for skill in profile.skills}
    required = [skill for skill in job.required_skills if skill.lower() not in owned]
    preferred = [skill for skill in job.preferred_skills if skill.lower() not in owned]
    recurring_missing = {
        item.skill.lower(): item.count for item in (feedback_summary.recurring_missing_skills if feedback_summary else [])
    }

    recommendations: list[SkillRecommendation] = []

    for skill in required[:3]:
        recurring_count = recurring_missing.get(skill.lower(), 0)
        reason = f"{skill} appears to be a direct requirement for this role and is not visible in the current resume."
        if recurring_count:
            reason += f" It has also appeared as a repeated gap in {recurring_count} past applications."
        recommendations.append(
            SkillRecommendation(
                skill=skill,
                priority="high",
                reason=reason,
            )
        )

    for skill in preferred[:2]:
        recurring_count = recurring_missing.get(skill.lower(), 0)
        reason = f"{skill} is a differentiator for this role and could improve competitiveness against other applicants."
        if recurring_count:
            reason += f" It keeps recurring as a gap across prior outcomes too."
        recommendations.append(
            SkillRecommendation(
                skill=skill,
                priority="medium",
                reason=reason,
            )
        )

    return recommendations
