from __future__ import annotations

from backend.app.schemas.domain import JobPosting


class ResearchAgent:
    """Normalizes incoming job records.

    Real integrations can later plug in job APIs, company career pages, and controlled scraping.
    """

    def normalize(self, jobs: list[JobPosting]) -> list[JobPosting]:
        normalized: list[JobPosting] = []
        for job in jobs:
            normalized.append(
                job.model_copy(
                    update={
                        "required_skills": [skill.strip() for skill in job.required_skills if skill.strip()],
                        "preferred_skills": [skill.strip() for skill in job.preferred_skills if skill.strip()],
                    }
                )
            )
        return normalized
