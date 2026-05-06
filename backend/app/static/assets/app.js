const state = {
  profileId: localStorage.getItem("aja_profile_id") || "",
  profile: null,
  runs: [],
  activeRun: null,
  selectedJobId: "",
  jobsDisplayCount: 10, // Track how many jobs to display
  totalJobsAvailable: 0, // Track total jobs
};

const nodes = {};

document.addEventListener("DOMContentLoaded", async () => {
  cacheNodes();
  bindEvents();
  renderAll();
  await checkHealth();
  await bootstrap();
});

function cacheNodes() {
  nodes.healthPill = document.getElementById("health-pill");
  nodes.profileChip = document.getElementById("profile-chip");
  nodes.resumeForm = document.getElementById("resume-form");
  nodes.targetForm = document.getElementById("target-form");
  nodes.targetSection = document.getElementById("target-section");
  nodes.profileSummary = document.getElementById("profile-summary");
  nodes.runHistory = document.getElementById("run-history");
  nodes.runOverview = document.getElementById("run-overview");
  nodes.warningPanel = document.getElementById("warning-panel");
  nodes.jobsList = document.getElementById("jobs-list");
  nodes.jobDetail = document.getElementById("job-detail");
  nodes.resumeInsights = document.getElementById("resume-insights");
  nodes.skillInsights = document.getElementById("skill-insights");
  nodes.toastStack = document.getElementById("toast-stack");
  nodes.inputPhase = document.getElementById("input-phase");
  nodes.resultsPhase = document.getElementById("results-phase");
  nodes.loadMoreBtn = document.getElementById("load-more-btn");
  nodes.jobsCount = document.getElementById("jobs-count");
  nodes.newSearchBtn = document.getElementById("new-search-btn");
  nodes.newResumeBtn = document.getElementById("new-resume-btn");
}

function bindEvents() {
  nodes.resumeForm.addEventListener("submit", handleResumeUpload);
  nodes.targetForm.addEventListener("submit", handleTargetSubmit);
  nodes.runHistory.addEventListener("click", handleHistoryClick);
  nodes.jobsList.addEventListener("click", handleJobSelection);
  nodes.loadMoreBtn?.addEventListener("click", handleLoadMore);
  nodes.newSearchBtn?.addEventListener("click", handleNewSearch);
  nodes.newResumeBtn?.addEventListener("click", handleNewResume);
}

async function bootstrap() {
  if (!state.profileId) {
    renderPhases();
    return;
  }

  try {
    await loadProfile();
    await loadRuns();
    renderPhases();
  } catch (error) {
    state.profileId = "";
    state.profile = null;
    state.runs = [];
    state.activeRun = null;
    state.selectedJobId = "";
    localStorage.removeItem("aja_profile_id");
    renderAll();
    renderPhases();
    showToast(error.message, "error");
  }
}

async function checkHealth() {
  try {
    const data = await apiFetch("/health");
    nodes.healthPill.textContent = `${data.app} online`;
    nodes.healthPill.className = "health-pill ok";
  } catch (error) {
    nodes.healthPill.textContent = "Backend unavailable";
    nodes.healthPill.className = "health-pill warning";
  }
}

async function loadProfile() {
  state.profile = await apiFetch(`/resumes/${encodeURIComponent(state.profileId)}`);
  prefillTargetForm();
  renderProfile();
}

async function loadRuns() {
  const data = await apiFetch(`/orchestrator/profiles/${encodeURIComponent(state.profileId)}/runs`);
  state.runs = data.runs || [];

  if (!state.runs.length) {
    state.activeRun = null;
    state.selectedJobId = "";
    state.jobsDisplayCount = 10;
    renderAll();
    return;
  }

  const activeRunId = state.activeRun?.run?.run_id;
  const nextRunId = state.runs.some((run) => run.run_id === activeRunId) ? activeRunId : state.runs[0].run_id;
  await loadRun(nextRunId);
}

