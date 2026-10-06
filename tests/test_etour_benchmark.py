"""Tests for Milestone 4D: Second External Benchmark Integration (eTour).

Verifies manifest parsing, dataset paths, ground-truth adapters (CSV & JSON),
granularity mapping, error detection, project ingestion validation,
denominator tracking (57 evaluable, 1 zero-link), and frozen baseline metrics.
"""

from pathlib import Path

import pytest

from tracewise.evaluation.adapters import (
    CsvGroundTruthAdapter,
    JsonGroundTruthAdapter,
    ProjectIngestionAdapter,
    RawTraceLinkRecord,
)
from tracewise.evaluation.manifest import BenchmarkProjectManifest
from tracewise.evaluation.multi_runner import MultiProjectBenchmarkRunner
from tracewise.evaluation.project import BenchmarkProject
from tracewise.evaluation.validation import (
    BenchmarkValidationError,
    validate_benchmark_project,
)
from tracewise.retrieval.bm25 import BM25Retriever
from tracewise.retrieval.semantic import SemanticRetriever
from tracewise.retrieval.structural import StructuralRetriever
from tracewise.retrieval.tfidf import TfidfRetriever

ETOUR_DIR = Path("data/benchmarks/etour")
ETOUR_MANIFEST = ETOUR_DIR / "benchmark_manifest.json"


