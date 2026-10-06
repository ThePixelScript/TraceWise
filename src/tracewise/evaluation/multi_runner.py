"""Multi-project benchmark execution, scalability profiling, and metric aggregation."""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tracewise.evaluation.metrics import evaluate_retrieval
from tracewise.evaluation.models import EvaluationResult
from tracewise.evaluation.project import BenchmarkProject
from tracewise.evaluation.validation import validate_benchmark_project
from tracewise.retrieval.base import BaseRetriever


class ProjectBenchmarkResult(BaseModel):
    """Evaluation metrics and scalability telemetry for a single project."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str
    project_name: str
    num_requirements: int
    num_evaluable_requirements: int = 0
    num_zero_link_requirements: int = 0
    num_source_files: int
    num_source_chunks: int
    num_ground_truth_links: int
    num_candidates_evaluated: int
    indexing_time_sec: float
    query_time_sec: float
    total_time_sec: float
    validation_status: str
    map: float
    mrr: float
    precision_at_k: dict[int, float]
    recall_at_k: dict[int, float]
    evaluation_result: EvaluationResult
    metadata: dict[str, Any] = Field(default_factory=dict)


class MultiProjectBenchmarkResult(BaseModel):
    """Aggregate benchmark results and experiment reproducibility record.

    Aggregation methodology documentation:
    - Macro-average: Unweighted arithmetic mean of project-level metric scores:
        Macro-M = (1 / |P|) * sum_{p in P} M_p
      Treats each software project as an equal unit of observation.
    - Micro-average (Pooled): Query-weighted average across all queries in all projects:
        Micro-M = (1 / sum |Q_p|) * sum_{p in P} sum_{q in Q_p} Metric(q)
      Weights projects proportionally to their requirement query count.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    timestamp: str
    retriever_name: str
    retriever_config: dict[str, Any] = Field(default_factory=dict)
    artifact_type_filter: str | None = None
    k_values: list[int]
    project_results: dict[str, ProjectBenchmarkResult]
    macro_aggregates: dict[str, float]
    micro_aggregates: dict[str, float]
    total_runtime_sec: float
    metadata: dict[str, Any] = Field(default_factory=dict)

    def format_table(self) -> str:
        """Format benchmark results as an explicit, reproducible Markdown table."""
        header = (
            "| Project | Model | MAP | MRR | P@1 | P@3 | P@5 | R@1 | R@3 | R@5 | "
            "Total Reqs | Eval Reqs (Denom) | Zero-Link Reqs | "
            "Source Classes | Gold Links |"
        )
        sep = (
            "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | "
            ":---: | :---: | :---: | :---: | :---: | :---: | :---: |"
        )
        lines = [
            f"### Benchmark Evaluation: {self.retriever_name}",
            f"Run ID: `{self.run_id}` | Artifact Filter: `{self.artifact_type_filter}`",
            "",
            header,
            sep,
        ]
        for pid, p in self.project_results.items():
            p1 = p.precision_at_k.get(1, 0.0)
            p3 = p.precision_at_k.get(3, 0.0)
            p5 = p.precision_at_k.get(5, 0.0)
            r1 = p.recall_at_k.get(1, 0.0)
            r3 = p.recall_at_k.get(3, 0.0)
            r5 = p.recall_at_k.get(5, 0.0)
            eval_reqs = p.num_evaluable_requirements or len(
                p.evaluation_result.query_results
            )
            zero_reqs = p.num_zero_link_requirements or (p.num_requirements - eval_reqs)
            lines.append(
                f"| `{pid}` | {self.retriever_name} | {p.map:.4f} | {p.mrr:.4f} | "
                f"{p1:.4f} | {p3:.4f} | {p5:.4f} | "
                f"{r1:.4f} | {r3:.4f} | {r5:.4f} | "
                f"{p.num_requirements} | {eval_reqs} | {zero_reqs} | "
                f"{p.num_source_chunks} | {p.num_ground_truth_links} |"
            )
        lines.append("")
        lines.append(
            "*Note on Denominator: MAP, MRR, P@k, and R@k are computed strictly "
            "over evaluable requirements with >=1 gold link (Eval Reqs); "
            "zero-link queries are excluded from ranking metrics according to "
            "the TraceWise evaluation protocol.*"
        )
        return "\n".join(lines)


