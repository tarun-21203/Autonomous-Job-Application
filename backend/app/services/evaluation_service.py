from __future__ import annotations

from backend.app.schemas.domain import (
    EvaluationBundle,
    EvaluationMetric,
    JobEvaluation,
    ResumeRecommendation,
    SkillRoadmap,
)


class EvaluationService:
    def evaluate(
        self,
        evaluations: list[JobEvaluation],
        resume_recommendation: ResumeRecommendation | None,
        skill_roadmap: SkillRoadmap | None,
    ) -> EvaluationBundle:
        average_fit = (
            sum(item.fit_score for item in evaluations) / len(evaluations) if evaluations else 0.0
        )
        top_recommendation_score = self._recommendation_score(evaluations)
        resume_alignment = self._resume_alignment_score(resume_recommendation)
        roadmap_feasibility = self._roadmap_feasibility_score(skill_roadmap)

        metrics = [
            EvaluationMetric(
                name="job_match_confidence",
                score=round(average_fit, 2),
                reasoning="Average fit score across the shortlisted jobs.",
            ),
            EvaluationMetric(
                name="recommendation_strength",
                score=round(top_recommendation_score, 2),
                reasoning="Weighted strength of apply/review signals from the job evaluations.",
            ),
            EvaluationMetric(
                name="resume_alignment",
                score=round(resume_alignment, 2),
                reasoning="How actionable and keyword-complete the selected resume recommendation looks.",
            ),
            EvaluationMetric(
                name="roadmap_feasibility",
                score=round(roadmap_feasibility, 2),
                reasoning="Whether the proposed learning roadmap looks focused enough to be realistic.",
            ),
        ]

        overall_confidence = round(
            (average_fit * 0.4)
            + (top_recommendation_score * 0.25)
            + (resume_alignment * 0.2)
            + (roadmap_feasibility * 0.15),
            2,
        )
        needs_human_review = overall_confidence < 72 or top_recommendation_score < 65

        reflection = (
            "The run has enough signal to continue with human review and approval."
            if not needs_human_review
            else "Confidence is still mixed. A human should inspect the selected job, resume tailoring, and roadmap before acting."
        )

        summary = (
            f"Overall confidence {overall_confidence}. "
            f"Top job signal is {round(top_recommendation_score, 2)} and roadmap feasibility is {round(roadmap_feasibility, 2)}."
        )

        return EvaluationBundle(
            overall_confidence=overall_confidence,
            needs_human_review=needs_human_review,
            summary=summary,
            reflection=reflection,
            metrics=metrics,
        )

    def _recommendation_score(self, evaluations: list[JobEvaluation]) -> float:
        if not evaluations:
            return 0.0
        mapping = {"apply": 100.0, "review": 70.0, "skip": 25.0}
        values = [mapping.get(item.recommendation, 25.0) for item in evaluations]
        return sum(values) / len(values)

    def _resume_alignment_score(self, resume_recommendation: ResumeRecommendation | None) -> float:
        if resume_recommendation is None:
            return 0.0
        evidence_bonus = min(len(resume_recommendation.evidence_used) * 12, 36)
        keyword_penalty = min(len(resume_recommendation.missing_keywords) * 6, 36)
        bullet_bonus = min(len(resume_recommendation.bullet_suggestions) * 10, 30)
        return max(0.0, min(100.0, 45.0 + evidence_bonus + bullet_bonus - keyword_penalty))

    def _roadmap_feasibility_score(self, skill_roadmap: SkillRoadmap | None) -> float:
        if skill_roadmap is None:
            return 0.0
        if not skill_roadmap.steps:
            return 92.0
        total_weeks = sum(step.timeline_weeks for step in skill_roadmap.steps)
        focus_count = len(skill_roadmap.steps)
        return max(35.0, min(100.0, 96.0 - (focus_count * 6.0) - max(total_weeks - 8, 0) * 2.0))


evaluation_service = EvaluationService()
