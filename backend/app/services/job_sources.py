from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches
import json
import re
from urllib import error, parse, request

from backend.app.core.config import settings
from backend.app.schemas.domain import JobPosting, SavedSearch


class JobSourceError(RuntimeError):
    pass


@dataclass
class FetchResult:
    jobs: list[JobPosting]
    warnings: list[str]


@dataclass(frozen=True)
class JobRelevance:
    job: JobPosting
    score: float


@dataclass(frozen=True)
class QueryVariant:
    query: str
    location: str
    label: str


SKILL_VOCAB = [
    "Python",
    "Java",
    "JavaScript",
    "TypeScript",
    "Go",
    "Rust",
    "C#",
    "C++",
    "SQL",
    "PostgreSQL",
    "MySQL",
    "FastAPI",
    "Django",
    "Flask",
    "Node.js",
    "React",
    "Angular",
    "Vue",
    "Kubernetes",
    "Docker",
    "AWS",
    "Azure",
    "GCP",
    "Terraform",
    "Kafka",
    "Spark",
    "Redis",
    "GraphQL",
    "Machine Learning",
    "PyTorch",
]

ROLE_ALIASES = {
    "backend developer": "Backend Engineer",
    "backend engineer": "Backend Engineer",
    "backend": "Backend Engineer",
    "back end": "Backend Engineer",
    "back-end": "Backend Engineer",
    "frontend developer": "Frontend Engineer",
    "frontend engineer": "Frontend Engineer",
    "frontend": "Frontend Engineer",
    "front end": "Frontend Engineer",
    "front-end": "Frontend Engineer",
    "fullstack": "Full Stack Engineer",
    "full stack": "Full Stack Engineer",
    "full-stack": "Full Stack Engineer",
    "sde": "Software Engineer",
    "software developer": "Software Engineer",
    "software engineer": "Software Engineer",
    "developer": "Software Engineer",
    "data science": "Data Scientist",
    "data scientist": "Data Scientist",
    "data analyst": "Data Analyst",
    "machine learning": "Machine Learning Engineer",
    "ml engineer": "Machine Learning Engineer",
    "ai engineer": "AI Engineer",
    "devops": "DevOps Engineer",
    "site reliability": "Site Reliability Engineer",
    "sre": "Site Reliability Engineer",
    "qa": "QA Engineer",
    "quality assurance": "QA Engineer",
    "product manager": "Product Manager",
    "project manager": "Project Manager",
    "android": "Android Engineer",
    "ios": "iOS Engineer",
}

ROLE_EXPANSIONS = {
    "Backend Engineer": ["Software Engineer", "API Engineer", "Platform Engineer"],
    "Frontend Engineer": ["Software Engineer", "React Developer", "UI Engineer"],
    "Full Stack Engineer": ["Software Engineer", "Backend Engineer", "Frontend Engineer"],
    "Software Engineer": ["Software Developer", "Backend Engineer", "Frontend Engineer"],
    "Data Scientist": ["Machine Learning Engineer", "Data Analyst", "AI Engineer"],
    "Machine Learning Engineer": ["AI Engineer", "Data Scientist", "Software Engineer"],
    "AI Engineer": ["Machine Learning Engineer", "Data Scientist", "Software Engineer"],
    "DevOps Engineer": ["Site Reliability Engineer", "Platform Engineer", "Cloud Engineer"],
    "Site Reliability Engineer": ["DevOps Engineer", "Platform Engineer", "Cloud Engineer"],
    "QA Engineer": ["Software Test Engineer", "Automation Engineer"],
}

LOCATION_ALIASES = {
    "bangalore": "Bengaluru",
    "banglore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "gurgaon": "Gurugram",
    "gurugram": "Gurugram",
    "delhi ncr": "Delhi",
    "newyork": "New York",
    "new york": "New York",
    "nyc": "New York",
    "sanfrancisco": "San Francisco",
    "sf": "San Francisco",
    "toranto": "Toronto",
    "toronto": "Toronto",
    "vancover": "Vancouver",
    "vancouver": "Vancouver",
    "london uk": "London",
    "united states": "United States",
    "usa": "United States",
    "us": "United States",
    "canada": "Canada",
    "india": "India",
    "remote": "Remote",
    "remot": "Remote",
    "work from home": "Remote",
    "wfh": "Remote",
}

