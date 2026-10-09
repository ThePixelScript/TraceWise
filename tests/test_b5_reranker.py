"""Unit tests for TraceWise Milestone B5: LLM-assisted RAG reranking baseline.

Verifies:
- Prompt construction and schema isolation
- Strict JSON parsing, schema validation, and error detection
- Missing, duplicate, unknown target IDs, and invalid score validation
- Provider abstraction and mocking
- Retrieval contract compliance and lifecycle
- Deterministic 3-level tie-breaking
- Bounded retry handling and safe fallback
"""

import json

import pytest

from tracewise.b5.prompt import (
    B5CandidateItem,
    B5PromptBuilder,
    B5ValidationError,
    parse_and_validate_b5_response,
)
from tracewise.b5.providers import (
    LLMProviderError,
    LLMResponse,
    MockLLMProvider,
)
from tracewise.b5.reranker import B5RerankRetriever
from tracewise.preprocessing.models import ProcessedText
from tracewise.retrieval.base import BaseRetriever
from tracewise.retrieval.exceptions import NotIndexedError
from tracewise.retrieval.models import RetrievalCandidate


def make_doc(
    source_id: str,
    text: str,
    file_path: str | None = None,
) -> ProcessedText:
    """Helper to create minimal valid ProcessedText instances for tests."""
    tokens = text.lower().split()
    meta = {}
    if file_path:
        meta["file_path"] = file_path
    return ProcessedText(
        source_id=source_id,
        original_text=text,
        normalized_text=text.lower(),
        tokens=tokens,
        metadata=meta,
    )


class StubCandidateRetriever(BaseRetriever):
    """Deterministic stub candidate retriever for unit testing."""

    retriever_name: str = "stub_bm25"

    def __init__(
        self, preset_candidates: list[tuple[str, float]] | None = None
    ) -> None:
        self._preset = preset_candidates or []
        self._indexed = False

    @property
    def is_indexed(self) -> bool:
        return self._indexed

    def index(self, documents: list[ProcessedText]) -> None:
        self._indexed = True

    def retrieve(
        self,
        query: ProcessedText,
        top_k: int | None = None,
    ) -> list[RetrievalCandidate]:
        if not self._indexed:
            raise NotIndexedError("StubRetriever not indexed.")
        results = [
            RetrievalCandidate(
                query_id=query.source_id,
                target_id=tid,
                score=score,
                rank=idx + 1,
                retriever_name=self.retriever_name,
            )
            for idx, (tid, score) in enumerate(self._preset)
        ]
        if top_k is not None:
            results = results[:top_k]
        return results


# ==============================================================================
# 1. Prompt Construction Tests
# ==============================================================================


class TestB5PromptConstruction:
    def test_prompt_contains_requirement_and_candidates(self):
        builder = B5PromptBuilder(max_code_chars=1000)
        candidates = [
            B5CandidateItem(
                target_id="AuthManager",
                file_path="src/auth/manager.py",
                code_text="class AuthManager:\n    def login(self): pass",
            ),
            B5CandidateItem(
                target_id="UserDao",
                file_path="src/db/user_dao.py",
                code_text="class UserDao:\n    def get_user(self): pass",
            ),
        ]

        prompt = builder.build_prompt(
            requirement_id="REQ-001",
            requirement_text="The system shall allow users to log in.",
            candidates=candidates,
        )

        assert "REQ-001" in prompt
        assert "The system shall allow users to log in." in prompt
        assert "AuthManager" in prompt
        assert "src/auth/manager.py" in prompt
        assert "UserDao" in prompt
        assert "src/db/user_dao.py" in prompt
        assert "class AuthManager" in prompt

    def test_prompt_defines_relevance_scale(self):
        builder = B5PromptBuilder()
        prompt = builder.build_prompt("REQ-1", "Text", [])

        assert "0 = unrelated" in prompt
        assert "1 = weak/indirect relation" in prompt
        assert "2 = plausible/partial implementation" in prompt
        assert "3 = strong/direct implementation" in prompt

    def test_prompt_specifies_strict_json_schema(self):
        builder = B5PromptBuilder()
        prompt = builder.build_prompt("REQ-1", "Text", [])

        assert '"candidates"' in prompt
        assert '"target_id"' in prompt
        assert '"score"' in prompt
        assert "Output valid JSON ONLY" in prompt
        assert "Do NOT invent, hallucinate, or alter any target_id" in prompt

    def test_prompt_code_truncation_when_exceeding_budget(self):
        builder = B5PromptBuilder(max_code_chars=50)
        long_code = "x = 1\n" * 30  # 180 chars
        candidate = B5CandidateItem(target_id="LargeClass", code_text=long_code)

        block = builder.format_candidate_block(1, candidate)
        assert "LargeClass" in block
        assert "[... remaining source code truncated for token budget ...]" in block


