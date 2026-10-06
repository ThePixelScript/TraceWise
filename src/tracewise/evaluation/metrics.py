"""Standard Information Retrieval (IR) evaluation metrics for traceability.

Granularity & Exact Matching Convention:
    The metrics in this module perform strict, exact string matching between
    candidate ``target_id`` values and ground-truth target identifiers.
    Structural units at different levels of granularity (e.g. classes,
    methods, functions, files) are NOT treated as interchangeable:
    a candidate targeting an enclosing class will not match a ground-truth
    entry targeting a specific method within that class.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from tracewise.evaluation.models import EvaluationResult, QueryEvaluationResult
from tracewise.retrieval.models import RetrievalCandidate


def precision_at_k(
    candidates: Sequence[RetrievalCandidate],
    relevant_targets: set[str],
    k: int,
) -> float:
    """Compute Precision@k for a ranked list of candidate hypotheses.

    Precision@k is the fraction of the top-k retrieved candidates that are
    in the ground-truth relevant set:
        Precision@k = |{c in top-k : c.target_id in relevant_targets}| / k

    Edge-case conventions:
        - k <= 0: Raises ValueError.
        - relevant_targets is empty: Returns 0.0.
        - candidates is empty: Returns 0.0.
        - len(candidates) < k: Divides by k per standard TREC/IR convention;
          unretrieved positions are treated as non-relevant.
        - Duplicate candidate target_ids: Each distinct relevant target is
          counted at most once.

    Args:
        candidates: Sequence of RetrievalCandidate objects ordered by descending rank.
        relevant_targets: Set of ground-truth target IDs for the query.
        k: Positive integer cutoff rank.

    Returns:
        Float precision score in [0.0, 1.0].
    """
    if k <= 0:
        raise ValueError(f"Cutoff k must be strictly positive, got {k}.")

    if not relevant_targets or not candidates:
        return 0.0

    top_k = candidates[:k]
    distinct_relevant_hits = {
        c.target_id for c in top_k if c.target_id in relevant_targets
    }
    return len(distinct_relevant_hits) / float(k)


def recall_at_k(
    candidates: Sequence[RetrievalCandidate],
    relevant_targets: set[str],
    k: int,
) -> float:
    """Compute Recall@k for a ranked list of candidate hypotheses.

    Recall@k is the fraction of relevant targets that appear in the top-k
    retrieved candidates:
        Recall@k = |{c in top-k : c.target_id in relevant_targets}| / |relevant_targets|

    Edge-case conventions:
        - k <= 0: Raises ValueError.
        - relevant_targets is empty: Returns 0.0.
        - candidates is empty: Returns 0.0.
        - Duplicate candidate target_ids: Each distinct relevant target is
          counted at most once.

    Args:
        candidates: Sequence of RetrievalCandidate objects ordered by descending rank.
        relevant_targets: Set of ground-truth target IDs for the query.
        k: Positive integer cutoff rank.

    Returns:
        Float recall score in [0.0, 1.0].
    """
    if k <= 0:
        raise ValueError(f"Cutoff k must be strictly positive, got {k}.")

    if not relevant_targets:
        return 0.0

    if not candidates:
        return 0.0

    top_k = candidates[:k]
    distinct_relevant_hits = {
        c.target_id for c in top_k if c.target_id in relevant_targets
    }
    return len(distinct_relevant_hits) / float(len(relevant_targets))


def average_precision(
    candidates: Sequence[RetrievalCandidate],
    relevant_targets: set[str],
    k: int | None = None,
) -> float:
    """Compute Average Precision (AP) for a ranked list of candidate hypotheses.

    Average Precision calculates the average of Precision@i at each rank i
    where a relevant item is retrieved, divided by the total count of known
    relevant targets:
        AP = (sum_{i=1..k} P(i) * rel(i)) / |relevant_targets|

    Edge-case conventions:
        - k is not None and k <= 0: Raises ValueError.
        - relevant_targets is empty: Returns 0.0.
        - candidates is empty: Returns 0.0.
        - Denominator: Total count of known relevant targets (|relevant_targets|),
          per standard TREC IR conventions.
        - Duplicate candidate target_ids: If a relevant target appears multiple
          times, only its first occurrence receives precision credit.

    Args:
        candidates: Sequence of RetrievalCandidate objects ordered by descending rank.
        relevant_targets: Set of ground-truth target IDs for the query.
        k: Optional rank cutoff. If None, evaluates across all candidates.

    Returns:
        Float Average Precision score in [0.0, 1.0].
    """
    if k is not None and k <= 0:
        raise ValueError(f"Cutoff k must be strictly positive, got {k}.")

    if not relevant_targets or not candidates:
        return 0.0

    eval_candidates = candidates[:k] if k is not None else candidates
    seen_targets: set[str] = set()
    hits: int = 0
    precision_sum: float = 0.0

    for idx, c in enumerate(eval_candidates, start=1):
        if c.target_id in relevant_targets and c.target_id not in seen_targets:
            seen_targets.add(c.target_id)
            hits += 1
            precision_sum += hits / float(idx)

    return precision_sum / float(len(relevant_targets))


def mean_average_precision(
    query_candidates: Mapping[str, Sequence[RetrievalCandidate]],
    ground_truth: Mapping[str, set[str]],
    k: int | None = None,
) -> float:
    """Compute Mean Average Precision (MAP) across multiple queries.

    Averages the Average Precision across all queries present in ground_truth
    that have at least one relevant target. Queries where the retriever returned
    zero candidates receive an AP of 0.0 and are included in the average.

    Args:
        query_candidates: Mapping from query_id to retrieved candidates.
        ground_truth: Mapping from query_id to set of relevant target IDs.
        k: Optional rank cutoff passed to average_precision.

    Returns:
        Float MAP score in [0.0, 1.0].
    """
    eval_queries = [qid for qid, targets in ground_truth.items() if len(targets) > 0]
    if not eval_queries:
        return 0.0

    total_ap = sum(
        average_precision(
            query_candidates.get(qid, []),
            ground_truth[qid],
            k=k,
        )
        for qid in eval_queries
    )
    return total_ap / float(len(eval_queries))


def reciprocal_rank(
    candidates: Sequence[RetrievalCandidate],
    relevant_targets: set[str],
    k: int | None = None,
) -> float:
    """Compute Reciprocal Rank (RR) for a ranked list of candidate hypotheses.

    Reciprocal Rank is the reciprocal of the 1-based rank of the first relevant
    candidate found:
        RR = 1.0 / first_relevant_rank (if found within rank <= k, else 0.0)

    Edge-case conventions:
        - k is not None and k <= 0: Raises ValueError.
        - relevant_targets is empty: Returns 0.0.
        - candidates is empty: Returns 0.0.
        - No relevant target found within top-k: Returns 0.0.

    Args:
        candidates: Sequence of RetrievalCandidate objects ordered by descending rank.
        relevant_targets: Set of ground-truth target IDs for the query.
        k: Optional rank cutoff. If None, evaluates across all candidates.

    Returns:
        Float Reciprocal Rank score in [0.0, 1.0].
    """
    if k is not None and k <= 0:
        raise ValueError(f"Cutoff k must be strictly positive, got {k}.")

    if not relevant_targets or not candidates:
        return 0.0

    eval_candidates = candidates[:k] if k is not None else candidates
    for idx, c in enumerate(eval_candidates, start=1):
        if c.target_id in relevant_targets:
            return 1.0 / float(idx)

    return 0.0


def mean_reciprocal_rank(
    query_candidates: Mapping[str, Sequence[RetrievalCandidate]],
    ground_truth: Mapping[str, set[str]],
    k: int | None = None,
) -> float:
    """Compute Mean Reciprocal Rank (MRR) across multiple queries.

    Averages the Reciprocal Rank across all queries present in ground_truth
    that have at least one relevant target. Queries where no relevant item was
    retrieved receive an RR of 0.0 and are included in the average.

    Args:
        query_candidates: Mapping from query_id to retrieved candidates.
        ground_truth: Mapping from query_id to set of relevant target IDs.
        k: Optional rank cutoff passed to reciprocal_rank.

    Returns:
        Float MRR score in [0.0, 1.0].
    """
    eval_queries = [qid for qid, targets in ground_truth.items() if len(targets) > 0]
    if not eval_queries:
        return 0.0

    total_rr = sum(
        reciprocal_rank(
            query_candidates.get(qid, []),
            ground_truth[qid],
            k=k,
        )
        for qid in eval_queries
    )
    return total_rr / float(len(eval_queries))


def evaluate_query(
    query_id: str,
    candidates: Sequence[RetrievalCandidate],
    relevant_targets: set[str],
    k_values: Sequence[int] = (1, 3, 5, 10),
) -> QueryEvaluationResult:
    """Evaluate retrieval results for a single query across multiple k cutoffs."""
    prec_at_k: dict[int, float] = {}
    rec_at_k: dict[int, float] = {}

    for k in sorted(k_values):
        prec_at_k[k] = precision_at_k(candidates, relevant_targets, k)
        rec_at_k[k] = recall_at_k(candidates, relevant_targets, k)

    ap = average_precision(candidates, relevant_targets, k=None)
    rr = reciprocal_rank(candidates, relevant_targets, k=None)

    return QueryEvaluationResult(
        query_id=query_id,
        num_relevant=len(relevant_targets),
        num_retrieved=len(candidates),
        precision_at_k=prec_at_k,
        recall_at_k=rec_at_k,
        average_precision=ap,
        reciprocal_rank=rr,
    )


def evaluate_retrieval(
    retriever_name: str,
    query_candidates: Mapping[str, Sequence[RetrievalCandidate]],
    ground_truth: Mapping[str, set[str]],
    dataset_name: str = "",
    k_values: Sequence[int] = (1, 3, 5, 10),
    metadata: dict[str, Any] | None = None,
) -> EvaluationResult:
    """Evaluate candidate retrieval across all queries against ground truth."""
    eval_queries = sorted(
        [qid for qid, targets in ground_truth.items() if len(targets) > 0]
    )
    num_queries = len(eval_queries)

    query_results: dict[str, QueryEvaluationResult] = {}
    for qid in eval_queries:
        cands = query_candidates.get(qid, [])
        targets = ground_truth[qid]
        q_res = evaluate_query(qid, cands, targets, k_values=k_values)
        query_results[qid] = q_res

    if num_queries == 0:
        return EvaluationResult(
            retriever_name=retriever_name,
            dataset_name=dataset_name or "unknown",
            num_queries=0,
            mean_average_precision=0.0,
            mean_reciprocal_rank=0.0,
            mean_precision_at_k={k: 0.0 for k in sorted(k_values)},
            mean_recall_at_k={k: 0.0 for k in sorted(k_values)},
            query_results={},
            metadata=metadata or {},
        )

    map_score = sum(q.average_precision for q in query_results.values()) / float(
        num_queries
    )
    mrr_score = sum(q.reciprocal_rank for q in query_results.values()) / float(
        num_queries
    )

    mean_prec: dict[int, float] = {}
    mean_rec: dict[int, float] = {}
    for k in sorted(k_values):
        mean_prec[k] = sum(q.precision_at_k[k] for q in query_results.values()) / float(
            num_queries
        )
        mean_rec[k] = sum(q.recall_at_k[k] for q in query_results.values()) / float(
            num_queries
        )

    return EvaluationResult(
        retriever_name=retriever_name,
        dataset_name=dataset_name or "unknown",
        num_queries=num_queries,
        mean_average_precision=map_score,
        mean_reciprocal_rank=mrr_score,
        mean_precision_at_k=mean_prec,
        mean_recall_at_k=mean_rec,
        query_results=query_results,
        metadata=metadata or {},
    )


__all__ = [
    "average_precision",
    "evaluate_query",
    "evaluate_retrieval",
    "mean_average_precision",
    "mean_reciprocal_rank",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
]
