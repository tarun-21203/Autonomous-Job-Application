from typing import Literal

from pydantic import BaseModel, Field


RecommendationType = Literal["apply", "review", "skip"]
PriorityType = Literal["high", "medium", "low"]
SearchSourceType = Literal["mock", "remoteok", "linkedin", "greenhouse", "lever", "serpapi"]
ExecutionType = Literal["manual_browser", "email_draft", "api_stub"]
ExecutionStatus = Literal[
    "approval_required",
    "queued",
    "running",
    "completed",
    "failed",
    "canceled",
]
OrchestratorRunStatus = Literal["created", "running", "completed", "failed", "needs_review"]
OrchestratorStepStatus = Literal["pending", "running", "completed", "failed", "skipped"]
ApplicationStatus = Literal[
    "evaluated",
    "approved",
    "tailored",
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "skipped",
    "archived",
]


class JobPosting(BaseModel):
    job_id: str
    title: str
    company: str
    description: str
    location: str | None = None
    source: str = "manual"
    url: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    profile_id: str
    name: str | None = None
    resume_text: str
    target_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)


class ResumeUploadResponse(BaseModel):
    profile: CandidateProfile
    summary: str


class ResumeRecommendation(BaseModel):
    summary: str
    bullet_suggestions: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    evidence_used: list[str] = Field(default_factory=list)


class SkillRecommendation(BaseModel):
    skill: str
    priority: PriorityType
    reason: str


class JobEvaluation(BaseModel):
    application_id: str | None = None
    status: ApplicationStatus = "evaluated"
    job: JobPosting
    fit_score: float
    recommendation: RecommendationType
    rationale: list[str] = Field(default_factory=list)
    resume_recommendation: ResumeRecommendation
    skill_recommendations: list[SkillRecommendation] = Field(default_factory=list)
    duplicate: bool = False
    requires_human_review: bool = True


class JobEvaluationRequest(BaseModel):
    profile_id: str
    jobs: list[JobPosting]


class JobEvaluationResponse(BaseModel):
    profile_id: str
    evaluations: list[JobEvaluation]


class ApplicationRecord(BaseModel):
    application_id: str
    profile_id: str
    job: JobPosting
    recommendation: RecommendationType
    status: ApplicationStatus
    fit_score: float
    rationale: list[str] = Field(default_factory=list)
    resume_recommendation: ResumeRecommendation
    skill_recommendations: list[SkillRecommendation] = Field(default_factory=list)
    duplicate: bool = False
    requires_human_review: bool = True
    created_at: str
    updated_at: str


class ApplicationListResponse(BaseModel):
    profile_id: str
    applications: list[ApplicationRecord]


class ApplicationStatusUpdateRequest(BaseModel):
    status: ApplicationStatus
    note: str | None = None


class ApplicationStatusUpdateResponse(BaseModel):
    application: ApplicationRecord
    message: str


class SavedSearchBase(BaseModel):
    name: str
    keywords: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    remote_only: bool = False
    salary_min: int | None = None
    companies_include: list[str] = Field(default_factory=list)
    companies_exclude: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    sources: list[SearchSourceType] = Field(default_factory=lambda: ["mock"])


class SavedSearchCreateRequest(SavedSearchBase):
    profile_id: str


class SavedSearch(SavedSearchBase):
    search_id: str
    profile_id: str
    created_at: str
    updated_at: str


class SavedSearchListResponse(BaseModel):
    profile_id: str
    searches: list[SavedSearch]


class SearchRunRecord(BaseModel):
    run_id: str
    search_id: str
    sources: list[SearchSourceType] = Field(default_factory=list)
    fetched_count: int
    warnings: list[str] = Field(default_factory=list)
    created_at: str


class SearchRunRequest(BaseModel):
    evaluate_jobs: bool = True
    limit: int = Field(default=20, ge=1, le=100)


class SearchRunResponse(BaseModel):
    search: SavedSearch
    run: SearchRunRecord
    jobs: list[JobPosting] = Field(default_factory=list)
    evaluations: list[JobEvaluation] = Field(default_factory=list)


class FeedbackRoleInsight(BaseModel):
    role: str
    count: int


class FeedbackSkillInsight(BaseModel):
    skill: str
    count: int
    reason: str