# ==============================================================================
# 2. Response Parsing and Validation Tests
# ==============================================================================


class TestB5ResponseParsingAndValidation:
    def test_valid_json_parses_successfully(self):
        payload = {
            "candidates": [
                {"target_id": "ClassA", "score": 3},
                {"target_id": "ClassB", "score": 1},
                {"target_id": "ClassC", "score": 0},
            ]
        }
        res = parse_and_validate_b5_response(
            json.dumps(payload), ["ClassA", "ClassB", "ClassC"]
        )
        assert res == {"ClassA": 3, "ClassB": 1, "ClassC": 0}

    def test_markdown_fenced_json_parses_successfully(self):
        payload = (
            "```json\n"
            '{\n  "candidates": [\n    {"target_id": "ClassA", "score": 2}\n  ]\n}\n'
            "```"
        )
        res = parse_and_validate_b5_response(payload, ["ClassA"])
        assert res == {"ClassA": 2}

    def test_invalid_json_syntax_raises_validation_error(self):
        with pytest.raises(B5ValidationError, match="Malformed JSON"):
            parse_and_validate_b5_response("not a valid json {", ["ClassA"])

    def test_missing_candidates_key_raises_validation_error(self):
        with pytest.raises(B5ValidationError, match="Missing required top-level"):
            parse_and_validate_b5_response('{"results": []}', ["ClassA"])

    def test_missing_candidate_in_response_raises_validation_error(self):
        payload = {"candidates": [{"target_id": "ClassA", "score": 3}]}
        # Expected ClassA and ClassB, but model only returned ClassA
        with pytest.raises(B5ValidationError, match="Expected 2 candidates"):
            parse_and_validate_b5_response(json.dumps(payload), ["ClassA", "ClassB"])

    def test_duplicate_target_id_raises_validation_error(self):
        payload = {
            "candidates": [
                {"target_id": "ClassA", "score": 3},
                {"target_id": "ClassA", "score": 1},
            ]
        }
        with pytest.raises(B5ValidationError, match="Duplicate target_id 'ClassA'"):
            parse_and_validate_b5_response(json.dumps(payload), ["ClassA", "ClassB"])

    def test_unknown_target_id_raises_validation_error(self):
        payload = {"candidates": [{"target_id": "UnknownClass", "score": 1}]}
        with pytest.raises(B5ValidationError, match="Unknown target_id 'UnknownClass'"):
            parse_and_validate_b5_response(json.dumps(payload), ["ClassA"])

    @pytest.mark.parametrize("invalid_score", [-1, 4, 1.5, "2", True, False, None])
    def test_invalid_score_values_raise_validation_error(self, invalid_score):
        payload = {"candidates": [{"target_id": "ClassA", "score": invalid_score}]}
        with pytest.raises(B5ValidationError, match="Invalid score"):
            parse_and_validate_b5_response(json.dumps(payload), ["ClassA"])

    def test_empty_expected_candidates_list(self):
        payload = {"candidates": []}
        res = parse_and_validate_b5_response(json.dumps(payload), [])
        assert res == {}


# ==============================================================================
# 3. Provider Mocking Tests
# ==============================================================================


class TestB5ProviderMocking:
    def test_mock_provider_records_calls_and_returns_responses(self):
        provider = MockLLMProvider(
            responses=['{"candidates": [{"target_id": "A", "score": 1}]}']
        )
        assert provider.model_name == "mock-qwen3.5:9b"
        assert provider.call_count == 0

        resp = provider.generate("Test prompt")
        assert provider.call_count == 1
        assert provider.calls[0] == "Test prompt"
        assert isinstance(resp, LLMResponse)
        assert "Class" not in resp.content

    def test_mock_provider_raises_queued_exception(self):
        provider = MockLLMProvider(
            responses=[LLMProviderError("Simulated connection failure")]
        )
        with pytest.raises(LLMProviderError, match="Simulated connection failure"):
            provider.generate("Prompt")


# ==============================================================================
# 4. Retrieval Contract & Lifecycle Tests
# ==============================================================================