RELATED_MIN_SCORE = 18.0
STRONG_MIN_SCORE = 35.0
TOKEN_PATTERN = re.compile(r"[a-z0-9+#.]+")


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


def _clean_term(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _term_key(value: str) -> str:
    return re.sub(r"[^a-z0-9+#.]+", " ", value.lower()).strip()


def _tokens(value: str) -> set[str]:
    return {token for token in TOKEN_PATTERN.findall(value.lower()) if len(token) > 1}


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left.lower(), right.lower()).ratio()


def _normalise_from_alias(value: str, aliases: dict[str, str], cutoff: float = 0.82) -> str:
    cleaned = _clean_term(value)
    key = _term_key(cleaned)
    if not key:
        return ""
    if key in aliases:
        return aliases[key]

    match = get_close_matches(key, aliases.keys(), n=1, cutoff=cutoff)
    if match:
        return aliases[match[0]]
    return cleaned


def _normalise_role(value: str) -> str:
    cleaned = _normalise_from_alias(value, ROLE_ALIASES, cutoff=0.78)
    if cleaned != _clean_term(value):
        return cleaned

    words = []
    for token in _clean_term(value).split():
        match = get_close_matches(token.lower(), ["engineer", "developer", "software", "data", "analyst"], n=1, cutoff=0.78)
        words.append(match[0] if match else token)
    corrected = " ".join(words)
    return _normalise_from_alias(corrected, ROLE_ALIASES, cutoff=0.78)


def _normalise_location(value: str) -> str:
    return _normalise_from_alias(value, LOCATION_ALIASES, cutoff=0.78)