class FeedbackSummary(BaseModel):
    profile_id: str
    total_applications: int
    status_counts: dict[str, int] = Field(default_factory=dict)
    successful_roles: list[FeedbackRoleInsight] = Field(default_factory=list)
    recurring_rejected_roles: list[FeedbackRoleInsight] = Field(default_factory=list)
    successful_skills: list[FeedbackSkillInsight] = Field(default_factory=list)
    recurring_missing_skills: list[FeedbackSkillInsight] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ExecutionTaskRequest(BaseModel):
    execution_type: ExecutionType
    dry_run: bool = True
    channel_target: str | None = None
    note: str | None = None


class ExecutionTaskRecord(BaseModel):
    task_id: str
    application_id: str
    profile_id: str
    execution_type: ExecutionType
    status: ExecutionStatus
    dry_run: bool = True
    human_approved: bool = False
    channel_target: str | None = None
    note: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    result: dict[str, object] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class ExecutionEventRecord(BaseModel):
    event_id: int
    task_id: str
    event_type: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)
    created_at: str


class ExecutionTaskResponse(BaseModel):
    task: ExecutionTaskRecord
    message: str


class ExecutionTaskListResponse(BaseModel):
    application_id: str
    tasks: list[ExecutionTaskRecord]


class ExecutionEventListResponse(BaseModel):
    task_id: str
    events: list[ExecutionEventRecord]


class ExecutionApprovalRequest(BaseModel):
    note: str | None = None


class ExecutionSubmissionConfirmationRequest(BaseModel):
    note: str | None = None


class ExecutionQueueProcessRequest(BaseModel):
    limit: int = Field(default=5, ge=1, le=50)


class ExecutionQueueProcessResponse(BaseModel):
    processed_count: int
    tasks: list[ExecutionTaskRecord] = Field(default_factory=list)
    message: str


class EvaluationMetric(BaseModel):
    name: str
    score: float
    reasoning: str


class EvaluationBundle(BaseModel):
    overall_confidence: float
    needs_human_review: bool = True
    summary: str
    reflection: str
    metrics: list[EvaluationMetric] = Field(default_factory=list)


class LearningResource(BaseModel):
    title: str
    provider: str
    resource_type: Literal["course", "project", "practice"] = "course"


class SkillRoadmapStep(BaseModel):
    focus_skill: str
    priority: PriorityType
    reason: str
    timeline_weeks: int
    resources: list[LearningResource] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)


class SkillRoadmap(BaseModel):
    summary: str
    steps: list[SkillRoadmapStep] = Field(default_factory=list)


class RankedJobInsight(BaseModel):
    job: JobPosting
    semantic_score: float
    fit_score: float | None = None
    combined_score: float
    reason: str


class SearchOverride(BaseModel):
    name: str = "Goal-derived search"
    keywords: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    remote_only: bool = False
    salary_min: int | None = None
    companies_include: list[str] = Field(default_factory=list)
    companies_exclude: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    sources: list[SearchSourceType] = Field(default_factory=lambda: ["mock"])


class OrchestratorRunRequest(BaseModel):
    profile_id: str
    goal: str
    search_id: str | None = None
    search_override: SearchOverride | None = None
    limit: int = Field(default=10, ge=1, le=50)


class OrchestratorStepRecord(BaseModel):
    step_id: str
    run_id: str
    name: str
    status: OrchestratorStepStatus
    input_payload: dict[str, object] = Field(default_factory=dict)
    output_payload: dict[str, object] = Field(default_factory=dict)
    reflection: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class OrchestratorRunRecord(BaseModel):
    run_id: str
    profile_id: str
    goal: str
    status: OrchestratorRunStatus
    plan: list[str] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    selected_job: JobPosting | None = None
    ranked_jobs: list[RankedJobInsight] = Field(default_factory=list)
    evaluations: list[JobEvaluation] = Field(default_factory=list)
    skill_roadmap: SkillRoadmap | None = None
    resume_recommendation: ResumeRecommendation | None = None
    evaluation_bundle: EvaluationBundle | None = None
    needs_human_review: bool = True
    created_at: str
    updated_at: str


class OrchestratorRunResponse(BaseModel):
    run: OrchestratorRunRecord
    steps: list[OrchestratorStepRecord] = Field(default_factory=list)


class OrchestratorRunListResponse(BaseModel):
    profile_id: str
    runs: list[OrchestratorRunRecord] = Field(default_factory=list)