async function loadRun(runId) {
  if (!runId) {
    state.activeRun = null;
    state.selectedJobId = "";
    state.jobsDisplayCount = 10;
    renderAll();
    return;
  }

  state.activeRun = await apiFetch(`/orchestrator/runs/${encodeURIComponent(runId)}`);
  state.jobsDisplayCount = 10;
  const displayedJobs = getDisplayedJobs();
  const selectedJobId = state.activeRun.run.selected_job?.job_id || displayedJobs[0]?.job.job_id || "";
  state.selectedJobId = selectedJobId;
  state.totalJobsAvailable = displayedJobs.length;
  renderAll();
}

async function handleResumeUpload(event) {
  event.preventDefault();
  const formData = new FormData(nodes.resumeForm);

  try {
    const response = await apiFetch("/resumes/upload", {
      method: "POST",
      body: formData,
    });

    state.profileId = response.profile.profile_id;
    state.profile = response.profile;
    state.runs = [];
    state.activeRun = null;
    state.selectedJobId = "";
    state.jobsDisplayCount = 10;
    localStorage.setItem("aja_profile_id", state.profileId);

    prefillTargetForm(true);
    renderAll();
    renderPhases();
    showToast("Resume uploaded! Now tell us about your target role.", "success");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function handleTargetSubmit(event) {
  event.preventDefault();

  if (!state.profileId) {
    showToast("Upload a resume first.", "info");
    return;
  }

  const formData = new FormData(nodes.targetForm);
  const targetPosition = String(formData.get("target_position") || "").trim();
  const targetRoles = [targetPosition, ...parseList(formData.get("target_roles"))].filter(Boolean);
  const workMode = String(formData.get("work_mode") || "flexible");
  const payload = {
    profile_id: state.profileId,
    goal: buildGoal(formData, targetRoles, workMode),
    limit: 10, // Always fetch top 10 initially
    search_override: {
      name: buildSearchName(formData),
      keywords: parseList(formData.get("keywords")),
      target_roles: targetRoles,
      locations: parseList(formData.get("locations")),
      remote_only: workMode === "remote",
      salary_min: parseInteger(formData.get("salary_min")),
      companies_include: parseList(formData.get("companies_include")),
      companies_exclude: [],
      required_skills: [], // Don't ask user for skills
      preferred_skills: [], // Don't ask user for skills
      sources: ["serpapi", "linkedin", "remoteok", "greenhouse", "lever"],
    },
  };

  try {
    showToast("Analyzing your profile and finding the best matches from top tech companies...", "info");
    const response = await apiFetch("/orchestrator/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    state.activeRun = response;
    state.jobsDisplayCount = 10;
    const displayedJobs = getDisplayedJobs();
    state.totalJobsAvailable = displayedJobs.length;
    state.selectedJobId = response.run.selected_job?.job_id || displayedJobs[0]?.job.job_id || "";
    showToast("Jobs analyzed successfully!", "success");
    renderAll();
    renderPhases();
    await loadRuns();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function handleHistoryClick(event) {
  const button = event.target.closest("[data-run-id]");
  if (!button) {
    return;
  }

  try {
    await loadRun(button.dataset.runId);
    renderPhases();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function handleJobSelection(event) {
  const button = event.target.closest("[data-job-id]");
  if (!button) {
    return;
  }

  state.selectedJobId = button.dataset.jobId;
  renderAll();
}

function handleLoadMore(event) {
  event.preventDefault();
  state.jobsDisplayCount += 10;
  renderJobs();
  renderLoadMoreButton();
}

function handleNewSearch() {
  if (!state.profileId) {
    showToast("Upload a resume first.", "info");
    return;
  }

  state.activeRun = null;
  state.selectedJobId = "";
  state.jobsDisplayCount = 10;
  nodes.targetForm.reset();
  prefillTargetForm(true);
  renderAll();
  renderPhases();
}

function handleNewResume() {
  state.profileId = "";
  state.profile = null;
  state.runs = [];
  state.activeRun = null;
  state.selectedJobId = "";
  state.jobsDisplayCount = 10;
  localStorage.removeItem("aja_profile_id");
  nodes.resumeForm.reset();
  nodes.targetForm.reset();
  renderAll();
  renderPhases();
}

function renderPhases() {
  // Show input phase only if no profile yet or no active run
  if (!state.profileId || !state.activeRun) {
    nodes.inputPhase.style.display = "block";
    nodes.resultsPhase.style.display = "none";
    nodes.targetSection.style.display = state.profileId ? "block" : "none";
  } else {
    nodes.inputPhase.style.display = "none";
    nodes.resultsPhase.style.display = "block";
  }
}

function renderAll() {
  renderProfile();
  renderRunHistory();
  renderOverview();
  renderWarnings();
  renderJobs();
  renderJobDetail();
  renderResumeInsights();
  renderSkillInsights();
  renderLoadMoreButton();
}

function renderProfile() {
  if (!state.profile) {
    nodes.profileChip.textContent = "No active profile";
    nodes.profileSummary.innerHTML = `
      <h3>Your Profile</h3>
      <p class="subtle">Upload a resume to get started</p>
    `;
    return;
  }

  nodes.profileChip.textContent = state.profile.name || state.profile.profile_id;
  const skills = (state.profile.skills || [])
    .slice(0, 8)
    .map((skill) => `<span class="tag">${escapeHtml(skill)}</span>`)
    .join("");
  const achievements = (state.profile.achievements || [])
    .slice(0, 3)
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");

  nodes.profileSummary.innerHTML = `
    <h3>${escapeHtml(state.profile.name || "Candidate Profile")}</h3>
    <div class="metric-strip">
      <div class="metric-box">
        <span class="metric-label">Skills</span>
        <strong>${(state.profile.skills || []).length}</strong>
      </div>
      <div class="metric-box">
        <span class="metric-label">Achievements</span>
        <strong>${(state.profile.achievements || []).length}</strong>
      </div>
    </div>
    ${skills ? `<div class="stack-block"><h4>Top Skills</h4><div class="tag-row">${skills}</div></div>` : ""}
    ${achievements ? `<div class="stack-block"><h4>Evidence</h4><ul class="bullet-list">${achievements}</ul></div>` : ""}
  `;
}

function renderRunHistory() {
  if (!state.runs.length) {
    nodes.runHistory.innerHTML = `
      <div class="empty-state" style="font-size: 0.9rem;">
        <h4>No past analyses yet</h4>
      </div>
    `;
    return;
  }

  nodes.runHistory.innerHTML = `<h3>Recent Analyses</h3>${state.runs
    .slice(0, 5)
    .map((run) => `
      <button
        class="history-item ${run.run_id === state.activeRun?.run?.run_id ? "is-active" : ""}"
        type="button"
        data-run-id="${escapeHtml(run.run_id)}"
      >
        <span class="history-title">${escapeHtml(run.goal.substring(0, 40))}</span>
        <span class="history-meta">${escapeHtml(formatDate(run.updated_at))}</span>
      </button>
    `)
    .join("")}`;
}

function renderOverview() {
  if (!state.activeRun) {
    nodes.runOverview.innerHTML = `
      <div class="empty-state">
        <h3>Ready to find your next role?</h3>
        <p>Upload your resume and describe your target job, then we'll analyze the market and show you the best opportunities.</p>
      </div>
    `;
    return;
  }

  const displayedJobs = getDisplayedJobs();
  const selected = getSelectedJobContext();
  const bundle = state.activeRun.run.evaluation_bundle;
  const metrics = bundle?.metrics || [];

  nodes.runOverview.innerHTML = `
    <div class="overview-grid">
      <div>
        <h2>${escapeHtml(state.activeRun.run.goal)}</h2>
        <p class="lead compact">
          ${escapeHtml(bundle?.summary || "Analysis complete. Here are your best matches.")}
        </p>
        <div class="status-row">
          <span class="status-pill ${state.activeRun.run.needs_human_review ? "review" : "apply"}">
            ${state.activeRun.run.needs_human_review ? "Review recommended" : "Ready to apply"}
          </span>
        </div>
      </div>
      <div class="metric-grid">
        <article class="metric-box strong">
          <span class="metric-label">Matching Roles</span>
          <strong>${displayedJobs.length}</strong>
        </article>
        <article class="metric-box strong">
          <span class="metric-label">Fit Confidence</span>
          <strong>${Math.round(bundle?.overall_confidence || 0)}%</strong>
        </article>
      </div>
    </div>
  `;
}

function renderWarnings() {
  if (!nodes.warningPanel) {
    return;
  }

  const warnings = getSearchWarnings();
  if (!warnings.length) {
    nodes.warningPanel.style.display = "none";
    nodes.warningPanel.innerHTML = "";
    return;
  }

  nodes.warningPanel.style.display = "block";
  nodes.warningPanel.innerHTML = `
    <h3>Search Notes</h3>
    <ul class="bullet-list">
      ${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}
    </ul>
  `;
}

function renderJobs() {
  if (!state.activeRun) {
    nodes.jobsList.innerHTML = `
      <div class="empty-state">
        <p>Submit your details to see matching jobs</p>
      </div>
    `;
    return;
  }

  const allJobs = getDisplayedJobs();
  const displayedItems = allJobs.slice(0, state.jobsDisplayCount);

  if (!displayedItems.length) {
    nodes.jobsList.innerHTML = `
      <div class="empty-state">
        <p>No jobs matched. Try adjusting your criteria.</p>
      </div>
    `;
    return;
  }

  nodes.jobsList.innerHTML = displayedItems
    .map((item, index) => {
      const evaluation = getEvaluationByJobId(item.job.job_id);
      const recommendation = evaluation?.recommendation || "review";
      const fitScore = Math.round(evaluation?.fit_score || item.fit_score || 0);
      const matchScore = Math.round(item.combined_score || 0);

      return `
        <button
          class="job-card ${item.job.job_id === state.selectedJobId ? "is-active" : ""}"
          type="button"
          data-job-id="${escapeHtml(item.job.job_id)}"
        >
          <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
            <span class="job-card-rank">#${index + 1}</span>
            <span style="display: inline-block; padding: 0.25rem 0.75rem; background: ${recommendation === 'apply' ? '#d1fae5' : '#fef3c7'}; color: ${recommendation === 'apply' ? '#10b981' : '#f59e0b'}; border-radius: 999px; font-size: 0.75rem; font-weight: 500;">
              ${escapeHtml(recommendation).charAt(0).toUpperCase() + escapeHtml(recommendation).slice(1)}
            </span>
          </div>
          <h4>${escapeHtml(item.job.title)}</h4>
          <div class="job-card-meta">${escapeHtml(item.job.company)} • ${escapeHtml(item.job.location || "Remote")}</div>
          <div class="job-scores">
            <div class="job-score-item">
              <div class="job-score-label">Fit Score</div>
              <div class="job-score-value">${fitScore}%</div>
            </div>
            <div class="job-score-item">
              <div class="job-score-label">Match</div>
              <div class="job-score-value">${matchScore}%</div>
            </div>
          </div>
          ${(item.job.required_skills || []).length > 0 ? `
            <div class="job-skills">
              ${(item.job.required_skills || []).slice(0, 3).map((skill) => `<span class="skill-tag">${escapeHtml(skill)}</span>`).join("")}
            </div>
          ` : ''}
        </button>
      `;
    })
    .join("");
}

function renderLoadMoreButton() {
  const allJobs = getDisplayedJobs();
  const shouldShow = state.jobsDisplayCount < allJobs.length;

  if (nodes.loadMoreBtn) {
    nodes.loadMoreBtn.style.display = shouldShow ? "block" : "none";
  }

  if (nodes.jobsCount) {
    nodes.jobsCount.textContent = `${state.jobsDisplayCount} of ${allJobs.length} jobs`;
  }
}

function renderJobDetail() {
  const selected = getSelectedJobContext();
  if (!selected) {
    nodes.jobDetail.innerHTML = `
      <div class="empty-state">
        <p>Select a job to see details and optimization tips</p>
      </div>
    `;
    return;
  }

  const evaluation = selected.evaluation;
  const job = selected.job;
  const recommendation = evaluation?.recommendation || "review";
  const fitScore = Math.round(evaluation?.fit_score || selected.fit_score || 0);
  const matchScore = Math.round(selected.semantic_score || 0);

  nodes.jobDetail.innerHTML = `
    <div class="job-detail-card">
      <h3 style="margin-bottom: 0.5rem;">${escapeHtml(job.title)}</h3>
      <p style="color: var(--text-secondary); margin-bottom: 1rem;">${escapeHtml(job.company)} • ${escapeHtml(job.location || "Remote")}</p>
      
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; padding: 1rem; background: var(--primary-soft); border-radius: var(--radius-lg); margin-bottom: 1.5rem;">
        <div style="text-align: center;">
          <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Fit Score</div>
          <div style="font-size: 1.75rem; font-weight: 700; color: var(--primary);">${fitScore}%</div>
        </div>
        <div style="text-align: center;">
          <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Match Relevance</div>
          <div style="font-size: 1.75rem; font-weight: 700; color: var(--primary);">${matchScore}%</div>
        </div>
      </div>

      ${job.required_skills?.length > 0 ? `
        <div class="job-detail-card">
          <h4>Required Skills</h4>
          <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
            ${(job.required_skills || []).map((skill) => `<span class="skill-tag">${escapeHtml(skill)}</span>`).join("")}
          </div>
        </div>
      ` : ""}

      ${job.preferred_skills?.length > 0 ? `
        <div class="job-detail-card">
          <h4>Nice to Have Skills</h4>
          <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
            ${(job.preferred_skills || []).map((skill) => `<span style="display: inline-block; padding: 0.25rem 0.75rem; background: var(--border-light); color: var(--text-secondary); border-radius: 999px; font-size: 0.75rem; font-weight: 500;">${escapeHtml(skill)}</span>`).join("")}
          </div>
        </div>
      ` : ""}

      ${job.description ? `
        <div class="job-detail-card">
          <h4>About the Role</h4>
          <p style="color: var(--text-secondary); line-height: 1.6;">${escapeHtml(job.description.substring(0, 600))}${job.description.length > 600 ? "..." : ""}</p>
        </div>
      ` : ""}

      ${job.url ? `<a class="btn btn-primary btn-full" href="${escapeHtml(job.url)}" target="_blank" rel="noreferrer" style="margin-top: 1rem;">View Full Job Posting →</a>` : ""}
    </div>
  `;
}

function renderResumeInsights() {
  const selected = getSelectedJobContext();
  const recommendation = selected?.evaluation?.resume_recommendation || state.activeRun?.run.resume_recommendation;

  if (!recommendation) {
    nodes.resumeInsights.innerHTML = `
      <div class="empty-state">
        <p>Select a job to get tailoring suggestions</p>
      </div>
    `;
    return;
  }

  const bulletSuggestions = (recommendation.bullet_suggestions || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  const missingKeywords = (recommendation.missing_keywords || [])
    .map((item) => `<span class="tag warn">${escapeHtml(item)}</span>`)
    .join("");

  nodes.resumeInsights.innerHTML = `
    <article class="summary-card">
      <h3>Optimize Your Resume</h3>
      <p>${escapeHtml(recommendation.summary || "Here's how to improve your resume for this role:")}</p>
      ${bulletSuggestions ? `
        <div class="stack-block">
          <h4>Key Bullets to Add</h4>
          <ul class="bullet-list">${bulletSuggestions}</ul>
        </div>
      ` : ""}
      ${missingKeywords ? `
        <div class="stack-block">
          <h4>Keywords to Highlight</h4>
          <div class="tag-row">${missingKeywords}</div>
        </div>
      ` : ""}
    </article>
  `;
}

function renderSkillInsights() {
  const selected = getSelectedJobContext();
  const jobSkills = selected?.evaluation?.skill_recommendations || [];
  const roadmap = state.activeRun?.run.skill_roadmap;

  if (!jobSkills.length && !roadmap?.steps?.length) {
    nodes.skillInsights.innerHTML = `
      <div class="empty-state">
        <p>Skill insights will appear here</p>
      </div>
    `;
    return;
  }

  const roadmapMarkup = roadmap?.steps?.length
    ? `
      <div class="stack-block">
        <h4>What to Learn</h4>
        ${roadmap.steps.map((step) => `
          <div class="skill-item">
            <strong>${escapeHtml(step.focus_skill)}</strong>
            <span class="status-pill ${escapeHtml(step.priority)}">${escapeHtml(step.priority)}</span>
            <p class="subtle">${escapeHtml(step.reason)}</p>
          </div>
        `).join("")}
      </div>
    `
    : "";

  nodes.skillInsights.innerHTML = `
    <article class="summary-card">
      <h3>Build Your Skills</h3>
      ${roadmapMarkup || "<p>No skill gaps identified.</p>"}
    </article>
  `;
}

function prefillTargetForm(force = false) {
  if (!state.profile) {
    return;
  }

  const targetRolesInput = nodes.targetForm.elements.namedItem("target_roles");
  const locationsInput = nodes.targetForm.elements.namedItem("locations");

  if (force || !String(targetRolesInput?.value || "").trim()) {
    if (targetRolesInput) {
      targetRolesInput.value = (state.profile.target_roles || []).join(", ");
    }
  }
  if (force || !String(locationsInput?.value || "").trim()) {
    if (locationsInput) {
      locationsInput.value = (state.profile.preferred_locations || []).join(", ");
    }
  }
}

function getDisplayedJobs() {
  if (!state.activeRun) {
    return [];
  }

  const rankedJobs = state.activeRun.run.ranked_jobs || [];
  if (rankedJobs.length) {
    return rankedJobs;
  }

  return [...(state.activeRun.run.evaluations || [])]
    .sort((left, right) => right.fit_score - left.fit_score)
    .map((evaluation) => ({
      job: evaluation.job,
      semantic_score: evaluation.fit_score,
      fit_score: evaluation.fit_score,
      combined_score: evaluation.fit_score,
      reason: "Matched based on your profile",
    }));
}

function getEvaluationByJobId(jobId) {
  return (state.activeRun?.run.evaluations || []).find((item) => item.job.job_id === jobId) || null;
}

function getSelectedJobContext() {
  const item = getDisplayedJobs().find((entry) => entry.job.job_id === state.selectedJobId) || getDisplayedJobs()[0];
  if (!item) {
    return null;
  }

  return {
    ...item,
    evaluation: getEvaluationByJobId(item.job.job_id),
  };
}

function getSearchWarnings() {
  const step = (state.activeRun?.steps || []).find((item) => item.name === "search_jobs");
  const warnings = step?.output_payload?.warnings;
  return Array.isArray(warnings) ? warnings : [];
}

function buildSearchName(formData) {
  const targetPosition = String(formData.get("target_position") || "").trim();
  const targetRoles = [targetPosition, ...parseList(formData.get("target_roles"))].filter(Boolean);
  if (targetRoles.length) {
    return `${targetRoles[0]} search`;
  }
  return "Goal-driven search";
}

function buildGoal(formData, targetRoles, workMode) {
  const parts = [];
  if (targetRoles.length) {
    parts.push(`Target role: ${targetRoles[0]}.`);
  }
  const years = String(formData.get("years_experience") || "").trim();
  if (years) {
    parts.push(`Experience: ${years} years.`);
  }
  const locations = parseList(formData.get("locations"));
  if (locations.length) {
    parts.push(`Preferred locations: ${locations.join(", ")}.`);
  }
  if (workMode && workMode !== "flexible") {
    parts.push(`Work mode: ${workMode}.`);
  }
  const keywords = parseList(formData.get("keywords"));
  if (keywords.length) {
    parts.push(`Keywords: ${keywords.join(", ")}.`);
  }
  const context = String(formData.get("goal") || "").trim();
  if (context) {
    parts.push(context);
  }
  return parts.join(" ") || "Find the best matching open jobs for this candidate.";
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, options);
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const detail = typeof data === "object" && data !== null ? data.detail : data;
    throw new Error(detail || `Request failed with status ${response.status}.`);
  }

  return data;
}

function parseList(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseInteger(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) {
    return null;
  }

  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatDate(value) {
  try {
    return new Date(value).toLocaleDateString();
  } catch (error) {
    return String(value || "");
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function showToast(message, kind = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${kind}`;
  toast.textContent = message;
  nodes.toastStack.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}
