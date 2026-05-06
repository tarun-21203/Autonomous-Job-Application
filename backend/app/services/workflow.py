from __future__ import annotations

from backend.app.agents.research_agent import ResearchAgent
from backend.app.agents.resume_coach_agent import ResumeCoachAgent
from backend.app.agents.scoring_agent import ScoringAgent
from backend.app.agents.supervisor_agent import SupervisorAgent
from backend.app.agents.writing_agent import WritingAgent
from backend.app.schemas.domain import JobEvaluation, JobEvaluationResponse, JobPosting
from backend.app.services.memory_store import MemoryStore, memory_store


class JobEvaluationWorkflow:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self.research_agent = ResearchAgent()
        self.scoring_agent = ScoringAgent()
        self.writing_agent = WritingAgent()
        self.resume_coach_agent = ResumeCoachAgent()
        self.supervisor_agent = SupervisorAgent()
        self.store = store or memory_store

    def run(self, profile_id: str, jobs: list[JobPosting]) -> JobEvaluationResponse:
        profile = self.store.get_profile(profile_id)
        if profile is None:
            raise ValueError(f"Unknown profile_id: {profile_id}")
        feedback_summary = self.store.get_feedback_summary(profile_id)

        normalized_jobs = self.research_agent.normalize(jobs)
        evaluations: list[JobEvaluation] = []

        for job in normalized_jobs:
            existing = self.store.find_application(profile_id, job)
            duplicate = existing is not None
            fit_score, rationale = self.scoring_agent.evaluate(
                profile,
                job,
                feedback_summary=feedback_summary,
            )
            resume_recommendation = self.writing_agent.recommend(profile, job)
            skill_recommendations = self.resume_coach_agent.recommend_skills(
                profile,
                job,
                feedback_summary=feedback_summary,
            )
            recommendation = self.supervisor_agent.decide(fit_score, duplicate)

            evaluation = JobEvaluation(
                job=job,
                fit_score=fit_score,
                recommendation=recommendation,
                rationale=rationale,
                resume_recommendation=resume_recommendation,
                skill_recommendations=skill_recommendations,
                duplicate=duplicate,
                requires_human_review=True,
            )
            application = self.store.save_evaluation(
                profile_id=profile_id,
                evaluation=evaluation,
                current_status=existing.status if existing else None,
            )
            evaluations.append(
                evaluation.model_copy(
                    update={
                        "application_id": application.application_id,
                        "status": application.status,
                    }
                )
            )

        return JobEvaluationResponse(profile_id=profile_id, evaluations=evaluations)


job_evaluation_workflow = JobEvaluationWorkflow()
