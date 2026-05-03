# Autonomous Job Application Agent with Human-in-the-Loop

## Introduction

The Autonomous Job Application Agent is an intelligent platform that helps job seekers discover, evaluate, and apply to roles with human oversight. Built with **FastAPI**, lightweight agent modules, and optional semantic memory (FAISS), the system automates research, scoring, and resume-tailoring while requiring human approval before any external submission.

## Background

Job search is noisy and time-consuming. Applicants often face repetitive research, poor matching, and manual tailoring of documents. This project combines deterministic agents, retrieval-augmented evidence, and semantic ranking to speed up discovery and increase application quality — while keeping a human in control of final actions.

## Key Features

### Core Application

- **Resume Upload & Parsing** – Accepts common resume formats and extracts achievements and skills for downstream scoring.
- **Job Research & Normalization** – `ResearchAgent` normalizes job postings from pluggable sources for consistent scoring.
- **Scoring Workflow** – `ScoringAgent` ranks and classifies jobs (e.g., `apply`, `review`, `skip`) with transparent rationale.
- **Resume Tailoring** – `WritingAgent` and `ResumeCoachAgent` suggest role-specific resume lines and cover-letter guidance.
- **Human-in-the-Loop Orchestration** – `SupervisorAgent` enforces approval checkpoints before irreversible steps.
- **Safe Execution Queue** – Controlled execution modes (dry-run stubs) plus explicit confirmation prevent accidental submission.
- **Persistence** – Default SQLite persistence for profiles, jobs, search runs and audit history.

### AI-Powered Enhancements

- **Semantic Ranking (FAISS)** – Per-profile FAISS indexes enable semantic job matching when enabled.
- **Hashed Embedder** – Lightweight deterministic embedder for offline or dependency-light setups.
- **RAG Evidence Retrieval** – Extracts resume evidence lines that overlap job requirements to justify recommendations.
- **Hybrid Ranking** – Combines semantic similarity and fit scores to produce better, explainable results.

## Implementation

### 1. Evidence-based Retrieval (RAG)

- The `rag_service` identifies candidate resume lines that overlap required and preferred skills from the job posting. This yields concise evidence used by agents to craft targeted resume bullets and explanations.

### 2. Semantic Ranking (FAISS + Hashed Embedder)

- The project ships a `HashedEmbedder` and a `FaissVectorMemory` wrapper. Jobs are indexed per-profile and queries are ranked semantically. When available, FAISS + NumPy provide fast nearest-neighbor lookup.

### 3. Hybrid Recommendation & Scoring

- Recommendations combine semantic similarity with explicit fit scores (derived from matching skills and role signals). This hybrid approach reduces cold-start issues and keeps recommendations interpretable.

## Getting Started

### Prerequisites

- **Python** 3.11+
- **pip** (or similar installer)
- Optional: **faiss-cpu** and **numpy** for semantic memory

### Environment Setup

1. Create and activate a virtual environment:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
# or install the package in editable mode
pip install -e .
```

3. (Optional) Create a `.env` file for configuration:

```env
SERPAPI_API_KEY=your_serpapi_key_here
DATABASE_PATH=data/agent.db
# add any other provider keys or overrides
```

### Running the Application

Start the FastAPI server (development):

```bash
uvicorn backend.app.main:app --reload --port 8000
```

Open the UI served from the backend at:

- `http://127.0.0.1:8000/`

Health endpoint:

- `GET /health`

API groups (prefixes):

- `/resumes` – resume upload and profile management
- `/jobs` – job ingestion and metadata
- `/searches` – saved searches and runs
- `/applications` – application records and transitions
- `/executions` – execution tasks and approvals
- `/feedback` – aggregated feedback summaries
- `/orchestrator` – orchestrator runs and audit history

## Technology Stack

### Backend

- **Python 3.11+** – language
- **FastAPI** – web framework
- **Uvicorn** – ASGI server
- **Pydantic** – data models
- **SQLite** (default) – simple persistence

### Semantic & ML

- **FAISS** (optional) – semantic indexing (`faiss-cpu`)
- **NumPy** – numerical routines
- **pypdf** – optional PDF parsing support

### Frontend

- **Static UI** – minimal static dashboard served from `backend/app/static`

## System Architecture

```
┌─────────────────┐    ┌────────────────────────┐    ┌─────────────────┐
│   Frontend      │    │      Backend/API       │    │   Persistence   │
│ (static UI)     │◄──►│  FastAPI + Agents      │◄──►│  SQLite + FAISS  │
│ index.html      │    │  RAG / Vector Memory   │    │  (data/faiss/)   │
└─────────────────┘    └────────────────────────┘    └─────────────────┘
```

## Project Structure

```
Agentic AI/
├── backend/
│   ├── app/
│   │   ├── agents/          # Research, Scoring, Writing, Supervisor agents
│   │   ├── api/             # FastAPI routes
│   │   ├── services/        # RAG, vector memory, orchestration, parsing
│   │   ├── core/            # config and settings
│   │   └── static/          # lightweight frontend (index.html)
├── data/                   # FAISS indexes, sqlite DB (data/agent.db)
├── tests/                  # unit tests
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Running Tests

```bash
python -m unittest discover -s tests
```

## Contributing

- File bugs or feature requests as issues.
- Send focused PRs with tests and clear descriptions.

## Notes & Roadmap

- Execution handlers are safe stubs by default — no silent submissions.
- Future improvements: provider-backed embeddings, Postgres + pgvector, richer job-source integrations, and a polished review dashboard.

---

Agentic AI — help job seekers find better fits, faster, with clear human oversight.