class TestB5RetrievalContract:
    def test_is_indexed_lifecycle(self):
        mock_provider = MockLLMProvider(default_response='{"candidates": []}')
        stub_bm25 = StubCandidateRetriever()
        retriever = B5RerankRetriever(
            candidate_retriever=stub_bm25, provider=mock_provider
        )

        assert not retriever.is_indexed
        retriever.index([make_doc("D1", "some content")])
        assert retriever.is_indexed

    def test_retrieve_before_index_raises_not_indexed_error(self):
        retriever = B5RerankRetriever(
            candidate_retriever=StubCandidateRetriever(),
            provider=MockLLMProvider(default_response="{}"),
        )
        with pytest.raises(NotIndexedError, match="cannot retrieve before indexing"):
            retriever.retrieve(make_doc("Q1", "query text"))

    def test_retrieve_with_invalid_top_k_raises_value_error(self):
        stub = StubCandidateRetriever()
        retriever = B5RerankRetriever(
            candidate_retriever=stub, provider=MockLLMProvider(default_response="{}")
        )
        retriever.index([make_doc("D1", "text")])
        with pytest.raises(ValueError, match="strictly positive"):
            retriever.retrieve(make_doc("Q1", "text"), top_k=0)

    def test_empty_candidate_retrieval_returns_empty(self):
        stub = StubCandidateRetriever(preset_candidates=[])
        mock_provider = MockLLMProvider(default_response="{}")
        retriever = B5RerankRetriever(candidate_retriever=stub, provider=mock_provider)
        retriever.index([make_doc("D1", "text")])

        res = retriever.retrieve(make_doc("Q1", "text"))
        assert res == []
        assert mock_provider.call_count == 0  # LLM should not be called if 0 candidates

    def test_retrieval_returns_valid_retrieval_candidates(self):
        stub = StubCandidateRetriever(preset_candidates=[("D1", 10.0), ("D2", 5.0)])
        json_resp = json.dumps(
            {
                "candidates": [
                    {"target_id": "D1", "score": 2},
                    {"target_id": "D2", "score": 3},
                ]
            }
        )
        retriever = B5RerankRetriever(
            candidate_retriever=stub,
            provider=MockLLMProvider(default_response=json_resp),
        )
        retriever.index([make_doc("D1", "code 1"), make_doc("D2", "code 2")])

        candidates = retriever.retrieve(make_doc("REQ1", "login"))
        assert len(candidates) == 2
        for cand in candidates:
            assert isinstance(cand, RetrievalCandidate)
            assert cand.query_id == "REQ1"
            assert cand.retriever_name == "b5_llm_rerank"
            assert cand.rank in (1, 2)
            assert cand.score in (2.0, 3.0)
            assert "bm25_score" in cand.metadata
            assert "bm25_rank" in cand.metadata
            assert "llm_score" in cand.metadata


# ==============================================================================
# 5. Deterministic Tie-Breaking Tests
# ==============================================================================


class TestB5DeterministicTieBreaking:
    """Verifies: LLM score desc -> BM25 rank asc -> target_id asc."""

    def test_three_level_deterministic_tie_breaking(self):
        # BM25 initial pool:
        # C1: rank 1, score 20.0
        # C2: rank 2, score 18.0
        # C3: rank 3, score 15.0
        # C4: rank 4, score 12.0
        # C5: rank 5, score 10.0
        preset = [
            ("C1", 20.0),
            ("C2", 18.0),
            ("C3", 15.0),
            ("C4", 12.0),
            ("C5", 10.0),
        ]
        # LLM scores:
        # C1: 1
        # C2: 3 (highest score -> must become rank 1)
        # C3: 1 (same LLM score as C1, but C1 had BM25 rank 1 vs C3 rank 3
        #        -> C1 before C3)
        # C4: 0 (score 0, BM25 rank 4)
        # C5: 0 (score 0, BM25 rank 5 -> C4 before C5)
        llm_response = json.dumps(
            {
                "candidates": [
                    {"target_id": "C1", "score": 1},
                    {"target_id": "C2", "score": 3},
                    {"target_id": "C3", "score": 1},
                    {"target_id": "C4", "score": 0},
                    {"target_id": "C5", "score": 0},
                ]
            }
        )

        retriever = B5RerankRetriever(
            candidate_retriever=StubCandidateRetriever(preset),
            provider=MockLLMProvider(default_response=llm_response),
        )
        retriever.index([make_doc(cid, f"code {cid}") for cid, _ in preset])

        results = retriever.retrieve(make_doc("Q1", "query"))

        assert [r.target_id for r in results] == ["C2", "C1", "C3", "C4", "C5"]
        assert [r.rank for r in results] == [1, 2, 3, 4, 5]
        assert [r.score for r in results] == [3.0, 1.0, 1.0, 0.0, 0.0]

    def test_zero_scores_are_preserved(self):
        preset = [("A", 10.0), ("B", 8.0)]
        llm_response = json.dumps(
            {
                "candidates": [
                    {"target_id": "A", "score": 0},
                    {"target_id": "B", "score": 0},
                ]
            }
        )
        retriever = B5RerankRetriever(
            candidate_retriever=StubCandidateRetriever(preset),
            provider=MockLLMProvider(default_response=llm_response),
        )
        retriever.index([make_doc("A", "code A"), make_doc("B", "code B")])

        results = retriever.retrieve(make_doc("Q1", "query"))
        assert len(results) == 2
        assert results[0].target_id == "A"
        assert results[1].target_id == "B"
        assert results[0].score == 0.0
        assert results[1].score == 0.0


