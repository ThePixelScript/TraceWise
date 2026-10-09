"""Benchmark execution and metric reporting for B5 LLM-assisted reranking."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tracewise.b5.prompt import B5_PROMPT_VERSION
from tracewise.b5.reranker import B5RerankRetriever
from tracewise.evaluation.metrics import evaluate_retrieval
from tracewise.evaluation.project import BenchmarkProject
from tracewise.retrieval.bm25 import BM25Retriever


class B5BenchmarkResult(BaseModel):
    """Detailed evaluation result and telemetry for B5 on a benchmark project."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str
    project_name: str
    num_requirements: int
    num_evaluable_requirements: int
    num_zero_link_requirements: int
    num_source_chunks: int
    num_gold_links: int
    # Candidate recall upper bound diagnostic
    bm25_candidate_recall_at_20: float
    # Frozen B1 BM25 baseline metrics
    b1_map: float
    b1_mrr: float
    b1_precision_at_k: dict[int, float]
    b1_recall_at_k: dict[int, float]
    # B5 LLM-reranked metrics
    b5_map: float
    b5_mrr: float
    b5_precision_at_k: dict[int, float]
    b5_recall_at_k: dict[int, float]
    # Telemetry
    candidate_retrieval_time_sec: float
    llm_inference_time_sec: float
    total_time_sec: float
    num_llm_calls: int
    retries: int
    parsing_failures: int
    fallback_count: int = 0
    avg_candidates_evaluated: float
    # Configuration metadata
    configuration: dict[str, Any] = Field(default_factory=dict)


def run_b5_evaluation(
    project: BenchmarkProject,
    rerank_retriever: B5RerankRetriever | None = None,
    k_values: Sequence[int] = (1, 3, 5, 20),
) -> B5BenchmarkResult:
    """Execute controlled B5 evaluation on a single benchmark project.

    Evaluates:
    1. Frozen B1 BM25 (computes candidate pool and theoretical ceiling Recall@20).
    2. B5 LLM reranking of the top-20 BM25 candidate pool.
    3. Detailed runtime telemetry and failure rates.

    Args:
        project: BenchmarkProject instance to evaluate.
        rerank_retriever: Configured B5RerankRetriever. If None, uses defaults.
        k_values: Cutoff k values for Precision@k and Recall@k.

    Returns:
        B5BenchmarkResult containing B1 vs B5 comparisons and runtime telemetry.
    """
    t_start = time.perf_counter()
    k_vals = tuple(sorted(set(k_values)))
    retriever = (
        rerank_retriever if rerank_retriever is not None else B5RerankRetriever()
    )

    # 1. Evaluate frozen B1 BM25 baseline (candidate generator)
    bm25 = BM25Retriever(k1=1.5, b=0.75)
    bm25.index(project.source_artifacts)

    bm25_candidates_by_query = {}
    for req in project.requirements:
        bm25_candidates_by_query[req.source_id] = bm25.retrieve(req, top_k=20)

    b1_eval = evaluate_retrieval(
        retriever_name="bm25",
        query_candidates=bm25_candidates_by_query,
        ground_truth=project.ground_truth,
        dataset_name=project.project_id,
        k_values=k_vals,
    )

    bm25_candidate_ceiling = b1_eval.mean_recall_at_k.get(20, 0.0)

    # 2. Evaluate B5 LLM Reranking
    retriever.reset_telemetry()
    retriever.index(project.source_artifacts)

    b5_candidates_by_query = {}
    for req in project.requirements:
        b5_candidates_by_query[req.source_id] = retriever.retrieve(req, top_k=20)

    b5_eval = evaluate_retrieval(
        retriever_name=retriever.retriever_name,
        query_candidates=b5_candidates_by_query,
        ground_truth=project.ground_truth,
        dataset_name=project.project_id,
        k_values=k_vals,
    )

    total_time = time.perf_counter() - t_start

    eval_req_count = len([qid for qid, t in project.ground_truth.items() if len(t) > 0])
    zero_link_count = project.num_requirements - eval_req_count
    num_queries = len(project.requirements)
    avg_candidates = (
        retriever.total_candidates_evaluated / num_queries if num_queries > 0 else 0.0
    )

    config = {
        "backend": "Ollama",
        "model": retriever.provider.model_name,
        "temperature": getattr(retriever.provider, "temperature", 0.0),
        "think": getattr(retriever.provider, "think", False),
        "candidate_generator": "BM25 (k1=1.5, b=0.75)",
        "candidate_k": retriever.candidate_k,
        "max_retries": retriever.max_retries,
        "prompt_version": B5_PROMPT_VERSION,
        "relevance_scale": "0..3",
    }

    return B5BenchmarkResult(
        project_id=project.project_id,
        project_name=project.project_name,
        num_requirements=project.num_requirements,
        num_evaluable_requirements=eval_req_count,
        num_zero_link_requirements=zero_link_count,
        num_source_chunks=project.num_source_chunks,
        num_gold_links=project.num_ground_truth_links,
        bm25_candidate_recall_at_20=bm25_candidate_ceiling,
        b1_map=b1_eval.mean_average_precision,
        b1_mrr=b1_eval.mean_reciprocal_rank,
        b1_precision_at_k=b1_eval.mean_precision_at_k,
        b1_recall_at_k=b1_eval.mean_recall_at_k,
        b5_map=b5_eval.mean_average_precision,
        b5_mrr=b5_eval.mean_reciprocal_rank,
        b5_precision_at_k=b5_eval.mean_precision_at_k,
        b5_recall_at_k=b5_eval.mean_recall_at_k,
        candidate_retrieval_time_sec=retriever.candidate_retrieval_time_sec,
        llm_inference_time_sec=retriever.llm_inference_time_sec,
        total_time_sec=total_time,
        num_llm_calls=retriever.num_llm_calls,
        retries=retriever.retries,
        parsing_failures=retriever.parsing_failures,
        fallback_count=retriever.fallback_count,
        avg_candidates_evaluated=avg_candidates,
        configuration=config,
    )


