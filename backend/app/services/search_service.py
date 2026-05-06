from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable
from uuid import uuid4

from backend.app.schemas.domain import (
    JobPosting,
    SavedSearch,
    SavedSearchCreateRequest,
    SearchRunResponse,
)
from backend.app.services.job_sources import (
    FetchResult,
    GreenhouseJobSource,
    LeverJobSource,
    LinkedInJobSource,
    JobSourceError,
    MockJobSource,
    RemoteOKJobSource,
    SerpApiJobSource,
)
from backend.app.services.memory_store import MemoryStore, memory_store
from backend.app.services.workflow import JobEvaluationWorkflow


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class SearchService:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store or memory_store
        self.workflow = JobEvaluationWorkflow(store=self.store)
        self.providers = {
            "mock": MockJobSource(),
            "remoteok": RemoteOKJobSource(),
            "linkedin": LinkedInJobSource(),
            "greenhouse": GreenhouseJobSource(),
            "lever": LeverJobSource(),
            "serpapi": SerpApiJobSource(),
        }

    def create_search(self, request: SavedSearchCreateRequest) -> SavedSearch:
        if self.store.get_profile(request.profile_id) is None:
            raise ValueError(f"Unknown profile_id: {request.profile_id}")

        timestamp = _utc_now()
        search = SavedSearch(
            search_id=str(uuid4()),
            profile_id=request.profile_id,
            name=request.name,
            keywords=request.keywords,
            target_roles=request.target_roles,
            locations=request.locations,
            remote_only=request.remote_only,
            salary_min=request.salary_min,
            companies_include=request.companies_include,
            companies_exclude=request.companies_exclude,
            required_skills=request.required_skills,
            preferred_skills=request.preferred_skills,
            sources=request.sources,
            created_at=timestamp,
            updated_at=timestamp,
        )
        return self.store.save_search(search)

    def list_searches(self, profile_id: str) -> list[SavedSearch]:
        if self.store.get_profile(profile_id) is None:
            raise ValueError(f"Unknown profile_id: {profile_id}")
        return self.store.list_searches(profile_id)

    def run_search(self, search_id: str, evaluate_jobs: bool, limit: int) -> SearchRunResponse:
        search = self.store.get_search(search_id)
        if search is None:
            raise ValueError(f"Unknown search_id: {search_id}")

        jobs: list[JobPosting] = []
        warnings: list[str] = []
        for source in search.sources:
            provider = self.providers.get(source)
            if provider is None:
                warnings.append(f"Unknown job source '{source}' was skipped.")
                continue
            try:
                result = provider.fetch_jobs(search, limit)
            except JobSourceError as error:
                warnings.append(str(error))
                continue
            jobs.extend(result.jobs)
            warnings.extend(result.warnings)

        unique_jobs = list(self._dedupe(jobs))[:limit]
        for job in unique_jobs:
            self.store.save_job(job)

        evaluations = []
        if evaluate_jobs and unique_jobs:
            evaluations = self.workflow.run(search.profile_id, unique_jobs).evaluations

        run = self.store.save_search_run(
            search_id=search_id,
            sources=search.sources,
            fetched_count=len(unique_jobs),
            warnings=warnings,
        )
        return SearchRunResponse(
            search=search,
            run=run,
            jobs=unique_jobs,
            evaluations=evaluations,
        )

    def _dedupe(self, jobs: Iterable[JobPosting]) -> Iterable[JobPosting]:
        seen: set[tuple[str, str, str]] = set()
        for job in jobs:
            key = (
                job.company.strip().lower(),
                job.title.strip().lower(),
                (job.location or "").strip().lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            yield job


search_service = SearchService()