class MultiProjectBenchmarkRunner:
    """Executes benchmark evaluations across multiple independent software projects."""

    def __init__(
        self,
        projects: Sequence[BenchmarkProject],
        k_values: Sequence[int] = (1, 3, 5, 10),
        validate_before_run: bool = True,
    ) -> None:
        """Initialize multi-project benchmark runner.

        Args:
            projects: Sequence of independent BenchmarkProject instances.
            k_values: Evaluation cutoffs for Precision@k and Recall@k.
            validate_before_run: Whether to run dataset validation prior to evaluation.

        Raises:
            ValueError: If projects sequence is empty.
        """
        if not projects:
            raise ValueError(
                "MultiProjectBenchmarkRunner requires at least one project."
            )

        # Ensure no cross-project project_id collisions
        seen_ids: set[str] = set()
        for p in projects:
            if p.project_id in seen_ids:
                raise ValueError(
                    f"Duplicate project_id '{p.project_id}' found in project suite."
                )
            seen_ids.add(p.project_id)

        self.projects = list(projects)
        self.k_values = tuple(sorted(k_values))
        self.validate_before_run = validate_before_run

    def run(
        self,
        retriever: BaseRetriever,
        top_k: int | None = None,
        artifact_type_filter: str | None = "source_code",
        run_id: str | None = None,
        retriever_config: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MultiProjectBenchmarkResult:
        """Execute evaluation across all projects and compute aggregate metrics.

        Args:
            retriever: Configured BaseRetriever to evaluate.
            top_k: Optional maximum candidates to retrieve per query (None = all).
            artifact_type_filter: Artifact type filter (default: 'source_code').
            run_id: Optional unique identifier for this benchmark run.
            retriever_config: Optional dictionary recording retriever hyper-parameters.
            metadata: Optional additional experiment metadata.

        Returns:
            MultiProjectBenchmarkResult with per-project and aggregate metrics.
        """
        active_run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        t_total_start = time.perf_counter()

        project_results: dict[str, ProjectBenchmarkResult] = {}

        for project in self.projects:
            # 1. Validation check
            if self.validate_before_run:
                validate_benchmark_project(project, raise_on_error=True)

            t_proj_start = time.perf_counter()

            # 2. Index target corpus & measure indexing time
            t_index_start = time.perf_counter()
            retriever.index(project.source_artifacts)
            t_index_end = time.perf_counter()
            indexing_time_sec = t_index_end - t_index_start

            # 3. Retrieve candidates for each requirement & measure query time
            t_query_start = time.perf_counter()
            query_candidates = {}
            total_candidates = 0

            for req in project.requirements:
                candidates = retriever.retrieve(req, top_k=top_k)
                query_candidates[req.source_id] = candidates
                total_candidates += len(candidates)

            t_query_end = time.perf_counter()
            query_time_sec = t_query_end - t_query_start
            total_proj_time_sec = time.perf_counter() - t_proj_start

            # 4. Evaluate candidates against ground truth
            eval_result = evaluate_retrieval(
                retriever_name=retriever.retriever_name,
                query_candidates=query_candidates,
                ground_truth=project.ground_truth,
                dataset_name=project.project_id,
                k_values=self.k_values,
                metadata={
                    "project_name": project.project_name,
                    "num_requirements": project.num_requirements,
                    "num_source_chunks": project.num_source_chunks,
                    "num_source_files": project.num_source_files,
                    "num_ground_truth_links": project.num_ground_truth_links,
                    "indexing_time_sec": indexing_time_sec,
                    "query_time_sec": query_time_sec,
                    "num_candidates_evaluated": total_candidates,
                    **(metadata or {}),
                },
            )

            eval_req_count = len(
                [qid for qid, t in project.ground_truth.items() if len(t) > 0]
            )
            zero_link_count = project.num_requirements - eval_req_count

            p_res = ProjectBenchmarkResult(
                project_id=project.project_id,
                project_name=project.project_name,
                num_requirements=project.num_requirements,
                num_evaluable_requirements=eval_req_count,
                num_zero_link_requirements=zero_link_count,
                num_source_files=project.num_source_files,
                num_source_chunks=project.num_source_chunks,
                num_ground_truth_links=project.num_ground_truth_links,
                num_candidates_evaluated=total_candidates,
                indexing_time_sec=indexing_time_sec,
                query_time_sec=query_time_sec,
                total_time_sec=total_proj_time_sec,
                validation_status="VALID",
                map=eval_result.mean_average_precision,
                mrr=eval_result.mean_reciprocal_rank,
                precision_at_k=eval_result.mean_precision_at_k,
                recall_at_k=eval_result.mean_recall_at_k,
                evaluation_result=eval_result,
            )
            project_results[project.project_id] = p_res

        total_runtime_sec = time.perf_counter() - t_total_start

        # 5. Compute Macro-aggregates
        num_projects = len(project_results)
        macro_aggregates: dict[str, float] = {
            "map": sum(r.map for r in project_results.values()) / num_projects,
            "mrr": sum(r.mrr for r in project_results.values()) / num_projects,
        }
        for k in self.k_values:
            macro_aggregates[f"precision@{k}"] = (
                sum(r.precision_at_k.get(k, 0.0) for r in project_results.values())
                / num_projects
            )
            macro_aggregates[f"recall@{k}"] = (
                sum(r.recall_at_k.get(k, 0.0) for r in project_results.values())
                / num_projects
            )

        # 6. Compute Micro-aggregates (Pooled query results)
        all_query_results = [
            q_res
            for p_res in project_results.values()
            for q_res in p_res.evaluation_result.query_results.values()
        ]
        total_queries = len(all_query_results)

        if total_queries == 0:
            micro_aggregates: dict[str, float] = {
                "map": 0.0,
                "mrr": 0.0,
            }
            for k in self.k_values:
                micro_aggregates[f"precision@{k}"] = 0.0
                micro_aggregates[f"recall@{k}"] = 0.0
        else:
            micro_aggregates = {
                "map": sum(q.average_precision for q in all_query_results)
                / total_queries,
                "mrr": sum(q.reciprocal_rank for q in all_query_results)
                / total_queries,
            }
            for k in self.k_values:
                micro_aggregates[f"precision@{k}"] = (
                    sum(q.precision_at_k.get(k, 0.0) for q in all_query_results)
                    / total_queries
                )
                micro_aggregates[f"recall@{k}"] = (
                    sum(q.recall_at_k.get(k, 0.0) for q in all_query_results)
                    / total_queries
                )

        resolved_config = {
            "retriever_name": retriever.retriever_name,
            **(retriever_config or {}),
        }
        if hasattr(retriever, "model_name"):
            resolved_config["model_name"] = retriever.model_name
        if hasattr(retriever, "k1"):
            resolved_config["k1"] = retriever.k1
        if hasattr(retriever, "b"):
            resolved_config["b"] = retriever.b
        if hasattr(retriever, "alpha"):
            resolved_config["alpha"] = retriever.alpha

        return MultiProjectBenchmarkResult(
            run_id=active_run_id,
            timestamp=timestamp,
            retriever_name=retriever.retriever_name,
            retriever_config=resolved_config,
            artifact_type_filter=artifact_type_filter,
            k_values=list(self.k_values),
            project_results=project_results,
            macro_aggregates=macro_aggregates,
            micro_aggregates=micro_aggregates,
            total_runtime_sec=total_runtime_sec,
            metadata=metadata or {},
        )


__all__ = [
    "MultiProjectBenchmarkResult",
    "MultiProjectBenchmarkRunner",
    "ProjectBenchmarkResult",
]
