from __future__ import annotations

from collections import defaultdict

from backend.app.schemas.domain import (
    CandidateProfile,
    JobPosting,
    LearningResource,
    SkillRoadmap,
    SkillRoadmapStep,
)


class SkillRoadmapService:
    def build(self, profile: CandidateProfile, jobs: list[JobPosting]) -> SkillRoadmap:
        owned = {skill.lower() for skill in profile.skills}
        weighted_gaps: dict[str, int] = defaultdict(int)

        for job in jobs:
            for skill in job.required_skills:
                if skill.lower() not in owned:
                    weighted_gaps[skill] += 3
            for skill in job.preferred_skills:
                if skill.lower() not in owned:
                    weighted_gaps[skill] += 1

        ranked_gaps = sorted(weighted_gaps.items(), key=lambda item: item[1], reverse=True)[:5]
        if not ranked_gaps:
            return SkillRoadmap(
                summary="Current profile already covers the strongest recurring skills across the selected jobs.",
                steps=[],
            )

        steps: list[SkillRoadmapStep] = []
        for index, (skill, weight) in enumerate(ranked_gaps, start=1):
            priority = "high" if index <= 2 else "medium"
            timeline_weeks = 2 if priority == "high" else 1
            steps.append(
                SkillRoadmapStep(
                    focus_skill=skill,
                    priority=priority,
                    reason=(
                        f"{skill} appears repeatedly across target jobs and is currently missing from the resume-backed profile."
                    ),
                    timeline_weeks=timeline_weeks,
                    resources=[
                        LearningResource(
                            title=f"{skill} fundamentals",
                            provider="Curated roadmap",
                            resource_type="course",
                        ),
                        LearningResource(
                            title=f"Build a mini project with {skill}",
                            provider="Project brief",
                            resource_type="project",
                        ),
                    ],
                    projects=[
                        f"Create a portfolio project that demonstrates {skill} in a backend workflow.",
                        f"Document measurable outcomes so the new skill can be added back into the resume.",
                    ],
                )
            )

        return SkillRoadmap(
            summary=(
                "Roadmap prioritized by recurring missing skills across the most relevant jobs, weighted toward required skills."
            ),
            steps=steps,
        )


skill_roadmap_service = SkillRoadmapService()
