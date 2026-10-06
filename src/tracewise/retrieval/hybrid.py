"""Hybrid retrieval baseline combining lexical, semantic, and structural signals.

Implements Reciprocal Rank Fusion (RRF) across:
- B0: TfidfRetriever (sparse lexical retrieval)
- B2: SemanticRetriever (dense semantic retrieval)
- B3: StructuralRetriever (structure-guided identifier + dependency retrieval)

Reference:
- Cormack, G. V., Clarke, C. L., & Buettcher, S. (2009). Reciprocal rank fusion
  outperforms Condorcet and individual machine learning methods. In Proceedings
  of the 32nd international ACM SIGIR conference on Research and development
  in information retrieval (pp. 758-759).
"""

from __future__ import annotations

from collections.abc import Sequence

from tracewise.preprocessing.models import ProcessedText
from tracewise.retrieval.base import BaseRetriever
from tracewise.retrieval.exceptions import NotIndexedError
from tracewise.retrieval.models import RetrievalCandidate
from tracewise.retrieval.semantic import SemanticRetriever
from tracewise.retrieval.structural import StructuralRetriever
from tracewise.retrieval.tfidf import TfidfRetriever


def compute_rrf_score(
    ranks: Sequence[int | None],
    k: int = 60,
) -> float:
    """Compute Reciprocal Rank Fusion (RRF) score for a single target across rankings.

    For each component ranking:
    - If the target is present with 1-based rank r, its contribution is 1.0 / (k + r).
    - If the target is absent (represented by None), its contribution is 0.0.

    Args:
        ranks: Sequence of 1-based integer ranks (or None for absent rankings).
        k: Predetermined RRF smoothing constant (default: 60).
            Must be strictly positive.

    Returns:
        Cumulative RRF score as a float.

    Raises:
        ValueError: If k <= 0 or if any provided rank is <= 0.
    """
    if k <= 0:
        raise ValueError(f"RRF constant k must be strictly positive, got {k}.")

    total_score = 0.0
    for rank in ranks:
        if rank is not None:
            if rank <= 0:
                raise ValueError(
                    f"RRF rank must be a positive 1-based integer, got {rank}."
                )
            total_score += 1.0 / (float(k) + float(rank))

    return total_score


def fuse_rrf_rankings(
    component_rankings: Sequence[Sequence[RetrievalCandidate]],
    all_target_ids: Sequence[str] | None = None,
    k: int = 60,
) -> list[tuple[str, float, list[int | None]]]:
    """Fuse multiple component candidate rankings using Reciprocal Rank Fusion (RRF).

    Key properties:
    - Predetermined constant: k = 60 follows the conventional RRF configuration
      used in the literature.
    - Equal contribution: unweighted RRF sum across component rankings is a
      TraceWise experimental design choice fixed a priori, not benchmark-tuned.
    - Missing targets: targets absent from a component receive 0.0 contribution.
    - Duplicate target handling: if a target appears multiple times within a single
      component ranking, its best (minimum) rank is used.
    - Deterministic tie-breaking: ties are broken by target_id ascending.

    Args:
        component_rankings: Sequence of candidate lists from component retrievers.
        all_target_ids: Optional complete set of target IDs in the indexed corpus.
            If provided, ensures every indexed target is included even if unranked.
        k: Predetermined RRF constant (default: 60).

    Returns:
        Sorted list of tuples: (target_id, fused_score, list_of_ranks_per_component).
    """
    if k <= 0:
        raise ValueError(f"RRF constant k must be strictly positive, got {k}.")

    # Step 1: Extract best (minimum) 1-based rank for each target_id per component
    comp_best_ranks: list[dict[str, int]] = []
    for candidates in component_rankings:
        best_ranks: dict[str, int] = {}
        for c in candidates:
            tid = c.target_id
            if tid not in best_ranks or c.rank < best_ranks[tid]:
                best_ranks[tid] = c.rank
        comp_best_ranks.append(best_ranks)

    # Step 2: Determine target universe
    target_universe: set[str] = set()
    if all_target_ids is not None:
        target_universe.update(all_target_ids)
    for best_ranks in comp_best_ranks:
        target_universe.update(best_ranks.keys())

    # Step 3: Compute fused score for every target artifact
    scored: list[tuple[str, float, list[int | None]]] = []
    for tid in target_universe:
        ranks_for_tid: list[int | None] = [
            b_ranks.get(tid) for b_ranks in comp_best_ranks
        ]
        score = compute_rrf_score(ranks_for_tid, k=k)
        scored.append((tid, score, ranks_for_tid))

    # Step 4: Deterministic ordering by (-score, target_id ascending)
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored


