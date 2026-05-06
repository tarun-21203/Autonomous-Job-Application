from __future__ import annotations

from backend.app.schemas.domain import CandidateProfile, JobPosting


def retrieve_relevant_evidence(profile: CandidateProfile, job: JobPosting, limit: int = 3) -> list[str]:
    job_terms = {term.lower() for term in job.required_skills + job.preferred_skills}
    scored_lines: list[tuple[int, str]] = []

    for line in profile.achievements:
        line_lower = line.lower()
        overlap = sum(1 for term in job_terms if term and term in line_lower)
        if overlap:
            scored_lines.append((overlap, line))

    if scored_lines:
        scored_lines.sort(key=lambda item: item[0], reverse=True)
        return [line for _, line in scored_lines[:limit]]

    return profile.achievements[:limit]
