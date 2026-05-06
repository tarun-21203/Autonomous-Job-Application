from __future__ import annotations

import hashlib
import json
from pathlib import Path

try:
    import numpy as np
except ImportError:  # pragma: no cover - exercised only when dependency is missing at runtime
    np = None

from backend.app.schemas.domain import JobPosting, RankedJobInsight

try:
    import faiss
except ImportError:  # pragma: no cover - exercised only when dependency is missing at runtime
    faiss = None


class VectorMemoryUnavailableError(RuntimeError):
    pass


class HashedEmbedder:
    def __init__(self, dimension: int = 256) -> None:
        self.dimension = dimension

    def embed(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimension, dtype="float32")
        tokens = [token.strip().lower() for token in text.split() if token.strip()]
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            slot = int.from_bytes(digest[:4], "little") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[slot] += sign

        norm = np.linalg.norm(vector)
        return vector if norm == 0 else vector / norm


class FaissVectorMemory:
    def __init__(self, base_dir: str | Path = "data/faiss", dimension: int = 256) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.dimension = dimension
        self.embedder = HashedEmbedder(dimension=dimension)
        if faiss is None or np is None:
            raise VectorMemoryUnavailableError(
                "FAISS or NumPy is not installed. Add 'faiss-cpu' and 'numpy' to enable semantic memory."
            )

    def index_jobs(self, profile_id: str, jobs: list[JobPosting]) -> None:
        vectors = [self.embedder.embed(self._job_text(job)) for job in jobs]
        if not vectors:
            return

        index = faiss.IndexFlatIP(self.dimension)
        matrix = np.vstack(vectors).astype("float32")
        index.add(matrix)

        faiss.write_index(index, str(self._index_path(profile_id)))
        self._metadata_path(profile_id).write_text(
            json.dumps([job.model_dump() for job in jobs], indent=2),
            encoding="utf-8",
        )

    def rank_jobs(
        self,
        profile_id: str,
        query: str,
        job_fit_scores: dict[str, float] | None = None,
        limit: int = 5,
    ) -> list[RankedJobInsight]:
        job_fit_scores = job_fit_scores or {}
        index_path = self._index_path(profile_id)
        metadata_path = self._metadata_path(profile_id)
        if not index_path.exists() or not metadata_path.exists():
            return []

        index = faiss.read_index(str(index_path))
        jobs = [JobPosting.model_validate(item) for item in json.loads(metadata_path.read_text(encoding="utf-8"))]
        query_vector = self.embedder.embed(query).reshape(1, -1).astype("float32")
        distances, indices = index.search(query_vector, min(limit, len(jobs)))

        ranked: list[RankedJobInsight] = []
        for score, idx in zip(distances[0], indices[0], strict=False):
            if idx < 0 or idx >= len(jobs):
                continue
            job = jobs[idx]
            fit_score = job_fit_scores.get(job.job_id)
            combined = (float(score) * 100 * 0.45) + ((fit_score or 0.0) * 0.55)
            ranked.append(
                RankedJobInsight(
                    job=job,
                    semantic_score=round(float(score) * 100, 2),
                    fit_score=fit_score,
                    combined_score=round(combined, 2),
                    reason=(
                        "Ranked with hashed semantic similarity over the goal text and combined with current fit score."
                    ),
                )
            )
        return ranked

    def _job_text(self, job: JobPosting) -> str:
        return " ".join(
            [
                job.title,
                job.company,
                job.description,
                " ".join(job.required_skills),
                " ".join(job.preferred_skills),
                job.location or "",
            ]
        )

    def _index_path(self, profile_id: str) -> Path:
        return self.base_dir / f"{profile_id}.index"

    def _metadata_path(self, profile_id: str) -> Path:
        return self.base_dir / f"{profile_id}.json"