class HybridRetriever(BaseRetriever):
    """Hybrid retrieval baseline combining lexical, semantic, and structural signals.

    Architecture:
    Combines three diverse, complementary retrieval baselines:
    - B0: TfidfRetriever (sparse lexical matching via sublinear TF + smoothed IDF)
    - B2: SemanticRetriever (dense semantic matching via all-MiniLM-L6-v2 embeddings)
    - B3: StructuralRetriever (structure-guided identifier matching + graph diffusion)

    Fusion Formulation:
    Uses Reciprocal Rank Fusion (RRF; Cormack et al., SIGIR 2009) as an
    equal-contribution, unweighted sum:
        RRF_score(d) = sum_{r in {B0, B2, B3}} (1 / (k + rank_r(d)))
    where:
    - k = 60 follows the conventional RRF configuration used in the literature.
    - Equal contribution of the B0, B2, and B3 rankings is a TraceWise experimental
      design choice fixed a priori, not benchmark-tuned.
    - If target artifact d is absent from component ranking r, its contribution is 0.0.
    - If a target artifact appears multiple times within a component ranking, its best
      (minimum) rank is used.
    - Candidates are ranked with 1-based consecutive ranks, breaking ties
      deterministically by target_id ascending:
        key=lambda candidate: (-candidate.score, candidate.target_id)

    Methodological Invariant:
    k = 60 follows the conventional RRF configuration used in the literature.
    Equal contribution of the B0, B2, and B3 rankings is a TraceWise experimental
    design choice fixed a priori, not benchmark-tuned. Ground-truth trace links
    are strictly prohibited from all retrieval and fusion operations.
    """

    retriever_name: str = "hybrid"

    def __init__(
        self,
        k: int = 60,
        tfidf_retriever: BaseRetriever | None = None,
        semantic_retriever: BaseRetriever | None = None,
        structural_retriever: BaseRetriever | None = None,
    ) -> None:
        """Initialize HybridRetriever with configurable component retrievers and RRF k.

        Args:
            k: Predetermined RRF smoothing constant (default: 60).
                Must be strictly positive.
            tfidf_retriever: Optional B0 lexical retriever instance.
                Defaults to TfidfRetriever().
            semantic_retriever: Optional B2 dense semantic retriever instance.
                Defaults to SemanticRetriever().
            structural_retriever: Optional B3 structure-guided retriever instance.
                Defaults to StructuralRetriever(alpha=0.5).

        Raises:
            ValueError: If k <= 0.
        """
        if k <= 0:
            raise ValueError(f"RRF constant k must be strictly positive, got {k}.")

        self.k: int = int(k)
        self.tfidf_retriever: BaseRetriever = tfidf_retriever or TfidfRetriever()
        self.semantic_retriever: BaseRetriever = (
            semantic_retriever or SemanticRetriever()
        )
        self.structural_retriever: BaseRetriever = (
            structural_retriever or StructuralRetriever(alpha=0.5)
        )
        self._target_ids: list[str] = []
        self._is_indexed: bool = False

    @property
    def is_indexed(self) -> bool:
        """Whether the retriever has an active index ready for querying."""
        return self._is_indexed or (
            self.tfidf_retriever.is_indexed
            and self.semantic_retriever.is_indexed
            and self.structural_retriever.is_indexed
        )

    def index(self, documents: Sequence[ProcessedText]) -> None:
        """Build or replace the target index across all component retrievers.

        Calling index again replaces previous indexes completely.

        Args:
            documents: Sequence of preprocessed text documents to index.

        Raises:
            ValueError: If documents is empty or contains duplicate source_ids.
        """
        doc_list = list(documents)
        if not doc_list:
            raise ValueError("Cannot index an empty document sequence.")

        seen_ids: set[str] = set()
        for doc in doc_list:
            if doc.source_id in seen_ids:
                raise ValueError(
                    f"Duplicate source_id '{doc.source_id}' found in documents."
                )
            seen_ids.add(doc.source_id)

        # Index each component retriever
        self.tfidf_retriever.index(doc_list)
        self.semantic_retriever.index(doc_list)
        self.structural_retriever.index(doc_list)

        self._target_ids = [d.source_id for d in doc_list]
        self._is_indexed = True

    def retrieve(
        self,
        query: ProcessedText,
        top_k: int | None = None,
    ) -> list[RetrievalCandidate]:
        """Retrieve matches for a query by fusing B0, B2, and B3 rankings with RRF.

        Candidates are scored using Reciprocal Rank Fusion (k=60) and sorted in
        descending order of score, with ties broken deterministically by target_id:
            key=lambda candidate: (-candidate.score, candidate.target_id)
        Ranks are 1-based and consecutive (1, 2, 3, ...).

        Args:
            query: Preprocessed query to retrieve against the indexed documents.
            top_k: Optional maximum number of candidates to return.
                If None, returns all candidates for the query.

        Returns:
            List of RetrievalCandidate objects ordered by descending fused score.

        Raises:
            NotIndexedError: If retrieve is called before indexing.
            ValueError: If top_k is less than or equal to 0.
        """
        if not self.is_indexed:
            raise NotIndexedError(
                f"Retriever '{self.retriever_name}' cannot retrieve before indexing."
            )

        if top_k is not None and top_k <= 0:
            raise ValueError(f"top_k must be strictly positive, got {top_k}.")

        # Step 1: Retrieve full candidate rankings from component retrievers
        tfidf_candidates = self.tfidf_retriever.retrieve(query, top_k=None)
        semantic_candidates = self.semantic_retriever.retrieve(query, top_k=None)
        structural_candidates = self.structural_retriever.retrieve(query, top_k=None)

        # Step 2: Fuse component rankings using Reciprocal Rank Fusion
        fused = fuse_rrf_rankings(
            component_rankings=[
                tfidf_candidates,
                semantic_candidates,
                structural_candidates,
            ],
            all_target_ids=self._target_ids,
            k=self.k,
        )

        # Step 3: Apply top_k cutoff if requested
        if top_k is not None:
            fused = fused[:top_k]

        # Step 4: Construct typed RetrievalCandidate results with 1-based ranks
        return [
            RetrievalCandidate(
                query_id=query.source_id,
                target_id=target_id,
                score=score,
                rank=rank,
                retriever_name=self.retriever_name,
                metadata={
                    "rrf_k": self.k,
                    "component_ranks": {
                        "tfidf": ranks[0],
                        "semantic": ranks[1],
                        "structural": ranks[2],
                    },
                },
            )
            for rank, (target_id, score, ranks) in enumerate(fused, start=1)
        ]
