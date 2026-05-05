from __future__ import annotations

from backend.app.schemas.domain import CandidateProfile, FeedbackSummary, JobPosting


class ScoringAgent:
    def evaluate(
        self,
        profile: CandidateProfile,
        job: JobPosting,
        feedback_summary: FeedbackSummary | None = None,
    ) -> tuple[float, list[str]]:
        owned = {skill.lower() for skill in profile.skills}
        required = {skill.lower() for skill in job.required_skills}
        preferred = {skill.lower() for skill in job.preferred_skills}

        required_matches = len(required & owned)
        preferred_matches = len(preferred & owned)
        role_match = any(role.lower() in job.title.lower() for role in profile.target_roles)
        location_match = not profile.preferred_locations or (job.location and job.location in profile.preferred_locations)

        required_ratio = required_matches / max(len(required), 1)
        preferred_ratio = preferred_matches / max(len(preferred), 1) if preferred else 0.5

        score = 40 * required_ratio + 20 * preferred_ratio
        if role_match:
            score += 25
        if location_match:
            score += 15

        reasons = [
            f"Matched {required_matches} of {len(required)} required skills.",
            f"Matched {preferred_matches} of {len(preferred)} preferred skills." if preferred else "No preferred skills were provided in the posting.",
        ]

        if role_match:
            reasons.append("Job title aligns with at least one target role from the candidate profile.")
        if location_match:
            reasons.append("Location is compatible with current preferences.")

        if feedback_summary and feedback_summary.total_applications:
            successful_roles = {item.role.lower() for item in feedback_summary.successful_roles}
            successful_skills = {item.skill.lower() for item in feedback_summary.successful_skills}
            recurring_missing_skills = {item.skill.lower() for item in feedback_summary.recurring_missing_skills}

            if any(role in job.title.lower() or job.title.lower() in role for role in successful_roles):
                score += 8
                reasons.append("Past positive outcomes suggest this role family performs well for the candidate.")

            if (required | preferred) & successful_skills:
                score += 7
                reasons.append("Past positive outcomes align with skills emphasized in this role.")

            if required & recurring_missing_skills:
                score -= 5
                reasons.append("This role depends on skills that have repeatedly shown up as growth gaps.")

        return round(max(0, min(score, 100)), 2), reasons
