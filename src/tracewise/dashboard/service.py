"""TraceWise Dashboard Service Layer.

Provides project ingestion caching, multi-baseline retrieval execution,
checkpoint loading, and ground-truth link reconciliation.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tracewise.evaluation.adapters import ProjectIngestionAdapter
from tracewise.evaluation.manifest import BenchmarkProjectManifest
from tracewise.evaluation.project import BenchmarkProject
from tracewise.preprocessing.models import ProcessedText
from tracewise.retrieval.base import BaseRetriever
from tracewise.retrieval.bm25 import BM25Retriever
from tracewise.retrieval.hybrid import HybridRetriever
from tracewise.retrieval.semantic import SemanticRetriever
from tracewise.retrieval.structural import StructuralRetriever
from tracewise.retrieval.tfidf import TfidfRetriever

logger = logging.getLogger(__name__)

DEFAULT_MANIFEST_PATHS: dict[str, Path] = {
    "sample_project": Path("data/fixtures/sample_project/benchmark_manifest.json"),
    "itrust": Path("data/benchmarks/itrust/benchmark_manifest.json"),
    "etour": Path("data/benchmarks/etour/benchmark_manifest.json"),
}

DEFAULT_CHECKPOINT_DIR = Path("experiments/results")

RETRIEVAL_METHODS_CATALOG: list[dict[str, Any]] = [
    {
        "id": "b0_tfidf",
        "name": "B0: TF-IDF",
        "description": "Unigram TF-IDF lexical baseline (Vector Space Model)",
        "family": "Lexical",
        "baseline_code": "B0",
        "parameters": {"lowercase": True, "token_pattern": r"(?u)\b\w+\b"},
    },
    {
        "id": "b1_bm25",
        "name": "B1: BM25",
        "description": "Okapi BM25 lexical ranking with doc-length normalization",
        "family": "Lexical",
        "baseline_code": "B1",
        "parameters": {"k1": 1.5, "b": 0.75},
    },
    {
        "id": "b2_semantic",
        "name": "B2: Dense Semantic",
        "description": "Dense vector retrieval using fastembed (bge-small-en-v1.5)",
        "family": "Dense Semantic",
        "baseline_code": "B2",
        "parameters": {"model": "BAAI/bge-small-en-v1.5"},
    },
    {
        "id": "b3_structural",
        "name": "B3: Structural",
        "description": "AST-aware structural code retrieval (lexical + call-graph)",
        "family": "Structural",
        "baseline_code": "B3",
        "parameters": {"alpha": 0.5},
    },
    {
        "id": "b4_hybrid",
        "name": "B4: Hybrid RRF",
        "description": "Reciprocal Rank Fusion uniting BM25 and dense semantic search",
        "family": "Hybrid",
        "baseline_code": "B4",
        "parameters": {"rrf_k": 60},
    },
    {
        "id": "b5_llm_rerank",
        "name": "B5: LLM Reranking",
        "description": "Retrieve-then-rerank: BM25 top-20 reranked with qwen3.5:9b",
        "family": "LLM Reranking",
        "baseline_code": "B5",
        "parameters": {
            "backend": "Ollama",
            "model": "qwen3.5:9b",
            "temperature": 0,
            "candidate_k": 20,
        },
    },
]


def extract_title_from_requirement(text: str, fallback_id: str) -> str:
    """Extract a concise human-readable title from requirement specification text."""
    if not text:
        return fallback_id

    # Pattern 1: Markdown title sections, e.g. "## Title\n\nUser Authentication..."
    title_match = re.search(r"##\s*Title\s*\n+([^\n#]+)", text, re.IGNORECASE)
    if title_match:
        extracted = title_match.group(1).strip()
        if extracted:
            return extracted

    # Pattern 2: "Use case name: DeleteCulturalHeritage" or similar
    uc_match = re.search(r"Use\s*case\s*name\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if uc_match:
        extracted = uc_match.group(1).strip()
        if extracted:
            return extracted

    # Pattern 3: First non-empty line stripped of markdown headers
    for line in text.splitlines():
        cleaned = re.sub(r"^#+\s*", "", line).strip()
        if cleaned:
            # If the first line is simply the ID itself, continue looking
            if cleaned.upper() == fallback_id.upper() or cleaned.startswith(
                f"{fallback_id} "
            ):
                continue
            return cleaned[:90] + ("..." if len(cleaned) > 90 else "")

    return fallback_id


class TraceWiseService:
    """Service provider connecting the retrieval engine to presentation layers.

    Caches loaded benchmark projects, indexed retrievers, and precomputed
    B5 LLM benchmark checkpoints for low-latency interactive querying.
    """

    def __init__(
        self,
        manifest_paths: dict[str, Path | str] | None = None,
        checkpoint_dir: Path | str | None = None,
    ) -> None:
        """Initialize the service with project manifests and checkpoint directory."""
        self.manifest_paths: dict[str, Path] = {
            k: Path(v) for k, v in (manifest_paths or DEFAULT_MANIFEST_PATHS).items()
        }
        self.checkpoint_dir = Path(checkpoint_dir or DEFAULT_CHECKPOINT_DIR)

        # In-memory caches
        self._projects: dict[str, BenchmarkProject] = {}
        self._requirement_maps: dict[str, dict[str, ProcessedText]] = {}
        self._source_maps: dict[str, dict[str, ProcessedText]] = {}
        self._retriever_cache: dict[tuple[str, str], BaseRetriever] = {}
        self._checkpoint_cache: dict[str, dict[str, Any]] = {}

    def get_supported_methods(self) -> list[dict[str, Any]]:
        """Return metadata for all supported retrieval and reranking methods."""
        return RETRIEVAL_METHODS_CATALOG

    def get_projects(self) -> list[dict[str, Any]]:
        """List all available benchmark projects with overview metrics."""
        projects_summary = []
        for project_id, manifest_path in self.manifest_paths.items():
            if not manifest_path.is_file():
                continue

            project = self.get_project_instance(project_id)
            checkpoint_file = self.checkpoint_dir / f"b5_checkpoint_{project_id}.json"

            projects_summary.append(
                {
                    "project_id": project.project_id,
                    "project_name": project.project_name,
                    "num_requirements": project.num_requirements,
                    "num_source_chunks": project.num_source_chunks,
                    "num_source_files": project.num_source_files,
                    "num_ground_truth_links": project.num_ground_truth_links,
                    "has_b5_checkpoint": checkpoint_file.is_file(),
                }
            )
        return projects_summary

    def get_project_instance(self, project_id: str) -> BenchmarkProject:
        """Retrieve or lazily ingest a BenchmarkProject instance."""
        if project_id not in self._projects:
            if project_id not in self.manifest_paths:
                avail = list(self.manifest_paths.keys())
                raise KeyError(f"Project '{project_id}' not found. Available: {avail}")
            manifest_path = self.manifest_paths[project_id]
            if not manifest_path.is_file():
                raise FileNotFoundError(
                    f"Manifest file missing for project '{project_id}': {manifest_path}"
                )

            manifest = BenchmarkProjectManifest.from_file(manifest_path)
            project = ProjectIngestionAdapter().ingest_project(manifest, validate=True)
            self._projects[project_id] = project

            # Build fast lookup maps
            self._requirement_maps[project_id] = {
                req.source_id: req for req in project.requirements
            }
            self._source_maps[project_id] = {
                chunk.source_id: chunk for chunk in project.source_artifacts
            }

        return self._projects[project_id]

    def get_project_details(self, project_id: str) -> dict[str, Any]:
        """Get comprehensive metadata and configuration for a specific project."""
        project = self.get_project_instance(project_id)
        checkpoint_file = self.checkpoint_dir / f"b5_checkpoint_{project_id}.json"
        evaluable_reqs = sum(
            1 for targets in project.ground_truth.values() if len(targets) > 0
        )

        return {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "num_requirements": project.num_requirements,
            "num_evaluable_requirements": evaluable_reqs,
            "num_zero_link_requirements": project.num_requirements - evaluable_reqs,
            "num_source_chunks": project.num_source_chunks,
            "num_source_files": project.num_source_files,
            "num_ground_truth_links": project.num_ground_truth_links,
            "metadata": project.metadata,
            "configuration": project.configuration,
            "has_b5_checkpoint": checkpoint_file.is_file(),
        }

    def get_requirements(
        self, project_id: str, mode: str = "evaluation"
    ) -> list[dict[str, Any]]:
        """List all requirements for a project with summaries and link counts.

        In developer mode, ground-truth link counts and evaluable status are
        strictly hidden to isolate benchmark labels from participant workflows.
        """
        norm_mode = self._normalize_mode(mode)
        project = self.get_project_instance(project_id)
        results = []

        for req in project.requirements:
            gold_links = project.ground_truth.get(req.source_id, set())
            is_dev = norm_mode == "developer"
            results.append(
                {
                    "requirement_id": req.source_id,
                    "title": extract_title_from_requirement(
                        req.original_text, req.source_id
                    ),
                    "char_count": len(req.original_text),
                    "tokens_count": len(req.tokens),
                    "gold_link_count": None if is_dev else len(gold_links),
                    "is_evaluable": None if is_dev else (len(gold_links) > 0),
                }
            )
        return results

    def get_requirement_detail(
        self, project_id: str, requirement_id: str, mode: str = "evaluation"
    ) -> dict[str, Any]:
        """Fetch specification text, ground truth links, and metadata.

        In developer mode, ground-truth links are withheld from the response.
        """
        norm_mode = self._normalize_mode(mode)
        project = self.get_project_instance(project_id)
        req_map = self._requirement_maps[project_id]

        if requirement_id not in req_map:
            raise KeyError(
                f"Requirement '{requirement_id}' not found in project '{project_id}'."
            )

        req = req_map[requirement_id]
        gold_links = sorted(list(project.ground_truth.get(requirement_id, set())))
        is_dev = norm_mode == "developer"

        return {
            "project_id": project_id,
            "requirement_id": req.source_id,
            "mode": norm_mode,
            "title": extract_title_from_requirement(req.original_text, req.source_id),
            "text": req.original_text,
            "normalized_text": req.normalized_text,
            "tokens": req.tokens,
            "tokens_count": len(req.tokens),
            "char_count": len(req.original_text),
            "gold_links": None if is_dev else gold_links,
            "gold_link_count": None if is_dev else len(gold_links),
            "is_evaluable": None if is_dev else (len(gold_links) > 0),
            "metadata": req.metadata,
        }

    def _get_or_create_retriever(
        self, project_id: str, method_id: str, source_chunks: Sequence[ProcessedText]
    ) -> BaseRetriever:
        """Instantiate and index a retriever instance for project and method."""
        key = (project_id, method_id)
        if key in self._retriever_cache:
            return self._retriever_cache[key]

        retriever: BaseRetriever
        if method_id == "b0_tfidf":
            retriever = TfidfRetriever()
        elif method_id == "b1_bm25":
            retriever = BM25Retriever(k1=1.5, b=0.75)
        elif method_id == "b2_semantic":
            retriever = SemanticRetriever()
        elif method_id == "b3_structural":
            retriever = StructuralRetriever(alpha=0.5)
        elif method_id == "b4_hybrid":
            retriever = HybridRetriever(k=60)
        else:
            raise ValueError(
                f"Unknown retrieval method '{method_id}'. Supported live methods: "
                "b0_tfidf, b1_bm25, b2_semantic, b3_structural, b4_hybrid."
            )

        retriever.index(source_chunks)
        self._retriever_cache[key] = retriever
        return retriever

    def _load_b5_checkpoint(self, project_id: str) -> dict[str, Any] | None:
        """Load and cache precomputed B5 benchmark checkpoint for a project."""
        if project_id in self._checkpoint_cache:
            return self._checkpoint_cache[project_id]

        checkpoint_path = self.checkpoint_dir / f"b5_checkpoint_{project_id}.json"
        if not checkpoint_path.is_file():
            return None

        try:
            with open(checkpoint_path, encoding="utf-8") as f:
                data = json.load(f)
            self._checkpoint_cache[project_id] = data
            return data
        except Exception as exc:
            logger.warning(
                "Failed to parse B5 checkpoint file at %s: %s", checkpoint_path, exc
            )
            return None

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        """Normalize and validate operating mode (evaluation vs. developer)."""
        clean = (mode or "").lower().strip()
        if clean in ("evaluation", "research", "eval"):
            return "evaluation"
        if clean in ("developer", "workflow", "dev"):
            return "developer"
        raise ValueError(
            f"Invalid mode '{mode}'. Supported: 'evaluation' or 'developer'."
        )

    def get_candidates(
        self,
        project_id: str,
        requirement_id: str,
        method: str = "b1_bm25",
        top_k: int = 20,
        mode: str = "evaluation",
    ) -> dict[str, Any]:
        """Retrieve ranked source candidates with ground-truth isolation.

        In developer mode, benchmark labels, ground-truth targets, and match
        indicators are withheld from the response to prevent evaluation leakage.
        """
        if top_k <= 0:
            raise ValueError(f"top_k must be a positive integer, got {top_k}")

        norm_mode = self._normalize_mode(mode)
        is_dev = norm_mode == "developer"
        project = self.get_project_instance(project_id)
        req_map = self._requirement_maps[project_id]
        source_map = self._source_maps[project_id]

        if requirement_id not in req_map:
            raise KeyError(
                f"Requirement '{requirement_id}' not found in project '{project_id}'."
            )

        req = req_map[requirement_id]
        gold_links = project.ground_truth.get(requirement_id, set())

        raw_candidates: list[dict[str, Any]] = []
        is_cached = False
        retrieval_time_sec = 0.0

        if method == "b5_llm_rerank":
            checkpoint_data = self._load_b5_checkpoint(project_id)
            if checkpoint_data and requirement_id in checkpoint_data:
                entry = checkpoint_data[requirement_id]
                b5_cands = entry.get("b5_candidates", [])
                retrieval_time_sec = entry.get("llm_time_sec", 0.0)
                is_cached = True

                for cand in b5_cands[:top_k]:
                    raw_candidates.append(
                        {
                            "rank": cand.get("rank"),
                            "target_id": cand.get("target_id"),
                            "score": cand.get("score"),
                            "retriever_name": "b5_llm_rerank",
                            "metadata": cand.get("metadata", {}),
                        }
                    )
            else:
                # If checkpoint missing, fall back to live B5 if possible
                from tracewise.b5.reranker import B5RerankRetriever

                bm25 = BM25Retriever(k1=1.5, b=0.75)
                bm25.index(project.source_artifacts)
                b5 = B5RerankRetriever(candidate_retriever=bm25, candidate_k=20)
                b5.index(project.source_artifacts)

                t0 = time.perf_counter()
                live_candidates = b5.retrieve(req, top_k=top_k)
                retrieval_time_sec = time.perf_counter() - t0

                for cand in live_candidates:
                    raw_candidates.append(
                        {
                            "rank": cand.rank,
                            "target_id": cand.target_id,
                            "score": cand.score,
                            "retriever_name": cand.retriever_name,
                            "metadata": cand.metadata,
                        }
                    )
        else:
            # Baselines B0 - B4 live retrieval
            retriever = self._get_or_create_retriever(
                project_id, method, project.source_artifacts
            )
            t0 = time.perf_counter()
            retrieved = retriever.retrieve(req, top_k=top_k)
            retrieval_time_sec = time.perf_counter() - t0

            for cand in retrieved:
                raw_candidates.append(
                    {
                        "rank": cand.rank,
                        "target_id": cand.target_id,
                        "score": cand.score,
                        "retriever_name": cand.retriever_name,
                        "metadata": cand.metadata,
                    }
                )

        # Enhance candidates with ground-truth and verification metadata
        enriched_candidates = []
        for cand in raw_candidates:
            target_id = cand["target_id"]
            is_gold = target_id in gold_links

            source_artifact = source_map.get(target_id)
            code_text = source_artifact.original_text if source_artifact else ""

            if "#" in target_id:
                display_name = target_id.split("#", 1)[1]
            elif "/" in target_id or "\\" in target_id:
                display_name = Path(target_id).name
            else:
                display_name = target_id

            enriched_candidates.append(
                {
                    "rank": cand["rank"],
                    "target_id": target_id,
                    "display_name": display_name,
                    "score": cand["score"],
                    "retriever_name": cand["retriever_name"],
                    "is_gold_link": None if is_dev else is_gold,
                    # Explicit separation between hypothesis and verified link:
                    "candidate_type": "retrieval_hypothesis",
                    "developer_verification_status": "unverified",
                    "developer_verification_note": (
                        "Pending developer verification workflow (Milestone B6)"
                    ),
                    "code_preview": code_text,
                    "code_lines": len(code_text.splitlines()) if code_text else 0,
                    "code_chars": len(code_text),
                    "metadata": cand.get("metadata", {}),
                }
            )

        gold_matched_count = (
            sum(1 for c in enriched_candidates if c["is_gold_link"])
            if not is_dev
            else None
        )

        method_info = next(
            (m for m in RETRIEVAL_METHODS_CATALOG if m["id"] == method),
            {"name": method},
        )

        return {
            "project_id": project_id,
            "requirement_id": requirement_id,
            "mode": norm_mode,
            "method": method,
            "method_name": method_info.get("name", method),
            "top_k": top_k,
            "total_candidates": len(enriched_candidates),
            "gold_links_retrieved": gold_matched_count,
            "total_gold_links": None if is_dev else len(gold_links),
            "is_evaluable": None if is_dev else (len(gold_links) > 0),
            "is_cached": is_cached,
            "retrieval_time_sec": retrieval_time_sec,
            "gold_link_targets": None if is_dev else sorted(list(gold_links)),
            "candidates": enriched_candidates,
        }


__all__ = [
    "DEFAULT_CHECKPOINT_DIR",
    "DEFAULT_MANIFEST_PATHS",
    "RETRIEVAL_METHODS_CATALOG",
    "TraceWiseService",
    "extract_title_from_requirement",
]