def _unique_terms(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_term(value)
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return unique


def _normalised_roles(search: SavedSearch) -> list[str]:
    roles = [_normalise_role(role) for role in search.target_roles]
    return _unique_terms(roles)


def _normalised_locations(search: SavedSearch) -> list[str]:
    locations = [_normalise_location(location) for location in search.locations]
    if search.remote_only:
        locations.insert(0, "Remote")
    return _unique_terms(locations)


def _search_adjustments(search: SavedSearch) -> list[str]:
    adjustments: list[str] = []
    for original, normalised in zip(search.target_roles, _normalised_roles(search), strict=False):
        if original.strip() and original.strip().lower() != normalised.lower():
            adjustments.append(f"role '{original}' -> '{normalised}'")
    for original, normalised in zip(search.locations, _normalised_locations(search), strict=False):
        if original.strip() and original.strip().lower() != normalised.lower():
            adjustments.append(f"location '{original}' -> '{normalised}'")
    return adjustments


def _related_roles(roles: list[str]) -> list[str]:
    related: list[str] = []
    for role in roles:
        related.extend(ROLE_EXPANSIONS.get(role, []))
    return _unique_terms(related)


def _job_relevance(job: JobPosting, search: SavedSearch) -> float:
    if search.companies_exclude and any(company.lower() in job.company.lower() for company in search.companies_exclude):
        return -1.0

    haystack = _build_haystack(job)
    title = job.title.lower()
    location = (job.location or "").lower()
    score = 0.0

    roles = _normalised_roles(search)
    if roles:
        role_scores = []
        for role in roles:
            role_key = role.lower()
            role_tokens = _tokens(role)
            title_tokens = _tokens(job.title)
            overlap = len(role_tokens & title_tokens) / max(1, len(role_tokens))
            ratio = max(_similarity(role_key, title), _similarity(role_key, haystack[:160]))
            if role_key in title:
                role_scores.append(42.0)
            elif role_key in haystack:
                role_scores.append(34.0)
            elif overlap >= 0.5:
                role_scores.append(24.0 + overlap * 10.0)
            elif ratio >= 0.72:
                role_scores.append(20.0 + ratio * 10.0)
            else:
                related = _related_roles([role])
                if any(related_role.lower() in haystack for related_role in related):
                    role_scores.append(18.0)
        score += max(role_scores, default=0.0)
    else:
        score += 12.0

    keywords = _unique_terms(search.keywords)
    if keywords:
        keyword_hits = sum(1 for keyword in keywords if keyword.lower() in haystack)
        score += min(18.0, keyword_hits * 5.0)

    required_hits = sum(1 for skill in search.required_skills if skill.lower() in haystack)
    preferred_hits = sum(1 for skill in search.preferred_skills if skill.lower() in haystack)
    score += min(24.0, required_hits * 7.0)
    score += min(12.0, preferred_hits * 4.0)

    locations = _normalised_locations(search)
    if locations:
        location_scores = []
        for desired in locations:
            desired_key = desired.lower()
            if desired_key == "remote" and "remote" in location:
                location_scores.append(24.0)
            elif desired_key in location:
                location_scores.append(22.0)
            elif _similarity(desired_key, location) >= 0.74:
                location_scores.append(16.0)
            elif desired_key in haystack:
                location_scores.append(12.0)
        score += max(location_scores, default=0.0)
    elif search.remote_only and "remote" in location:
        score += 24.0

    if search.companies_include:
        if any(company.lower() in job.company.lower() for company in search.companies_include):
            score += 16.0
        else:
            score -= 8.0

    return score


def _rank_jobs_for_search(jobs: list[JobPosting], search: SavedSearch, limit: int) -> tuple[list[JobPosting], list[str]]:
    ranked: list[JobRelevance] = []
    for job in jobs:
        score = _job_relevance(job, search)
        if score >= 0:
            ranked.append(JobRelevance(job=job, score=score))

    ranked.sort(key=lambda item: item.score, reverse=True)
    strong = [item for item in ranked if item.score >= STRONG_MIN_SCORE]
    related = [item for item in ranked if item.score >= RELATED_MIN_SCORE]

    warnings: list[str] = []
    adjustments = _search_adjustments(search)
    if adjustments:
        warnings.append(f"Normalized search input: {', '.join(adjustments)}.")

    selected = strong or related or ranked
    if ranked and not strong:
        warnings.append("No exact matches were found, so nearest related jobs were returned.")

    return [item.job for item in selected[:limit]], warnings


def _infer_skills(text: str) -> list[str]:
    lower_text = text.lower()
    return [skill for skill in SKILL_VOCAB if skill.lower() in lower_text][:10]


def _build_haystack(job: JobPosting) -> str:
    return " ".join(
        [
            job.title,
            job.company,
            job.description,
            " ".join(job.required_skills),
            " ".join(job.preferred_skills),
            job.location or "",
        ]
    ).lower()


def _search_matches_job(job: JobPosting, search: SavedSearch) -> bool:
    return _job_relevance(job, search) >= RELATED_MIN_SCORE


class MockJobSource:
    source_name = "mock"

    def fetch_jobs(self, search: SavedSearch, limit: int) -> FetchResult:
        roles = _normalised_roles(search) or search.target_roles or ["Software Engineer"]
        keywords = search.required_skills or search.preferred_skills or search.keywords or ["Python"]
        locations = _normalised_locations(search) or (["Remote"] if search.remote_only else ["Remote", "Hybrid"])

        jobs: list[JobPosting] = []
        for index, role in enumerate(roles, start=1):
            for location in locations:
                if len(jobs) >= limit:
                    break
                primary_skill = keywords[(index - 1) % len(keywords)]
                company = f"{role.split()[0]} Labs {index}"
                title = role if "engineer" in role.lower() else f"{role} Engineer"
                job_id = f"mock-{index}-{location.lower().replace(' ', '-')}"
                jobs.append(
                    JobPosting(
                        job_id=job_id,
                        title=title,
                        company=company,
                        description=(
                            f"{company} is hiring a {title} to work on backend systems, "
                            f"automation, and data workflows using {primary_skill}."
                        ),
                        location=location,
                        source=self.source_name,
                        url=f"https://example.com/jobs/{job_id}",
                        required_skills=list(dict.fromkeys(search.required_skills or [primary_skill, "SQL"])),
                        preferred_skills=list(dict.fromkeys(search.preferred_skills or ["Docker", "AWS"])),
                    )
                )
            if len(jobs) >= limit:
                break

        ranked_jobs, warnings = _rank_jobs_for_search(jobs, search, limit)
        return FetchResult(jobs=ranked_jobs[:limit], warnings=warnings)


class SerpApiJobSource:
    source_name = "serpapi"
    endpoint = "https://serpapi.com/search.json"

    def __init__(self) -> None:
        self.api_key = settings.serpapi_api_key.strip()

    def fetch_jobs(self, search: SavedSearch, limit: int) -> FetchResult:
        if not self.api_key:
            return FetchResult(
                jobs=[],
                warnings=[
                    "SERPAPI_API_KEY is not configured. Add it to your environment to fetch Google Jobs data."
                ],
            )

        warnings: list[str] = []
        candidates: list[JobPosting] = []
        seen: set[str] = set()

        for variant in self._build_query_variants(search):
            next_token: str | None = None
            max_pages = 2 if variant.label == "exact" else 1

            for _ in range(max_pages):
                payload = self._search_page(
                    query=variant.query,
                    location=variant.location,
                    next_page_token=next_token,
                )
                page_jobs = self._parse_jobs(payload)
                for job in page_jobs:
                    fingerprint = f"{job.company.lower()}::{job.title.lower()}::{(job.location or '').lower()}"
                    if fingerprint in seen:
                        continue
                    seen.add(fingerprint)
                    candidates.append(job)

                ranked, _ = _rank_jobs_for_search(candidates, search, limit)
                if len(ranked) >= limit and variant.label in {"exact", "normalized"}:
                    break

                next_token = payload.get("serpapi_pagination", {}).get("next_page_token")
                if not next_token:
                    break

            ranked, _ = _rank_jobs_for_search(candidates, search, limit)
            if len(ranked) >= limit:
                break

        jobs, ranking_warnings = _rank_jobs_for_search(candidates, search, limit)
        warnings.extend(ranking_warnings)
        if not candidates:
            warnings.append("SerpApi returned no jobs for the expanded query set.")
        elif not jobs:
            warnings.append("SerpApi returned no jobs matching current filters.")
        return FetchResult(jobs=jobs[:limit], warnings=warnings)

    def _build_query(self, search: SavedSearch) -> str:
        role_part = ", ".join(_normalised_roles(search) or search.target_roles) if search.target_roles else "software engineer"
        keyword_part = " ".join(_unique_terms(search.keywords)) if search.keywords else ""
        remote_part = " remote" if search.remote_only else ""
        query = f"{role_part} {keyword_part} jobs{remote_part}".strip()
        return re.sub(r"\s+", " ", query)

    def _build_query_variants(self, search: SavedSearch) -> list[QueryVariant]:
        roles = _normalised_roles(search) or _unique_terms(search.target_roles) or ["Software Engineer"]
        related_roles = _related_roles(roles)
        keywords = _unique_terms(search.keywords)
        skills = _unique_terms((search.required_skills + search.preferred_skills)[:4])
        locations = _normalised_locations(search)
        primary_location = locations[0] if locations else ""
        remote_part = " remote" if search.remote_only else ""

        query_parts = [
            ("exact", roles, keywords),
            ("normalized", roles, keywords + skills),
            ("related", related_roles or roles, keywords[:2] + skills[:2]),
            ("broad", ["Software Engineer"], keywords[:2] + skills[:2]),
        ]

        variants: list[QueryVariant] = []
        seen: set[tuple[str, str]] = set()
        for label, role_group, extra_terms in query_parts:
            role_part = " OR ".join(role_group[:3]) if role_group else "Software Engineer"
            extra_part = " ".join(extra_terms)
            query = re.sub(r"\s+", " ", f"{role_part} {extra_part} jobs{remote_part}".strip())
            location_options = [primary_location]
            if primary_location:
                location_options.append("")
            for location in location_options:
                key = (query.lower(), location.lower())
                if key in seen:
                    continue
                seen.add(key)
                variants.append(QueryVariant(query=query, location=location, label=label))
            if len(variants) >= 6:
                break

        return variants

    def _search_page(self, query: str, location: str, next_page_token: str | None) -> dict[str, object]:
        params: dict[str, str] = {
            "engine": "google_jobs",
            "api_key": self.api_key,
            "q": query,
            "hl": "en",
            "gl": "us",
        }
        if location:
            params["location"] = location
        if next_page_token:
            params["next_page_token"] = next_page_token

        req = request.Request(
            f"{self.endpoint}?{parse.urlencode(params)}",
            headers={"User-Agent": "AutonomousJobApplicationAgent/0.1"},
        )
        try:
            with request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise JobSourceError(f"SerpApi request failed: HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise JobSourceError(f"SerpApi request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise JobSourceError("SerpApi response was not valid JSON.") from exc

    def _parse_jobs(self, payload: dict[str, object]) -> list[JobPosting]:
        results = payload.get("jobs_results") or []
        if not isinstance(results, list):
            return []

        jobs: list[JobPosting] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            company = str(item.get("company_name") or "").strip()
            if not title or not company:
                continue

            description = _strip_html(
                str(item.get("description") or item.get("via") or f"{title} at {company}")
            )
            location = str(item.get("location") or "Remote").strip()
            apply_options = item.get("apply_options") if isinstance(item.get("apply_options"), list) else []
            first_apply = apply_options[0] if apply_options and isinstance(apply_options[0], dict) else {}
            url = str(first_apply.get("link") or item.get("share_link") or item.get("link") or "").strip() or None
            raw_job_id = str(item.get("job_id") or item.get("share_link") or f"{company}-{title}")
            job_id = f"serpapi-{parse.quote_plus(raw_job_id)}"

            skills = _infer_skills(f"{title} {description}")
            required = skills[:6]
            preferred = skills[6:10]

            jobs.append(
                JobPosting(
                    job_id=job_id,
                    title=title,
                    company=company,
                    description=description,
                    location=location,
                    source=self.source_name,
                    url=url,
                    required_skills=required,
                    preferred_skills=preferred,
                )
            )
        return jobs


class RemoteOKJobSource:
    source_name = "remoteok"
    endpoint = "https://remoteok.com/api"

    def fetch_jobs(self, search: SavedSearch, limit: int) -> FetchResult:
        req = request.Request(
            self.endpoint,
            headers={"User-Agent": "AutonomousJobApplicationAgent/0.1"},
        )
        try:
            with request.urlopen(req, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            raise JobSourceError(f"Failed to fetch RemoteOK jobs: {exc}") from exc

        raw_jobs = payload[1:] if isinstance(payload, list) else []
        candidates: list[JobPosting] = []

        for item in raw_jobs:
            job = self._to_job(item)
            if job is None:
                continue
            candidates.append(job)

        jobs, warnings = _rank_jobs_for_search(candidates, search, limit)
        if not jobs:
            warnings.append("RemoteOK returned no jobs matching current filters.")
        return FetchResult(jobs=jobs, warnings=warnings)

    def _to_job(self, item: dict[str, object]) -> JobPosting | None:
        title = str(item.get("position") or item.get("title") or "").strip()
        company = str(item.get("company") or "").strip()
        description = _strip_html(str(item.get("description") or "").strip())
        if not title or not company or not description:
            return None

        tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
        inferred = _infer_skills(description)
        combined = list(dict.fromkeys(tags + inferred))
        location = str(item.get("location") or "Remote").strip() or "Remote"
        job_id = str(item.get("id") or parse.quote_plus(f"{company}-{title}"))
        url = str(item.get("url") or item.get("apply_url") or "").strip() or None
        return JobPosting(
            job_id=f"remoteok-{job_id}",
            title=title,
            company=company,
            description=description,
            location=location,
            source=self.source_name,
            url=url,
            required_skills=combined[:6],
            preferred_skills=combined[6:10],
        )


class LinkedInJobSource:
    source_name = "linkedin"
    endpoint = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    card_pattern = re.compile(r"<li[^>]*class=\"[^\"]*base-card[^\"]*\"[^>]*>(.*?)</li>", re.DOTALL)

    def fetch_jobs(self, search: SavedSearch, limit: int) -> FetchResult:
        warnings: list[str] = []
        jobs: list[JobPosting] = []
        seen: set[str] = set()

        queries = self._build_queries(search)
        for keywords, location in queries:
            if len(jobs) >= limit:
                break
            start = 0
            while len(jobs) < limit and start < 75:
                page_jobs = self._fetch_page(search, keywords, location, start)
                if not page_jobs:
                    break
                for job in page_jobs:
                    key = f"{job.company.lower()}::{job.title.lower()}::{(job.location or '').lower()}"
                    if key in seen:
                        continue
                    seen.add(key)
                    jobs.append(job)
                    if len(jobs) >= limit:
                        break
                start += len(page_jobs)

        jobs, ranking_warnings = _rank_jobs_for_search(jobs, search, limit)
        warnings.extend(ranking_warnings)
        if not jobs:
            warnings.append("LinkedIn returned no jobs or blocked the guest search for current filters.")
        return FetchResult(jobs=jobs[:limit], warnings=warnings)

    def _build_queries(self, search: SavedSearch) -> list[tuple[str, str]]:
        roles = _normalised_roles(search) or search.target_roles or search.keywords or ["Software Engineer"]
        roles = _unique_terms(roles + _related_roles(roles) + ["Software Engineer"])[:5]
        locations = _normalised_locations(search) or (["Remote"] if search.remote_only else [""])
        if "" not in locations:
            locations.append("")
        return [(role.strip(), location.strip()) for role in roles for location in locations if role.strip()][:8]

    def _fetch_page(self, search: SavedSearch, keywords: str, location: str, start: int) -> list[JobPosting]:
        params = {"keywords": keywords, "location": location, "start": str(start)}
        req = request.Request(
            f"{self.endpoint}?{parse.urlencode(params)}",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        try:
            with request.urlopen(req, timeout=20) as response:
                payload = response.read().decode("utf-8", errors="ignore")
        except error.URLError as exc:
            raise JobSourceError(f"Failed to fetch LinkedIn jobs: {exc}") from exc

        cards = self.card_pattern.findall(payload)
        jobs: list[JobPosting] = []
        for card in cards:
            parsed = self._parse_card(card)
            if parsed is None:
                continue
            jobs.append(parsed)
        return jobs

    def _parse_card(self, card_html: str) -> JobPosting | None:
        url_match = re.search(r"href=\"([^\"]*linkedin\.com/jobs/view/[^\"]+)\"", card_html)
        title_match = re.search(r"base-search-card__title[^>]*>\s*(.*?)\s*<", card_html, re.DOTALL)
        company_match = re.search(
            r"base-search-card__subtitle[^>]*>.*?<a[^>]*>\s*(.*?)\s*</a>",
            card_html,
            re.DOTALL,
        )
        location_match = re.search(r"job-search-card__location[^>]*>\s*(.*?)\s*<", card_html, re.DOTALL)

        title = _strip_html(title_match.group(1)) if title_match else ""
        company = _strip_html(company_match.group(1)) if company_match else ""
        location = _strip_html(location_match.group(1)) if location_match else "Remote"
        url = url_match.group(1) if url_match else None
        if not title or not company:
            return None

        job_id_match = re.search(r"/jobs/view/(\d+)", url or "")
        job_id = f"linkedin-{job_id_match.group(1)}" if job_id_match else f"linkedin-{parse.quote_plus(company + '-' + title)}"
        description = f"LinkedIn job posting: {title} at {company}."
        inferred = _infer_skills(f"{title} {description}")
        required = inferred[:5] if inferred else ["Communication", "Problem Solving"]
        return JobPosting(
            job_id=job_id,
            title=title,
            company=company,
            description=description,
            location=location,
            source=self.source_name,
            url=url,
            required_skills=required,
            preferred_skills=inferred[5:8],
        )


class GreenhouseJobSource:
    source_name = "greenhouse"
    base_url = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    boards = [
        "airbnb",
        "coinbase",
        "stripe",
        "datadog",
        "cloudflare",
        "notion",
        "plaid",
        "doordash",
        "canva",
        "robinhood",
    ]

    def fetch_jobs(self, search: SavedSearch, limit: int) -> FetchResult:
        candidates: list[JobPosting] = []
        warnings: list[str] = []
        seen: set[str] = set()

        for board in self.boards:
            if len(candidates) >= max(limit * 4, limit):
                break
            try:
                board_jobs = self._fetch_board(board)
            except JobSourceError as error_message:
                warnings.append(str(error_message))
                continue

            for job in board_jobs:
                key = f"{job.company.lower()}::{job.title.lower()}::{(job.location or '').lower()}"
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(job)

        jobs, ranking_warnings = _rank_jobs_for_search(candidates, search, limit)
        warnings.extend(ranking_warnings)
        if not jobs:
            warnings.append("Greenhouse boards returned no jobs matching current filters.")
        return FetchResult(jobs=jobs[:limit], warnings=warnings)

    def _fetch_board(self, board: str) -> list[JobPosting]:
        req = request.Request(
            self.base_url.format(board=board),
            headers={"User-Agent": "AutonomousJobApplicationAgent/0.1"},
        )
        try:
            with request.urlopen(req, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise JobSourceError(f"Greenhouse board '{board}' unavailable: {exc.code}") from exc
        except error.URLError as exc:
            raise JobSourceError(f"Failed to fetch Greenhouse board '{board}': {exc}") from exc

        jobs: list[JobPosting] = []
        for item in payload.get("jobs", []):
            title = str(item.get("title") or "").strip()
            absolute_url = str(item.get("absolute_url") or "").strip()
            if not title:
                continue
            location = str((item.get("location") or {}).get("name") or "Remote").strip()
            content = _strip_html(str(item.get("content") or ""))
            company = board.replace("-", " ").title()
            inferred = _infer_skills(f"{title} {content}")
            jobs.append(
                JobPosting(
                    job_id=f"greenhouse-{item.get('id')}",
                    title=title,
                    company=company,
                    description=content or f"{title} role at {company}.",
                    location=location,
                    source=self.source_name,
                    url=absolute_url or None,
                    required_skills=inferred[:6],
                    preferred_skills=inferred[6:10],
                )
            )
        return jobs


class LeverJobSource:
    source_name = "lever"
    base_url = "https://api.lever.co/v0/postings/{company}?mode=json"
    companies = [
        "figma",
        "netlify",
        "sourcegraph",
        "asanacareers",
        "improbable",
        "discord",
        "scaleai",
        "robinhood",
    ]

    def fetch_jobs(self, search: SavedSearch, limit: int) -> FetchResult:
        candidates: list[JobPosting] = []
        warnings: list[str] = []
        seen: set[str] = set()

        for company in self.companies:
            if len(candidates) >= max(limit * 4, limit):
                break
            try:
                postings = self._fetch_company(company)
            except JobSourceError as error_message:
                warnings.append(str(error_message))
                continue

            for job in postings:
                key = f"{job.company.lower()}::{job.title.lower()}::{(job.location or '').lower()}"
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(job)

        jobs, ranking_warnings = _rank_jobs_for_search(candidates, search, limit)
        warnings.extend(ranking_warnings)
        if not jobs:
            warnings.append("Lever boards returned no jobs matching current filters.")
        return FetchResult(jobs=jobs[:limit], warnings=warnings)

    def _fetch_company(self, company: str) -> list[JobPosting]:
        req = request.Request(
            self.base_url.format(company=company),
            headers={"User-Agent": "AutonomousJobApplicationAgent/0.1"},
        )
        try:
            with request.urlopen(req, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise JobSourceError(f"Lever company '{company}' unavailable: {exc.code}") from exc
        except error.URLError as exc:
            raise JobSourceError(f"Failed to fetch Lever company '{company}': {exc}") from exc

        jobs: list[JobPosting] = []
        for item in payload:
            title = str(item.get("text") or "").strip()
            if not title:
                continue
            categories = item.get("categories") or {}
            location = str(categories.get("location") or "Remote").strip()
            description = _strip_html(str(item.get("descriptionPlain") or item.get("description") or ""))
            company_name = company.replace("-", " ").title()
            inferred = _infer_skills(f"{title} {description}")
            jobs.append(
                JobPosting(
                    job_id=f"lever-{item.get('id')}",
                    title=title,
                    company=company_name,
                    description=description or f"{title} role at {company_name}.",
                    location=location,
                    source=self.source_name,
                    url=str(item.get("hostedUrl") or "").strip() or None,
                    required_skills=inferred[:6],
                    preferred_skills=inferred[6:10],
                )
            )
        return jobs