class TestETourManifestParsing:
    """Verifies declarative manifest configuration for eTour."""

    def test_manifest_loads_and_parses_successfully(self):
        assert ETOUR_MANIFEST.is_file(), f"Manifest file missing: {ETOUR_MANIFEST}"
        manifest = BenchmarkProjectManifest.from_file(ETOUR_MANIFEST)

        assert manifest.project_id == "etour"
        assert "eTour" in manifest.project_name
        assert manifest.requirement_source == "UC/*.txt"
        assert manifest.source_path == "CC/*.java"
        assert manifest.ground_truth_path == "UC2CC.csv"
        assert manifest.ground_truth_format == "csv"
        assert manifest.requirement_artifact_type == "requirement"
        assert manifest.source_artifact_type == "source_code"
        assert manifest.chunking_config.get("strategy") == "file"
        assert manifest.chunking_config.get("granularity") == "class"
        assert manifest.chunking_config.get("use_stem_as_id") is True
        assert manifest.metadata.get("total_requirements") == 58
        assert manifest.metadata.get("evaluable_requirements") == 57
        assert manifest.metadata.get("zero_link_requirements") == 1
        assert manifest.metadata.get("source_classes") == 116
        assert manifest.metadata.get("gold_links") == 308
        assert manifest.metadata.get("dataset_variant") == (
            "eTour req2code benchmark variant sourced from the LiSSA "
            "ICSE 2025 replication package"
        )
        assert (
            manifest.metadata.get("repository_commit")
            == "a8e652f29bbdcc4bdcd3d98cd85aa4a37cb65480"
        )
        assert manifest.metadata.get("sha256_uc2cc_csv") == (
            "bb9081ab8b1a0a42614ac25a19b0c044f9ec52323c074d6cd19eee0cd6154fde"
        )
        assert "moderate size" in manifest.metadata.get("dataset_scale", "")
        assert "MIT" in manifest.metadata.get("licensing_status", "")

    def test_nonexistent_manifest_raises_error(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            BenchmarkProjectManifest.from_file(tmp_path / "nonexistent_manifest.json")


class TestETourDatasetPathsAndIntegrity:
    """Verifies filesystem paths, file counts, and encoding integrity for eTour."""

    def test_dataset_directories_and_files_exist(self):
        assert (ETOUR_DIR / "UC").is_dir()
        assert (ETOUR_DIR / "CC").is_dir()
        assert (ETOUR_DIR / "UC2CC.csv").is_file()
        assert (ETOUR_DIR / "trace_links.json").is_file()
        assert (ETOUR_DIR / "README.md").is_file()

    def test_requirement_files_count_and_extensions(self):
        uc_files = list((ETOUR_DIR / "UC").glob("*.txt"))
        assert len(uc_files) == 58
        for uc in uc_files:
            assert uc.stat().st_size > 0, f"Empty requirement file: {uc}"

    def test_source_code_files_count_and_extensions(self):
        cc_files = list((ETOUR_DIR / "CC").glob("*.java"))
        assert len(cc_files) == 116
        for cc in cc_files:
            assert cc.stat().st_size > 0, f"Empty source file: {cc}"


class TestETourGroundTruthAdapters:
    """Verifies CSV and JSON ground-truth adapters on eTour links."""

    def test_csv_adapter_loads_exact_records(self):
        adapter = CsvGroundTruthAdapter()
        records = adapter.load_raw_records(ETOUR_DIR / "UC2CC.csv")

        assert len(records) == 308
        assert all(isinstance(r, RawTraceLinkRecord) for r in records)
        assert all(r.requirement_id.startswith("UC") for r in records)
        assert all(bool(r.artifact_id) for r in records)

        mapping = adapter.load(ETOUR_DIR / "UC2CC.csv")
        assert len(mapping) == 57
        assert sum(len(targets) for targets in mapping.values()) == 308

    def test_json_adapter_loads_identical_mapping(self):
        csv_adapter = CsvGroundTruthAdapter()
        json_adapter = JsonGroundTruthAdapter()

        csv_mapping = csv_adapter.load(ETOUR_DIR / "UC2CC.csv")
        json_mapping = json_adapter.load(ETOUR_DIR / "trace_links.json")

        assert csv_mapping == json_mapping


class TestETourProjectIngestionAndValidation:
    """Verifies construction, validation rules, and error handling for eTour."""

    def test_etour_ingestion_and_validation(self):
        manifest = BenchmarkProjectManifest.from_file(ETOUR_MANIFEST)
        adapter = ProjectIngestionAdapter()
        project = adapter.ingest_project(manifest, validate=True)

        assert isinstance(project, BenchmarkProject)
        assert project.project_id == "etour"
        assert len(project.requirements) == 58
        assert len(project.source_artifacts) == 116
        assert len(project.source_files) == 116
        assert len(project.ground_truth) == 57
        assert sum(len(v) for v in project.ground_truth.values()) == 308

        report = validate_benchmark_project(project, raise_on_error=True)
        assert report.is_valid is True
        assert len(report.errors) == 0

    def test_deterministic_repeated_loading(self):
        manifest = BenchmarkProjectManifest.from_file(ETOUR_MANIFEST)
        adapter = ProjectIngestionAdapter()

        project_a = adapter.ingest_project(manifest, validate=False)
        project_b = adapter.ingest_project(manifest, validate=False)

        assert [r.source_id for r in project_a.requirements] == [
            r.source_id for r in project_b.requirements
        ]
        assert [c.source_id for c in project_a.source_artifacts] == [
            c.source_id for c in project_b.source_artifacts
        ]
        assert project_a.ground_truth == project_b.ground_truth

    def test_missing_requirement_id_in_ground_truth_raises_error(self):
        manifest = BenchmarkProjectManifest.from_file(ETOUR_MANIFEST)
        project = ProjectIngestionAdapter().ingest_project(manifest, validate=False)

        corrupted_gt = dict(project.ground_truth)
        corrupted_gt["UC999_NON_EXISTENT"] = {"AdvancedSearch"}

        corrupted_project = BenchmarkProject(
            project_id=project.project_id,
            project_name=project.project_name,
            requirements=project.requirements,
            source_artifacts=project.source_artifacts,
            source_files=project.source_files,
            ground_truth=corrupted_gt,
        )

        with pytest.raises(
            BenchmarkValidationError, match="non-existent requirement ID"
        ):
            validate_benchmark_project(corrupted_project, raise_on_error=True)

    def test_missing_target_id_in_ground_truth_raises_error(self):
        manifest = BenchmarkProjectManifest.from_file(ETOUR_MANIFEST)
        project = ProjectIngestionAdapter().ingest_project(manifest, validate=False)

        corrupted_gt = dict(project.ground_truth)
        corrupted_gt["UC1"] = {"NonExistentClass"}

        corrupted_project = BenchmarkProject(
            project_id=project.project_id,
            project_name=project.project_name,
            requirements=project.requirements,
            source_artifacts=project.source_artifacts,
            source_files=project.source_files,
            ground_truth=corrupted_gt,
        )

        with pytest.raises(
            BenchmarkValidationError, match="non-existent source target ID"
        ):
            validate_benchmark_project(corrupted_project, raise_on_error=True)


class TestETourEvaluationAndBaselineResults:
    """Verifies baseline retrieval metrics on eTour (Requirements -> Source Code)."""

    def test_etour_baseline_results_and_table_format(self):
        manifest = BenchmarkProjectManifest.from_file(ETOUR_MANIFEST)
        project = ProjectIngestionAdapter().ingest_project(manifest, validate=True)
        runner = MultiProjectBenchmarkRunner([project], k_values=(1, 3, 5))

        # B0: TF-IDF
        b0_res = runner.run(TfidfRetriever())
        p0 = b0_res.project_results["etour"]
        assert p0.num_requirements == 58
        assert p0.num_evaluable_requirements == 57
        assert p0.num_zero_link_requirements == 1
        assert p0.num_source_chunks == 116
        assert p0.num_ground_truth_links == 308

        assert round(p0.map, 4) == 0.3878
        assert round(p0.mrr, 4) == 0.6636
        assert round(p0.precision_at_k[1], 4) == 0.5263
        assert round(p0.precision_at_k[3], 4) == 0.4386
        assert round(p0.precision_at_k[5], 4) == 0.3509
        assert round(p0.recall_at_k[1], 4) == 0.1211
        assert round(p0.recall_at_k[3], 4) == 0.2686
        assert round(p0.recall_at_k[5], 4) == 0.3686

        # B1: BM25
        b1_res = runner.run(BM25Retriever())
        p1 = b1_res.project_results["etour"]
        assert round(p1.map, 4) == 0.2987
        assert round(p1.mrr, 4) == 0.5994
        assert round(p1.precision_at_k[1], 4) == 0.4035
        assert round(p1.precision_at_k[3], 4) == 0.3567
        assert round(p1.precision_at_k[5], 4) == 0.2772
        assert round(p1.recall_at_k[1], 4) == 0.0712
        assert round(p1.recall_at_k[3], 4) == 0.2332
        assert round(p1.recall_at_k[5], 4) == 0.2969

        # B2: Semantic
        b2_res = runner.run(SemanticRetriever())
        p2 = b2_res.project_results["etour"]
        assert round(p2.map, 4) == 0.4329
        assert round(p2.mrr, 4) == 0.6918
        assert round(p2.precision_at_k[1], 4) == 0.5439
        assert round(p2.precision_at_k[3], 4) == 0.4620
        assert round(p2.precision_at_k[5], 4) == 0.4035
        assert round(p2.recall_at_k[1], 4) == 0.1129
        assert round(p2.recall_at_k[3], 4) == 0.2685
        assert round(p2.recall_at_k[5], 4) == 0.3952

        # B3: Structural
        b3_res = runner.run(StructuralRetriever(alpha=0.5))
        p3 = b3_res.project_results["etour"]
        assert round(p3.map, 4) == 0.2755
        assert round(p3.mrr, 4) == 0.3210
        assert round(p3.precision_at_k[1], 4) == 0.1228
        assert round(p3.precision_at_k[3], 4) == 0.1696
        assert round(p3.precision_at_k[5], 4) == 0.1895
        assert round(p3.recall_at_k[1], 4) == 0.0319
        assert round(p3.recall_at_k[3], 4) == 0.0985
        assert round(p3.recall_at_k[5], 4) == 0.1871

        # Table formatting check
        table = b0_res.format_table()
        assert "etour" in table
        assert "58" in table
        assert "57" in table
        assert "1" in table
        assert "116" in table
        assert "308" in table
