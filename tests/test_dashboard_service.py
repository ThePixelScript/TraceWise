"""Tests for TraceWise Dashboard service layer."""

import pytest

from tracewise.dashboard.service import (
    TraceWiseService,
    extract_title_from_requirement,
)


class TestExtractTitleHelper:
    """Verifies title extraction logic across various requirement text formats."""

    def test_extracts_markdown_section_title(self) -> None:
        text = (
            "# REQ-001\n\n## Title\n\nUser Authentication via Email\n\n## Description\n"
        )
        title = extract_title_from_requirement(text, "REQ-001")
        assert title == "User Authentication via Email"

    def test_extracts_use_case_name(self) -> None:
        text = "Use case name: DeleteCulturalHeritage \nDescription: Delete object..."
        title = extract_title_from_requirement(text, "UC1")
        assert title == "DeleteCulturalHeritage"

    def test_extracts_first_meaningful_line_when_no_header(self) -> None:
        text = "The system shall allow users to reset their passwords securely."
        title = extract_title_from_requirement(text, "REQ-005")
        assert (
            title == "The system shall allow users to reset their passwords securely."
        )

    def test_falls_back_to_id_when_empty_or_whitespace(self) -> None:
        assert extract_title_from_requirement("", "REQ-999") == "REQ-999"
        assert extract_title_from_requirement("   \n\n  ", "REQ-999") == "REQ-999"


class TestTraceWiseServiceProjects:
    """Verifies project discovery, ingestion caching, and metadata reporting."""

    @pytest.fixture
    def service(self) -> TraceWiseService:
        return TraceWiseService()

    def test_get_supported_methods(self, service: TraceWiseService) -> None:
        methods = service.get_supported_methods()
        method_ids = [m["id"] for m in methods]
        assert "b0_tfidf" in method_ids
        assert "b1_bm25" in method_ids
        assert "b2_semantic" in method_ids
        assert "b3_structural" in method_ids
        assert "b4_hybrid" in method_ids
        assert "b5_llm_rerank" in method_ids

    def test_get_projects_returns_all_datasets(self, service: TraceWiseService) -> None:
        projects = service.get_projects()
        pids = [p["project_id"] for p in projects]
        assert "sample_project" in pids
        assert "itrust" in pids
        assert "etour" in pids

        sample = next(p for p in projects if p["project_id"] == "sample_project")
        assert sample["num_requirements"] == 10
        assert sample["num_source_chunks"] == 26
        assert sample["num_ground_truth_links"] == 16
        assert sample["has_b5_checkpoint"] is True

    def test_get_project_details_sample_project(
        self, service: TraceWiseService
    ) -> None:
        details = service.get_project_details("sample_project")
        assert details["project_id"] == "sample_project"
        assert details["num_requirements"] == 10
        assert details["num_evaluable_requirements"] == 10
        assert details["num_zero_link_requirements"] == 0
        assert "chunking_config" in details["configuration"]

    def test_get_project_details_unknown_raises_key_error(
        self, service: TraceWiseService
    ) -> None:
        with pytest.raises(KeyError, match="not found"):
            service.get_project_details("non_existent_project")


class TestTraceWiseServiceRequirements:
    """Verifies requirement listing and individual specification lookup."""

    @pytest.fixture
    def service(self) -> TraceWiseService:
        return TraceWiseService()

    def test_get_requirements_sample_project(self, service: TraceWiseService) -> None:
        reqs = service.get_requirements("sample_project")
        assert len(reqs) == 10
        req_ids = [r["requirement_id"] for r in reqs]
        assert "REQ-001" in req_ids
        assert "REQ-010" in req_ids

        req1 = next(r for r in reqs if r["requirement_id"] == "REQ-001")
        assert req1["title"] == "User Authentication via Email and Password"
        assert req1["gold_link_count"] > 0
        assert req1["is_evaluable"] is True

    def test_get_requirement_detail_sample_project(
        self, service: TraceWiseService
    ) -> None:
        detail = service.get_requirement_detail("sample_project", "REQ-001")
        assert detail["requirement_id"] == "REQ-001"
        assert "authenticate users" in detail["text"]
        assert len(detail["gold_links"]) > 0
        assert (
            "src/auth/service.py#AuthenticationService.authenticate_user"
            in detail["gold_links"]
        )
        assert detail["is_evaluable"] is True

    def test_get_requirement_detail_unknown_req_raises_key_error(
        self, service: TraceWiseService
    ) -> None:
        with pytest.raises(KeyError, match="not found"):
            service.get_requirement_detail("sample_project", "UNKNOWN-REQ")


