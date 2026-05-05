from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3


SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    profile_id TEXT PRIMARY KEY,
    name TEXT,
    resume_text TEXT NOT NULL,
    target_roles_json TEXT NOT NULL,
    preferred_locations_json TEXT NOT NULL,
    skills_json TEXT NOT NULL,
    achievements_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    fingerprint TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    description TEXT NOT NULL,
    location TEXT,
    source TEXT NOT NULL,
    url TEXT,
    required_skills_json TEXT NOT NULL,
    preferred_skills_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
    application_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    job_fingerprint TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    status TEXT NOT NULL,
    fit_score REAL NOT NULL,
    rationale_json TEXT NOT NULL,
    resume_recommendation_json TEXT NOT NULL,
    skill_recommendations_json TEXT NOT NULL,
    duplicate INTEGER NOT NULL,
    requires_human_review INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(profile_id, job_fingerprint),
    FOREIGN KEY(profile_id) REFERENCES profiles(profile_id),
    FOREIGN KEY(job_fingerprint) REFERENCES jobs(fingerprint)
);

CREATE TABLE IF NOT EXISTS application_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(application_id) REFERENCES applications(application_id)
);

CREATE TABLE IF NOT EXISTS saved_searches (
    search_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    name TEXT NOT NULL,
    keywords_json TEXT NOT NULL,
    target_roles_json TEXT NOT NULL,
    locations_json TEXT NOT NULL,
    remote_only INTEGER NOT NULL,
    salary_min INTEGER,
    companies_include_json TEXT NOT NULL,
    companies_exclude_json TEXT NOT NULL,
    required_skills_json TEXT NOT NULL,
    preferred_skills_json TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(profile_id) REFERENCES profiles(profile_id)
);

CREATE TABLE IF NOT EXISTS search_runs (
    run_id TEXT PRIMARY KEY,
    search_id TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    fetched_count INTEGER NOT NULL,
    warnings_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(search_id) REFERENCES saved_searches(search_id)
);

CREATE TABLE IF NOT EXISTS execution_tasks (
    task_id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    execution_type TEXT NOT NULL,
    status TEXT NOT NULL,
    dry_run INTEGER NOT NULL,
    human_approved INTEGER NOT NULL,
    channel_target TEXT,
    note TEXT,
    payload_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(application_id) REFERENCES applications(application_id),
    FOREIGN KEY(profile_id) REFERENCES profiles(profile_id)
);

CREATE TABLE IF NOT EXISTS execution_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES execution_tasks(task_id)
);

CREATE TABLE IF NOT EXISTS orchestrator_runs (
    run_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    goal TEXT NOT NULL,
    status TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    observations_json TEXT NOT NULL,
    selected_job_json TEXT,
    ranked_jobs_json TEXT NOT NULL,
    evaluations_json TEXT NOT NULL,
    skill_roadmap_json TEXT,
    resume_recommendation_json TEXT,
    evaluation_bundle_json TEXT,
    needs_human_review INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(profile_id) REFERENCES profiles(profile_id)
);

CREATE TABLE IF NOT EXISTS orchestrator_steps (
    step_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    input_payload_json TEXT NOT NULL,
    output_payload_json TEXT NOT NULL,
    reflection TEXT,
    started_at TEXT,
    completed_at TEXT,
    FOREIGN KEY(run_id) REFERENCES orchestrator_runs(run_id)
);
"""


def initialize_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()


@contextmanager
def get_connection(database_path: Path):
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
