"""Tests for Milestone 4B: Real-Project Benchmark Infrastructure."""

import json
from pathlib import Path

import pytest

from tracewise.evaluation import (
    BenchmarkProject,
    BenchmarkProjectManifest,
    BenchmarkValidationError,
    JsonGroundTruthAdapter,
    MultiProjectBenchmarkRunner,
    ProjectIngestionAdapter,
    validate_benchmark_project,
)
from tracewise.preprocessing.models import ProcessedText
from tracewise.retrieval import (
    BM25Retriever,
    SemanticRetriever,
    StructuralRetriever,
    TfidfRetriever,
)


def make_doc(source_id: str, tokens: list[str]) -> ProcessedText:
    """Helper to create minimal valid ProcessedText instances for tests."""
    text = " ".join(tokens)
    return ProcessedText(
        source_id=source_id,
        original_text=text,
        normalized_text=text,
        tokens=tokens,
    )


@pytest.fixture
def sample_project_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent / "data" / "fixtures" / "sample_project"
    )


@pytest.fixture
def sample_manifest_path(sample_project_dir: Path) -> Path:
    return sample_project_dir / "benchmark_manifest.json"


# ==============================================================================
# 1. Project Manifest Tests
# ==============================================================================


class TestBenchmarkProjectManifest:
    def test_parse_valid_json_manifest(self, sample_manifest_path: Path):
        manifest = BenchmarkProjectManifest.from_file(sample_manifest_path)
        assert manifest.project_id == "sample_project"
        assert manifest.project_name == "Sample Project (Synthetic IDP Baseline)"
        assert manifest.requirement_source == "requirements/*.md"
        assert manifest.source_path == "src/**/*.py"
        assert manifest.ground_truth_path == "trace_links.json"
        assert manifest.requirement_artifact_type == "requirement"
        assert manifest.source_artifact_type == "source_code"

    def test_parse_valid_yaml_manifest(self, tmp_path: Path):
        yaml_content = """
project_id: "test_proj"
project_name: "Test Project"
requirement_source: "reqs/*.md"
source_path: "code/*.py"
ground_truth_path: "links.json"
"""
        yaml_file = tmp_path / "manifest.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        manifest = BenchmarkProjectManifest.from_file(yaml_file)
        assert manifest.project_id == "test_proj"
        assert manifest.project_name == "Test Project"
        assert manifest.requirement_source == "reqs/*.md"
        assert manifest.root_path == str(tmp_path.resolve())

    def test_missing_manifest_file_raises_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="Manifest file not found"):
            BenchmarkProjectManifest.from_file(tmp_path / "nonexistent.json")

    def test_empty_project_id_raises_value_error(self, tmp_path: Path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text(
            json.dumps({"project_id": "", "project_name": "Test"}), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="cannot be empty"):
            BenchmarkProjectManifest.from_file(bad_file)


# ==============================================================================
# 2. Ground-Truth Adapter & Validation Tests
# ==============================================================================


class TestGroundTruthAdapterAndValidation:
    def test_load_valid_ground_truth(self, sample_project_dir: Path):
        adapter = JsonGroundTruthAdapter()
        gt = adapter.load(
            sample_project_dir / "trace_links.json",
            artifact_type="source_code",
        )
        assert len(gt) == 10
        total_links = sum(len(v) for v in gt.values())
        assert total_links == 16

    def test_malformed_json_raises_value_error(self, tmp_path: Path):
        bad_gt = tmp_path / "corrupt.json"
        bad_gt.write_text("not json content", encoding="utf-8")
        adapter = JsonGroundTruthAdapter()
        with pytest.raises(ValueError, match="Malformed JSON"):
            adapter.load(bad_gt)

    def test_missing_requirement_id_in_row_raises_value_error(self, tmp_path: Path):
        bad_gt = tmp_path / "missing_req.json"
        bad_gt.write_text(
            json.dumps(
                [{"artifact_id": "file.py#func", "artifact_type": "source_code"}]
            ),
            encoding="utf-8",
        )
        adapter = JsonGroundTruthAdapter()
        with pytest.raises(ValueError, match="missing or invalid 'requirement_id'"):
            adapter.load(bad_gt)

    def test_detect_duplicate_ground_truth_links(self):
        project = BenchmarkProject(
            project_id="dup_test",
            project_name="Duplicate Link Test",
            requirements=[make_doc("REQ-1", ["auth"])],
            source_artifacts=[make_doc("SRC-1", ["auth", "token"])],
            ground_truth={"REQ-1": {"SRC-1"}},
        )
        from tracewise.evaluation.adapters import RawTraceLinkRecord

        records = [
            RawTraceLinkRecord(requirement_id="REQ-1", artifact_id="SRC-1"),
            RawTraceLinkRecord(requirement_id="REQ-1", artifact_id="SRC-1"),
        ]
        with pytest.raises(BenchmarkValidationError, match="Duplicate ground-truth"):
            validate_benchmark_project(project, raw_records=records)

    def test_detect_missing_requirement_id_in_corpus(self):
        project = BenchmarkProject(
            project_id="missing_req_test",
            project_name="Missing Req Test",
            requirements=[make_doc("REQ-1", ["auth"])],
            source_artifacts=[make_doc("SRC-1", ["auth", "token"])],
            ground_truth={
                "REQ-999": {"SRC-1"}
            },  # REQ-999 does not exist in requirements
        )
        with pytest.raises(
            BenchmarkValidationError, match="non-existent requirement ID"
        ):
            validate_benchmark_project(project)

    def test_detect_missing_target_id_in_corpus(self):
        project = BenchmarkProject(
            project_id="missing_target_test",
            project_name="Missing Target Test",
            requirements=[make_doc("REQ-1", ["auth"])],
            source_artifacts=[make_doc("SRC-1", ["auth", "token"])],
            ground_truth={
                "REQ-1": {"SRC-MISSING"}
            },  # SRC-MISSING does not exist in chunks
        )
        with pytest.raises(
            BenchmarkValidationError, match="non-existent source target ID"
        ):
            validate_benchmark_project(project)

    def test_detect_empty_requirement_corpus(self):
        project = BenchmarkProject(
            project_id="empty_req",
            project_name="Empty Req",
            requirements=[],
            source_artifacts=[make_doc("SRC-1", ["auth"])],
            ground_truth={},
        )
        with pytest.raises(
            BenchmarkValidationError, match="Requirement corpus is empty"
        ):
            validate_benchmark_project(project)

    def test_detect_empty_source_corpus(self):
        project = BenchmarkProject(
            project_id="empty_src",
            project_name="Empty Src",
            requirements=[make_doc("REQ-1", ["auth"])],
            source_artifacts=[],
            ground_truth={},
        )
        with pytest.raises(
            BenchmarkValidationError, match="Source-code target corpus is empty"
        ):
            validate_benchmark_project(project)

    def test_detect_duplicate_requirement_ids_in_corpus(self):
        project = BenchmarkProject(
            project_id="dup_req_corpus",
            project_name="Dup Req Corpus",
            requirements=[make_doc("REQ-1", ["auth"]), make_doc("REQ-1", ["login"])],
            source_artifacts=[make_doc("SRC-1", ["auth"])],
            ground_truth={"REQ-1": {"SRC-1"}},
        )
        with pytest.raises(BenchmarkValidationError, match="Duplicate requirement IDs"):
            validate_benchmark_project(project)

    def test_detect_test_artifacts_in_source_corpus(self):
        # A source chunk that accidentally points to test code
        test_chunk = ProcessedText(
            source_id="tests/test_auth.py#test_login",
            original_text="def test_login(): pass",
            normalized_text="def test_login(): pass",
            tokens=["test", "login"],
            metadata={"artifact_type": "test_case"},
        )
        project = BenchmarkProject(
            project_id="test_in_src",
            project_name="Test In Src",
            requirements=[make_doc("REQ-1", ["auth"])],
            source_artifacts=[test_chunk],
            ground_truth={},
        )
        with pytest.raises(BenchmarkValidationError, match="Test artifacts detected"):
            validate_benchmark_project(project)


# ==============================================================================
# 3. Project Ingestion Adapter Tests
# ==============================================================================


class TestProjectIngestionAdapter:
    def test_ingest_sample_project_from_manifest(self, sample_manifest_path: Path):
        project = ProjectIngestionAdapter.from_manifest_file(sample_manifest_path)
        assert project.project_id == "sample_project"
        assert project.num_requirements == 10
        assert project.num_source_chunks == 26
        assert project.num_source_files == 8
        assert project.num_ground_truth_links == 16


# ==============================================================================
# 4. Multi-Project Execution & Aggregation Tests
# ==============================================================================


class TestMultiProjectBenchmarkExecution:
    @pytest.fixture
    def two_projects(self) -> tuple[BenchmarkProject, BenchmarkProject]:
        # Project Alpha: 2 requirements, 3 source chunks, 2 links
        p_alpha = BenchmarkProject(
            project_id="alpha",
            project_name="Project Alpha",
            requirements=[
                make_doc("REQ-A1", ["auth", "token"]),
                make_doc("REQ-A2", ["database", "pool"]),
            ],
            source_artifacts=[
                make_doc("SRC-A1", ["auth", "token", "service"]),
                make_doc("SRC-A2", ["database", "pool", "connect"]),
                make_doc("SRC-A3", ["unrelated", "noise"]),
            ],
            source_files=["src/auth.py", "src/db.py"],
            ground_truth={
                "REQ-A1": {"SRC-A1"},
                "REQ-A2": {"SRC-A2"},
            },
        )

        # Project Beta: 1 requirement, 2 source chunks, 1 link
        p_beta = BenchmarkProject(
            project_id="beta",
            project_name="Project Beta",
            requirements=[
                make_doc("REQ-B1", ["cache", "redis"]),
            ],
            source_artifacts=[
                make_doc("SRC-B1", ["cache", "redis", "client"]),
                make_doc("SRC-B2", ["unrelated", "noise"]),
            ],
            source_files=["src/cache.py"],
            ground_truth={
                "REQ-B1": {"SRC-B1"},
            },
        )
        return p_alpha, p_beta

    def test_multi_project_execution_isolation(
        self, two_projects: tuple[BenchmarkProject, BenchmarkProject]
    ):
        p_alpha, p_beta = two_projects
        runner = MultiProjectBenchmarkRunner([p_alpha, p_beta])
        result = runner.run(TfidfRetriever())

        assert len(result.project_results) == 2
        assert "alpha" in result.project_results
        assert "beta" in result.project_results

        res_alpha = result.project_results["alpha"]
        res_beta = result.project_results["beta"]

        assert res_alpha.num_requirements == 2
        assert res_alpha.num_source_chunks == 3
        assert res_beta.num_requirements == 1
        assert res_beta.num_source_chunks == 2

        # Verify perfect lexical matching on both projects
        assert res_alpha.map == 1.0
        assert res_beta.map == 1.0
        assert result.macro_aggregates["map"] == 1.0
        assert result.micro_aggregates["map"] == 1.0

    def test_macro_vs_micro_aggregation_with_different_scores(self):
        # Project 1 has 1 query with MAP = 1.0
        p1 = BenchmarkProject(
            project_id="p1",
            project_name="Project 1",
            requirements=[make_doc("Q1", ["match"])],
            source_artifacts=[make_doc("T1", ["match"])],
            ground_truth={"Q1": {"T1"}},
        )
        # Project 2 has 2 queries: Q2 has AP = 1.0, Q3 has AP = 0.0 (top_k=1)
        # Therefore project 2 MAP = 0.5
        p2 = BenchmarkProject(
            project_id="p2",
            project_name="Project 2",
            requirements=[
                make_doc("Q2", ["match"]),
                make_doc("Q3", ["distractor"]),
            ],
            source_artifacts=[
                make_doc("T2_match", ["match"]),
                make_doc("T2_distract", ["distractor"]),
                make_doc("T2_target", ["unrelated"]),
            ],
            ground_truth={"Q2": {"T2_match"}, "Q3": {"T2_target"}},
        )

        runner = MultiProjectBenchmarkRunner([p1, p2])
        res = runner.run(TfidfRetriever(), top_k=1)

        # Project 1 MAP = 1.0
        # Project 2 MAP = (1.0 + 0.0) / 2 = 0.5
        # Macro-MAP = (1.0 + 0.5) / 2 = 0.75
        # Micro-MAP (pooled across 3 queries) = (1.0 + 1.0 + 0.0) / 3 = 2/3 ≈ 0.6667
        assert res.project_results["p1"].map == pytest.approx(1.0, abs=1e-5)
        assert res.project_results["p2"].map == pytest.approx(0.5, abs=1e-5)
        assert res.macro_aggregates["map"] == pytest.approx(0.75, abs=1e-5)
        assert res.micro_aggregates["map"] == pytest.approx(2.0 / 3.0, abs=1e-4)

    def test_scalability_telemetry_collected(
        self, two_projects: tuple[BenchmarkProject, BenchmarkProject]
    ):
        p_alpha, p_beta = two_projects
        runner = MultiProjectBenchmarkRunner([p_alpha, p_beta])
        res = runner.run(TfidfRetriever())

        assert res.total_runtime_sec > 0.0
        for p_res in res.project_results.values():
            assert p_res.indexing_time_sec >= 0.0
            assert p_res.query_time_sec >= 0.0
            assert p_res.total_time_sec >= 0.0
            assert p_res.num_candidates_evaluated > 0

    def test_duplicate_project_id_raises_value_error(
        self, two_projects: tuple[BenchmarkProject, BenchmarkProject]
    ):
        p_alpha, _ = two_projects
        # Two projects with identical project_id
        with pytest.raises(ValueError, match="Duplicate project_id"):
            MultiProjectBenchmarkRunner([p_alpha, p_alpha])


# ==============================================================================
# 5. Exact Regression Against Current Synthetic Benchmark
# ==============================================================================


class TestSampleProjectExactRegression:
    @pytest.fixture
    def sample_project(self, sample_manifest_path: Path) -> BenchmarkProject:
        return ProjectIngestionAdapter.from_manifest_file(sample_manifest_path)

    def test_b0_tfidf_regression(self, sample_project: BenchmarkProject):
        runner = MultiProjectBenchmarkRunner([sample_project])
        result = runner.run(TfidfRetriever(), artifact_type_filter="source_code")
        p_res = result.project_results["sample_project"]

        # Exact frozen metrics:
        assert p_res.map == pytest.approx(0.7485, abs=1e-3)
        assert p_res.mrr == pytest.approx(0.8500, abs=1e-3)

        assert p_res.precision_at_k[1] == pytest.approx(0.8000, abs=1e-3)
        assert p_res.precision_at_k[3] == pytest.approx(0.3667, abs=1e-3)
        assert p_res.precision_at_k[5] == pytest.approx(0.2400, abs=1e-3)

        assert p_res.recall_at_k[1] == pytest.approx(0.5500, abs=1e-3)
        assert p_res.recall_at_k[3] == pytest.approx(0.7500, abs=1e-3)
        assert p_res.recall_at_k[5] == pytest.approx(0.8000, abs=1e-3)

        # Macro aggregates must match single project results exactly
        assert result.macro_aggregates["map"] == pytest.approx(0.7485, abs=1e-3)
        assert result.micro_aggregates["map"] == pytest.approx(0.7485, abs=1e-3)

    def test_b1_bm25_regression(self, sample_project: BenchmarkProject):
        runner = MultiProjectBenchmarkRunner([sample_project])
        result = runner.run(
            BM25Retriever(k1=1.5, b=0.75), artifact_type_filter="source_code"
        )
        p_res = result.project_results["sample_project"]

        # Exact frozen metrics:
        assert p_res.map == pytest.approx(0.7030, abs=1e-3)
        assert p_res.mrr == pytest.approx(0.8033, abs=1e-3)

        assert p_res.precision_at_k[1] == pytest.approx(0.7000, abs=1e-3)
        assert p_res.precision_at_k[3] == pytest.approx(0.3333, abs=1e-3)
        assert p_res.precision_at_k[5] == pytest.approx(0.2600, abs=1e-3)

        assert p_res.recall_at_k[1] == pytest.approx(0.5000, abs=1e-3)
        assert p_res.recall_at_k[3] == pytest.approx(0.7000, abs=1e-3)
        assert p_res.recall_at_k[5] == pytest.approx(0.8500, abs=1e-3)

    def test_b2_semantic_regression(self, sample_project: BenchmarkProject):
        runner = MultiProjectBenchmarkRunner([sample_project])
        result = runner.run(
            SemanticRetriever(model_name="sentence-transformers/all-MiniLM-L6-v2"),
            artifact_type_filter="source_code",
        )
        p_res = result.project_results["sample_project"]

        # Exact frozen metrics:
        assert p_res.map == pytest.approx(0.7350, abs=1e-3)
        assert p_res.mrr == pytest.approx(0.8500, abs=1e-3)

        assert p_res.precision_at_k[1] == pytest.approx(0.7000, abs=1e-3)
        assert p_res.precision_at_k[3] == pytest.approx(0.4333, abs=1e-3)
        assert p_res.precision_at_k[5] == pytest.approx(0.2800, abs=1e-3)

        assert p_res.recall_at_k[1] == pytest.approx(0.4500, abs=1e-3)
        assert p_res.recall_at_k[3] == pytest.approx(0.8500, abs=1e-3)
        assert p_res.recall_at_k[5] == pytest.approx(0.9000, abs=1e-3)

    def test_b3_structural_regression(self, sample_project: BenchmarkProject):
        runner = MultiProjectBenchmarkRunner([sample_project])
        result = runner.run(
            StructuralRetriever(alpha=0.5),
            artifact_type_filter="source_code",
        )
        p_res = result.project_results["sample_project"]

        # Exact frozen metrics for B3:
        assert p_res.map == pytest.approx(0.3977, abs=1e-3)
        assert p_res.mrr == pytest.approx(0.4333, abs=1e-3)

        assert p_res.precision_at_k[1] == pytest.approx(0.2000, abs=1e-3)
        assert p_res.precision_at_k[3] == pytest.approx(0.2000, abs=1e-3)
        assert p_res.precision_at_k[5] == pytest.approx(0.2200, abs=1e-3)

        assert p_res.recall_at_k[1] == pytest.approx(0.1000, abs=1e-3)
        assert p_res.recall_at_k[3] == pytest.approx(0.4000, abs=1e-3)
        assert p_res.recall_at_k[5] == pytest.approx(0.7000, abs=1e-3)