class TestTraceWiseServiceCandidateRetrieval:
    """Verifies retrieval, B5 checkpointing, and verification isolation."""

    @pytest.fixture
    def service(self) -> TraceWiseService:
        return TraceWiseService()

    def test_retrieve_candidates_b1_bm25(self, service: TraceWiseService) -> None:
        result = service.get_candidates(
            project_id="sample_project",
            requirement_id="REQ-001",
            method="b1_bm25",
            top_k=5,
        )
        assert result["project_id"] == "sample_project"
        assert result["requirement_id"] == "REQ-001"
        assert result["method"] == "b1_bm25"
        assert len(result["candidates"]) == 5

        # Check candidate structure and verification isolation
        cand = result["candidates"][0]
        assert cand["rank"] == 1
        assert isinstance(cand["score"], float)
        assert cand["target_id"].startswith("src/")
        assert cand["candidate_type"] == "retrieval_hypothesis"
        assert cand["developer_verification_status"] == "unverified"
        assert "Milestone B6" in cand["developer_verification_note"]
        assert isinstance(cand["is_gold_link"], bool)
        assert len(cand["code_preview"]) > 0
        assert cand["code_lines"] > 0

    def test_retrieve_candidates_b0_tfidf(self, service: TraceWiseService) -> None:
        result = service.get_candidates(
            project_id="sample_project",
            requirement_id="REQ-001",
            method="b0_tfidf",
            top_k=3,
        )
        assert len(result["candidates"]) == 3
        assert result["candidates"][0]["retriever_name"] == "tfidf_cosine"

    def test_retrieve_candidates_b5_from_checkpoint(
        self, service: TraceWiseService
    ) -> None:
        result = service.get_candidates(
            project_id="sample_project",
            requirement_id="REQ-001",
            method="b5_llm_rerank",
            top_k=5,
        )
        assert result["is_cached"] is True
        assert len(result["candidates"]) == 5

        cand1 = result["candidates"][0]
        assert cand1["retriever_name"] == "b5_llm_rerank"
        assert "llm_score" in cand1["metadata"]
        assert "bm25_rank" in cand1["metadata"]
        assert cand1["candidate_type"] == "retrieval_hypothesis"
        assert cand1["developer_verification_status"] == "unverified"

    def test_retrieve_candidates_invalid_top_k(self, service: TraceWiseService) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            service.get_candidates(
                project_id="sample_project",
                requirement_id="REQ-001",
                method="b1_bm25",
                top_k=0,
            )

    def test_retrieve_candidates_unknown_method(
        self, service: TraceWiseService
    ) -> None:
        with pytest.raises(ValueError, match="Unknown retrieval method"):
            service.get_candidates(
                project_id="sample_project",
                requirement_id="REQ-001",
                method="non_existent_method",
                top_k=5,
            )

    def test_developer_mode_isolates_ground_truth_in_candidates(
        self, service: TraceWiseService
    ) -> None:
        result = service.get_candidates(
            project_id="sample_project",
            requirement_id="REQ-001",
            method="b1_bm25",
            top_k=5,
            mode="developer",
        )
        assert result["mode"] == "developer"
        assert result["gold_links_retrieved"] is None
        assert result["total_gold_links"] is None
        assert result["gold_link_targets"] is None
        assert result["is_evaluable"] is None

        for cand in result["candidates"]:
            assert cand["is_gold_link"] is None
            assert cand["candidate_type"] == "retrieval_hypothesis"
            assert cand["developer_verification_status"] == "unverified"

    def test_developer_mode_isolates_ground_truth_in_requirements(
        self, service: TraceWiseService
    ) -> None:
        reqs = service.get_requirements("sample_project", mode="developer")
        for r in reqs:
            assert r["gold_link_count"] is None
            assert r["is_evaluable"] is None

    def test_developer_mode_isolates_ground_truth_in_requirement_detail(
        self, service: TraceWiseService
    ) -> None:
        detail = service.get_requirement_detail(
            "sample_project", "REQ-001", mode="developer"
        )
        assert detail["mode"] == "developer"
        assert detail["gold_links"] is None
        assert detail["gold_link_count"] is None
        assert detail["is_evaluable"] is None

    def test_invalid_mode_raises_value_error(self, service: TraceWiseService) -> None:
        with pytest.raises(ValueError, match="Invalid mode"):
            service.get_candidates(
                project_id="sample_project",
                requirement_id="REQ-001",
                mode="invalid_mode",
            )
