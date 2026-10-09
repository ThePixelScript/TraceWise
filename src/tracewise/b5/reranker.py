"""Controlled LLM-assisted RAG reranking retriever for TraceWise B5."""

from __future__ import annotations

import time
from collections.abc import Sequence

from tracewise.b5.prompt import (
    B5CandidateItem,
    B5PromptBuilder,
    B5ValidationError,
    parse_and_validate_b5_response,
)
from tracewise.b5.providers import (
    LLMProvider,
    LLMProviderError,
    OllamaProvider,
)
from tracewise.preprocessing.models import ProcessedText
from tracewise.retrieval.base import BaseRetriever
from tracewise.retrieval.bm25 import BM25Retriever
from tracewise.retrieval.exceptions import NotIndexedError
from tracewise.retrieval.models import RetrievalCandidate


class B5RerankRetriever(BaseRetriever):
    """Controlled retrieve-then-rerank pipeline baseline (B5).

    Pipeline specification:
    1. Candidate Retrieval: Top-k=20 candidates generated via frozen B1 BM25.
    2. Prompt Construction: Formats requirement and code candidates into a single
       fixed prompt.
    3. LLM Scoring: Queries local LLM (qwen3.5:9b, temp=0, think=false) for 0–3
       relevance scores.
    4. Validation & Bounded Retry: Validates strict JSON output with fixed retry
       limit.
    5. Deterministic Reranking: Sorts candidates by:
         Primary:   LLM relevance score descending
         Secondary: original BM25 rank ascending
         Tertiary:  target_id ascending
    6. Contract Output: Emits standard RetrievalCandidate objects with 1-based ranks.
    """

    retriever_name: str = "b5_llm_rerank"

    def __init__(
        self,
        candidate_retriever: BaseRetriever | None = None,
        provider: LLMProvider | None = None,
        candidate_k: int = 20,
        max_retries: int = 2,
        fallback_to_bm25: bool = True,
        prompt_builder: B5PromptBuilder | None = None,
    ) -> None:
        """Initialize the B5 reranking retriever.

        Args:
            candidate_retriever: Candidate retrieval baseline. Defaults to frozen
                B1 BM25.
            provider: LLM inference provider. Defaults to
                OllamaProvider(qwen3.5:9b).
            candidate_k: Fixed candidate pool size retrieved per requirement
                (default: 20).
            max_retries: Fixed maximum retry count for malformed model outputs
                (default: 2).
            fallback_to_bm25: If True, falls back to preserving BM25 ranking (with
                score 0.0) upon retry exhaustion, safely recording the failure.
                If False, raises error.
            prompt_builder: Fixed B5 prompt builder instance.
        """
        self.candidate_retriever = (
            candidate_retriever
            if candidate_retriever is not None
            else BM25Retriever(k1=1.5, b=0.75)
        )
        self.provider = (
            provider
            if provider is not None
            else OllamaProvider(model="qwen3.5:9b", temperature=0.0, think=False)
        )
        if candidate_k <= 0:
            raise ValueError(
                f"candidate_k must be strictly positive, got {candidate_k}."
            )
        if max_retries < 0:
            raise ValueError(f"max_retries must be non-negative, got {max_retries}.")

        self.candidate_k = candidate_k
        self.max_retries = max_retries
        self.fallback_to_bm25 = fallback_to_bm25
        self.prompt_builder = prompt_builder or B5PromptBuilder()

        self._is_indexed: bool = False
        self._documents: dict[str, ProcessedText] = {}

        # Scalability and experiment telemetry
        self.candidate_retrieval_time_sec: float = 0.0
        self.llm_inference_time_sec: float = 0.0
        self.num_llm_calls: int = 0
        self.retries: int = 0
        self.parsing_failures: int = 0
        self.fallback_count: int = 0
        self.total_candidates_evaluated: int = 0
        self.total_queries: int = 0

    @property
    def is_indexed(self) -> bool:
        """Whether the retriever and its candidate generator are indexed."""
        return self._is_indexed and self.candidate_retriever.is_indexed

    def reset_telemetry(self) -> None:
        """Reset runtime counters before a benchmark run."""
        self.candidate_retrieval_time_sec = 0.0
        self.llm_inference_time_sec = 0.0
        self.num_llm_calls = 0
        self.retries = 0
        self.parsing_failures = 0
        self.fallback_count = 0
        self.total_candidates_evaluated = 0
        self.total_queries = 0

    def index(self, documents: Sequence[ProcessedText]) -> None:
        """Build the target code corpus index.

        Indexes documents in the underlying candidate retriever (BM25)
        and preserves document references for context prompt generation.
        """
        self.candidate_retriever.index(documents)
        self._documents = {doc.source_id: doc for doc in documents}
        self._is_indexed = True

    def retrieve(
        self,
        query: ProcessedText,
        top_k: int | None = None,
    ) -> list[RetrievalCandidate]:
        """Retrieve and rerank candidates for a requirement query.

        Args:
            query: Preprocessed requirement text query.
            top_k: Optional maximum number of final reranked candidates to return.

        Returns:
            List of RetrievalCandidate objects sorted by descending LLM score.

        Raises:
            NotIndexedError: If retrieve is called before index.
            ValueError: If top_k <= 0.
            B5ValidationError: If model output is malformed, retries exhausted,
                and fallback_to_bm25 is False.
        """
        if not self.is_indexed:
            raise NotIndexedError("B5RerankRetriever cannot retrieve before indexing.")
        if top_k is not None and top_k <= 0:
            raise ValueError(f"top_k must be strictly positive, got {top_k}.")

        # 1. Candidate Retrieval via frozen BM25
        t_cand_start = time.perf_counter()
        bm25_candidates = self.candidate_retriever.retrieve(
            query, top_k=self.candidate_k
        )
        t_cand_end = time.perf_counter()
        self.candidate_retrieval_time_sec += t_cand_end - t_cand_start

        if not bm25_candidates:
            self.total_queries += 1
            return []

        # 2. Prepare candidate representations for prompt
        candidate_items: list[B5CandidateItem] = []
        for cand in bm25_candidates:
            doc = self._documents.get(cand.target_id)
            code_text = doc.original_text if doc else ""
            location = (
                doc.metadata.get("file_path")
                if doc and doc.metadata.get("file_path")
                else cand.target_id
            )
            candidate_items.append(
                B5CandidateItem(
                    target_id=cand.target_id,
                    file_path=str(location),
                    code_text=code_text,
                    metadata=cand.metadata,
                )
            )

        expected_target_ids = [c.target_id for c in bm25_candidates]
        prompt = self.prompt_builder.build_prompt(
            requirement_id=query.source_id,
            requirement_text=query.original_text,
            candidates=candidate_items,
        )

        # 3. LLM Scoring with bounded retry for malformed output
        t_llm_start = time.perf_counter()
        scores: dict[str, int] = {}
        fallback_occurred = False

        for attempt in range(self.max_retries + 1):
            self.num_llm_calls += 1
            try:
                llm_response = self.provider.generate(prompt)
                scores = parse_and_validate_b5_response(
                    raw_response=llm_response.content,
                    expected_target_ids=expected_target_ids,
                )
                break
            except (B5ValidationError, LLMProviderError, Exception) as exc:
                if attempt < self.max_retries:
                    self.retries += 1
                else:
                    self.parsing_failures += 1
                    if self.fallback_to_bm25:
                        # Fail safely: preserve candidate pool in BM25 order
                        # with 0 scores
                        scores = {tid: 0 for tid in expected_target_ids}
                        fallback_occurred = True
                        self.fallback_count += 1
                    else:
                        raise exc

        t_llm_end = time.perf_counter()
        self.llm_inference_time_sec += t_llm_end - t_llm_start
        self.total_candidates_evaluated += len(bm25_candidates)
        self.total_queries += 1

        # 4. Deterministic Reranking
        # Sort key:
        #   Primary:   descending LLM score (-score)
        #   Secondary: original BM25 rank ascending (c.rank)
        #   Tertiary:  target_id ascending (c.target_id)
        sorted_candidates = sorted(
            bm25_candidates,
            key=lambda c: (-scores.get(c.target_id, 0), c.rank, c.target_id),
        )

        # 5. Output normal RetrievalCandidate objects
        reranked: list[RetrievalCandidate] = []
        for rank_idx, orig_cand in enumerate(sorted_candidates, start=1):
            raw_score = scores.get(orig_cand.target_id, 0)
            # When fallback occurred, no genuine LLM judgment exists.
            reported_llm_score = None if fallback_occurred else raw_score
            reranked.append(
                RetrievalCandidate(
                    query_id=query.source_id,
                    target_id=orig_cand.target_id,
                    score=float(raw_score),
                    rank=rank_idx,
                    retriever_name=self.retriever_name,
                    metadata={
                        **orig_cand.metadata,
                        "bm25_score": orig_cand.score,
                        "bm25_rank": orig_cand.rank,
                        "llm_score": reported_llm_score,
                        "b5_fallback": fallback_occurred,
                    },
                )
            )

        if top_k is not None:
            reranked = reranked[:top_k]

        return reranked


__all__ = ["B5RerankRetriever"]