# ==============================================================================
# 6. Retry Limit & Malformed Output Tests
# ==============================================================================


class TestB5RetryAndFallback:
    def test_retry_on_malformed_json_succeeds_on_second_attempt(self):
        # Attempt 1: Malformed JSON
        # Attempt 2: Valid response
        valid_json = json.dumps({"candidates": [{"target_id": "C1", "score": 3}]})
        provider = MockLLMProvider(
            responses=[
                "Malformed output {not json",
                valid_json,
            ]
        )
        retriever = B5RerankRetriever(
            candidate_retriever=StubCandidateRetriever([("C1", 10.0)]),
            provider=provider,
            max_retries=2,
        )
        retriever.index([make_doc("C1", "code")])

        res = retriever.retrieve(make_doc("Q1", "query"))

        assert len(res) == 1
        assert res[0].target_id == "C1"
        assert res[0].score == 3.0
        assert retriever.retries == 1
        assert retriever.parsing_failures == 0
        assert retriever.num_llm_calls == 2

    def test_retry_exhaustion_falls_back_safely_to_bm25(self):
        # 3 attempts (1 initial + 2 retries), all malformed
        provider = MockLLMProvider(
            responses=[
                "Malformed 1",
                "Malformed 2",
                "Malformed 3",
            ]
        )
        preset = [("C1", 10.0), ("C2", 5.0)]
        retriever = B5RerankRetriever(
            candidate_retriever=StubCandidateRetriever(preset),
            provider=provider,
            max_retries=2,
            fallback_to_bm25=True,
        )
        retriever.index([make_doc("C1", "code 1"), make_doc("C2", "code 2")])

        res = retriever.retrieve(make_doc("Q1", "query"))

        assert len(res) == 2
        # BM25 order preserved with score 0.0 and no fabricated LLM score
        assert res[0].target_id == "C1"
        assert res[1].target_id == "C2"
        assert res[0].score == 0.0
        assert res[1].score == 0.0
        assert res[0].metadata.get("b5_fallback") is True
        assert res[0].metadata.get("llm_score") is None
        assert retriever.retries == 2
        assert retriever.parsing_failures == 1
        assert retriever.fallback_count == 1
        assert retriever.num_llm_calls == 3

    def test_retry_exhaustion_raises_when_fallback_disabled(self):
        provider = MockLLMProvider(
            responses=[
                "Malformed 1",
                "Malformed 2",
            ]
        )
        retriever = B5RerankRetriever(
            candidate_retriever=StubCandidateRetriever([("C1", 10.0)]),
            provider=provider,
            max_retries=1,
            fallback_to_bm25=False,
        )
        retriever.index([make_doc("C1", "code 1")])

        with pytest.raises(B5ValidationError):
            retriever.retrieve(make_doc("Q1", "query"))


# ==============================================================================
# 7. Benchmark Helper Tests
# ==============================================================================


class TestB5BenchmarkHelper:
    def test_run_b5_evaluation_with_mock_provider(self):
        from tracewise.b5.benchmark import (
            format_b5_comparison_table,
            run_b5_evaluation,
        )
        from tracewise.evaluation.project import BenchmarkProject

        reqs = [
            make_doc("REQ1", "login with password"),
            make_doc("REQ2", "logout session"),
        ]
        srcs = [
            make_doc("AuthService", "login authentication password"),
            make_doc("SessionManager", "logout terminate session"),
            make_doc("UserDao", "database user lookup"),
        ]
        gt = {
            "REQ1": {"AuthService"},
            "REQ2": {"SessionManager"},
        }
        proj = BenchmarkProject(
            project_id="mini_project",
            project_name="Mini Benchmark Project",
            requirements=reqs,
            source_artifacts=srcs,
            source_files=["AuthService.py", "SessionManager.py", "UserDao.py"],
            ground_truth=gt,
        )

        mock_resp = json.dumps(
            {
                "candidates": [
                    {"target_id": "AuthService", "score": 3},
                    {"target_id": "SessionManager", "score": 3},
                    {"target_id": "UserDao", "score": 0},
                ]
            }
        )
        reranker = B5RerankRetriever(
            provider=MockLLMProvider(default_response=mock_resp),
            candidate_k=20,
        )

        result = run_b5_evaluation(proj, rerank_retriever=reranker)
        assert result.project_id == "mini_project"
        assert result.num_requirements == 2
        assert result.num_evaluable_requirements == 2
        assert result.num_zero_link_requirements == 0
        assert result.bm25_candidate_recall_at_20 == 1.0
        assert result.b5_map >= 0.0
        assert result.num_llm_calls == 2
        assert result.parsing_failures == 0

        table = format_b5_comparison_table([result])
        assert "mini_project" in table
        assert "B1 (BM25)" in table
        assert "B5 (LLM Rerank)" in table