def format_b5_comparison_table(results: Sequence[B5BenchmarkResult]) -> str:
    """Format B1 vs B5 comparison table across benchmark projects."""
    lines = [
        "### TraceWise Milestone B5: Controlled Retrieve-then-Rerank Benchmark",
        "",
        (
            "| Project | Method | BM25 R@20 (Ceiling) | MAP | MRR | "
            "P@1 | P@3 | P@5 | R@1 | R@3 | R@5 |"
        ),
        (
            "| :--- | :--- | :---: | :---: | :---: | "
            ":---: | :---: | :---: | :---: | :---: | :---: |"
        ),
    ]

    for res in results:
        b1_p1 = res.b1_precision_at_k.get(1, 0.0)
        b1_p3 = res.b1_precision_at_k.get(3, 0.0)
        b1_p5 = res.b1_precision_at_k.get(5, 0.0)
        b1_r1 = res.b1_recall_at_k.get(1, 0.0)
        b1_r3 = res.b1_recall_at_k.get(3, 0.0)
        b1_r5 = res.b1_recall_at_k.get(5, 0.0)

        b5_p1 = res.b5_precision_at_k.get(1, 0.0)
        b5_p3 = res.b5_precision_at_k.get(3, 0.0)
        b5_p5 = res.b5_precision_at_k.get(5, 0.0)
        b5_r1 = res.b5_recall_at_k.get(1, 0.0)
        b5_r3 = res.b5_recall_at_k.get(3, 0.0)
        b5_r5 = res.b5_recall_at_k.get(5, 0.0)

        ceil = f"{res.bm25_candidate_recall_at_20:.4f}"

        lines.append(
            f"| `{res.project_id}` | B1 (BM25) | {ceil} | "
            f"{res.b1_map:.4f} | {res.b1_mrr:.4f} | "
            f"{b1_p1:.4f} | {b1_p3:.4f} | {b1_p5:.4f} | "
            f"{b1_r1:.4f} | {b1_r3:.4f} | {b1_r5:.4f} |"
        )
        lines.append(
            f"| `{res.project_id}` | B5 (LLM Rerank) | {ceil} | "
            f"{res.b5_map:.4f} | {res.b5_mrr:.4f} | "
            f"{b5_p1:.4f} | {b5_p3:.4f} | {b5_p5:.4f} | "
            f"{b5_r1:.4f} | {b5_r3:.4f} | {b5_r5:.4f} |"
        )

    lines.append("")
    lines.append("#### Telemetry and Scalability")
    lines.append(
        "| Project | LLM Calls | Retries | Parsing Failures | Fallbacks | "
        "BM25 Time (s) | LLM Time (s) | Total Time (s) | Avg Cands/Req |"
    )
    lines.append(
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
    )
    for res in results:
        lines.append(
            f"| `{res.project_id}` | {res.num_llm_calls} | {res.retries} | "
            f"{res.parsing_failures} | {res.fallback_count} | "
            f"{res.candidate_retrieval_time_sec:.2f} | "
            f"{res.llm_inference_time_sec:.2f} | {res.total_time_sec:.2f} | "
            f"{res.avg_candidates_evaluated:.1f} |"
        )

    return "\n".join(lines)


__all__ = [
    "B5BenchmarkResult",
    "format_b5_comparison_table",
    "run_b5_evaluation",
]
