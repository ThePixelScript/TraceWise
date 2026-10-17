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


class TestCandidateEvidenceMetadata:
    """Verifies ranking evidence and transparency metadata enrichment
    (Milestone B6.3).
    """

    @pytest.fixture
    def service(self) -> TraceWiseService:
        return TraceWiseService()

    def test_b0_tfidf_evidence_metadata(self, service: TraceWiseService) -> None:
        res = service.get_candidates(
            "sample_project", "REQ-001", method="b0_tfidf", top_k=3
        )
        cand = res["candidates"][0]
        meta = cand["metadata"]
        assert meta["retrieval_method"] == "b0_tfidf"
        assert "Cosine Similarity" in meta["similarity_metric"]
        assert isinstance(meta["matched_terms"], list)
        assert meta["matched_terms_count"] == len(meta["matched_terms"])
        assert meta["query_terms_count"] > 0
        assert meta["target_token_count"] > 0
        assert "is_gold_link" not in meta

    def test_b1_bm25_evidence_metadata(self, service: TraceWiseService) -> None:
        res = service.get_candidates(
            "sample_project", "REQ-001", method="b1_bm25", top_k=3
        )
        cand = res["candidates"][0]
        meta = cand["metadata"]
        assert meta["retrieval_method"] == "b1_bm25"
        assert meta["bm25_k1"] == 1.5
        assert meta["bm25_b"] == 0.75
        assert isinstance(meta["matched_terms"], list)
        assert meta["matched_terms_count"] > 0
        assert meta["target_token_count"] > 0
        assert "is_gold_link" not in meta

    def test_b2_semantic_evidence_metadata(self, service: TraceWiseService) -> None:
        res = service.get_candidates(
            "sample_project", "REQ-001", method="b2_semantic", top_k=3
        )
        cand = res["candidates"][0]
        meta = cand["metadata"]
        assert meta["retrieval_method"] == "b2_semantic"
        assert "all-MiniLM-L6-v2" in meta["embedding_model"]
        assert meta["similarity_metric"] == "Dense Cosine Similarity"
        assert meta["vector_dimension"] == 384
        assert "is_gold_link" not in meta

    def test_b3_structural_evidence_metadata(self, service: TraceWiseService) -> None:
        res = service.get_candidates(
            "sample_project", "REQ-001", method="b3_structural", top_k=3
        )
        cand = res["candidates"][0]
        meta = cand["metadata"]
        assert meta["retrieval_method"] == "b3_structural"
        assert meta["alpha"] == 0.5
        assert "seed_score" in meta
        assert "graph_score" in meta
        assert "degree" in meta
        assert isinstance(meta["seed_score"], float)
        assert isinstance(meta["graph_score"], float)
        assert isinstance(meta["degree"], int)
        assert "is_gold_link" not in meta

    def test_b4_hybrid_evidence_metadata(self, service: TraceWiseService) -> None:
        res = service.get_candidates(
            "sample_project", "REQ-001", method="b4_hybrid", top_k=3
        )
        cand = res["candidates"][0]
        meta = cand["metadata"]
        assert meta["retrieval_method"] == "b4_hybrid"
        assert meta["rrf_k"] == 60
        assert "component_ranks" in meta
        assert "component_contributions" in meta
        assert "tfidf" in meta["component_contributions"]
        assert "semantic" in meta["component_contributions"]
        assert "structural" in meta["component_contributions"]
        assert "is_gold_link" not in meta

    def test_b5_llm_rerank_evidence_metadata(self, service: TraceWiseService) -> None:
        res = service.get_candidates(
            "sample_project", "REQ-001", method="b5_llm_rerank", top_k=3
        )
        cand = res["candidates"][0]
        meta = cand["metadata"]
        assert meta["retrieval_method"] == "b5_llm_rerank"
        assert "bm25_score" in meta
        assert "bm25_rank" in meta
        assert "llm_score" in meta
        assert "b5_fallback" in meta
        assert "qwen3.5:9b" in meta["reranker_model"]
        assert "is_gold_link" not in meta

    def test_evidence_metadata_blinded_in_developer_mode(
        self, service: TraceWiseService
    ) -> None:
        methods = [
            "b0_tfidf",
            "b1_bm25",
            "b2_semantic",
            "b3_structural",
            "b4_hybrid",
            "b5_llm_rerank",
        ]
        for m in methods:
            res = service.get_candidates(
                "sample_project", "REQ-001", method=m, top_k=3, mode="developer"
            )
            for cand in res["candidates"]:
                assert cand["is_gold_link"] is None
                assert "is_gold_link" not in cand["metadata"]
                assert "gold_links" not in cand["metadata"]

    def test_b2_and_b4_catalog_metadata(self, service: TraceWiseService) -> None:
        methods = {m["id"]: m for m in service.get_supported_methods()}
        assert "b2_semantic" in methods
        b2 = methods["b2_semantic"]
        assert "all-MiniLM-L6-v2" in b2["parameters"]["model"]
        assert "all-MiniLM-L6-v2" in b2["description"]

        assert "b4_hybrid" in methods
        b4 = methods["b4_hybrid"]
        assert b4["parameters"]["rrf_k"] == 60
        assert b4["parameters"]["components"] == [
            "b0_tfidf",
            "b2_semantic",
            "b3_structural",
        ]
        assert "B0 TF-IDF" in b4["description"]
        assert "B2 Semantic" in b4["description"]
        assert "B3 Structural" in b4["description"]

    def test_developer_only_service_enforces_blinding(self) -> None:
        dev_service = TraceWiseService(developer_only=True)
        assert dev_service.developer_only is True

        # Mode coercion: even when client requests "evaluation", developer mode
        # is enforced
        projects = dev_service.get_projects(mode="evaluation")
        for p in projects:
            assert p["num_ground_truth_links"] is None

        detail = dev_service.get_project_details("sample_project", mode="evaluation")
        assert detail["mode"] == "developer"
        assert detail["num_evaluable_requirements"] is None
        assert detail["num_zero_link_requirements"] is None
        assert detail["num_ground_truth_links"] is None
        assert "gold_links" not in detail["metadata"]
        assert "evaluable_requirements" not in detail["metadata"]
        assert "zero_link_requirements" not in detail["metadata"]
        assert "description" not in detail["metadata"]

        reqs = dev_service.get_requirements("sample_project", mode="evaluation")
        for r in reqs:
            assert r["gold_link_count"] is None
            assert r["is_evaluable"] is None

        req_detail = dev_service.get_requirement_detail(
            "sample_project", "REQ-001", mode="evaluation"
        )
        assert req_detail["mode"] == "developer"
        assert req_detail["gold_links"] is None
        assert req_detail["gold_link_count"] is None
        assert req_detail["is_evaluable"] is None

        cands = dev_service.get_candidates(
            "sample_project", "REQ-001", method="b1_bm25", mode="evaluation"
        )
        assert cands["mode"] == "developer"
        assert cands["gold_links_retrieved"] is None
        assert cands["total_gold_links"] is None
        assert cands["is_evaluable"] is None
        assert cands["gold_link_targets"] is None
        for c in cands["candidates"]:
            assert c["is_gold_link"] is None

    def test_standard_service_allows_research_mode(self) -> None:
        std_service = TraceWiseService(developer_only=False)
        assert std_service.developer_only is False

        # In standard mode, research/evaluation mode exposes ground truth as designed
        projects = std_service.get_projects(mode="evaluation")
        sample_p = next(p for p in projects if p["project_id"] == "sample_project")
        assert sample_p["num_ground_truth_links"] == 16

        detail = std_service.get_project_details("sample_project", mode="evaluation")
        assert detail["mode"] == "evaluation"
        assert detail["num_ground_truth_links"] == 16
        assert detail["num_evaluable_requirements"] == 10
        assert detail["num_zero_link_requirements"] == 0

        reqs = std_service.get_requirements("sample_project", mode="evaluation")
        req1 = next(r for r in reqs if r["requirement_id"] == "REQ-001")
        assert req1["gold_link_count"] == 1
        assert req1["is_evaluable"] is True

        req_detail = std_service.get_requirement_detail(
            "sample_project", "REQ-001", mode="evaluation"
        )
        assert req_detail["gold_links"] == [
            "src/auth/service.py#AuthenticationService.authenticate_user",
        ]
        assert req_detail["gold_link_count"] == 1
        assert req_detail["is_evaluable"] is True

        cands = std_service.get_candidates(
            "sample_project", "REQ-001", method="b1_bm25", mode="evaluation"
        )
        assert cands["total_gold_links"] == 1
        assert isinstance(cands["gold_links_retrieved"], int)
        assert len(cands["gold_link_targets"]) == 1
