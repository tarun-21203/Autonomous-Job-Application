from __future__ import annotations

from backend.app.core.config import settings


class SupervisorAgent:
    def decide(self, fit_score: float, duplicate: bool) -> str:
        if duplicate:
            return "skip"
        if fit_score >= settings.min_apply_score:
            return "apply"
        if fit_score >= settings.min_review_score:
            return "review"
        return "skip"
