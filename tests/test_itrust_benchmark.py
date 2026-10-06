"""Tests for Milestone 4C: First Real-Project Dataset Integration (iTrust).

Verifies manifest parsing, path validation, ground-truth adapters (CSV & JSON),
granularity mapping, error detection, benchmark project construction,
deterministic loading, and synthetic baseline regression invariants.
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
from tracewise.ingestion.file_chunker import FileChunker
from tracewise.models.artifact import Artifact, ArtifactType
from tracewise.retrieval.bm25 import BM25Retriever
from tracewise.retrieval.hybrid import HybridRetriever
from tracewise.retrieval.semantic import SemanticRetriever
from tracewise.retrieval.structural import StructuralRetriever
from tracewise.retrieval.tfidf import TfidfRetriever

ITRUST_DIR = Path("data/benchmarks/itrust")
ITRUST_MANIFEST = ITRUST_DIR / "benchmark_manifest.json"
SAMPLE_MANIFEST = Path("data/fixtures/sample_project/benchmark_manifest.json")


class TestITrustManifestParsing:
    """Verifies declarative manifest configuration for iTrust."""

    def test_manifest_loads_and_parses_successfully(self):
        assert ITRUST_MANIFEST.is_file(), f"Manifest file missing: {ITRUST_MANIFEST}"
        manifest = BenchmarkProjectManifest.from_file(ITRUST_MANIFEST)

        assert manifest.project_id == "itrust"
        assert "iTrust" in manifest.project_name
        assert manifest.requirement_source == "UC/*.txt"
        assert manifest.source_path == "CC/*.java"
        assert manifest.ground_truth_path == "UC2JAVA.csv"
        assert manifest.ground_truth_format == "csv"
        assert manifest.requirement_artifact_type == "requirement"
        assert manifest.source_artifact_type == "source_code"
        assert manifest.chunking_config.get("strategy") == "file"
        assert manifest.chunking_config.get("granularity") == "class"
        assert manifest.chunking_config.get("use_stem_as_id") is True
        assert manifest.metadata.get("total_requirements") == 131
        assert manifest.metadata.get("evaluable_requirements") == 105
        assert manifest.metadata.get("zero_link_requirements") == 26
        assert manifest.metadata.get("source_classes") == 226
        assert manifest.metadata.get("gold_links") == 286
        assert manifest.metadata.get("dataset_variant") == (
            "iTrust req2code benchmark variant sourced from the LiSSA "
            "ICSE 2025 replication package"
        )
        assert (
            manifest.metadata.get("repository_commit")
            == "a8e652f29bbdcc4bdcd3d98cd85aa4a37cb65480"
        )
        assert manifest.metadata.get("sha256_uc2java_csv") == (
            "36e57100b6fa0066252b0b147bc79f5424e1fe739ca4c50d66f67fbbba9a6acd"
        )
        assert "moderate size" in manifest.metadata.get("dataset_scale", "")
        assert "MIT" in manifest.metadata.get("licensing_status", "")

    def test_nonexistent_manifest_raises_error(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            BenchmarkProjectManifest.from_file(tmp_path / "nonexistent_manifest.json")


class TestITrustDatasetPathsAndIntegrity:
    """Verifies filesystem paths, file counts, and encoding integrity for iTrust."""

    def test_dataset_directories_and_files_exist(self):
        assert (ITRUST_DIR / "UC").is_dir()
        assert (ITRUST_DIR / "CC").is_dir()
        assert (ITRUST_DIR / "UC2JAVA.csv").is_file()
        assert (ITRUST_DIR / "trace_links.json").is_file()
        assert (ITRUST_DIR / "README.md").is_file()

    def test_requirement_files_count_and_extensions(self):
        uc_files = list((ITRUST_DIR / "UC").glob("*.txt"))
        assert len(uc_files) == 131
        for uc in uc_files:
            assert uc.stat().st_size > 0, f"Empty requirement file: {uc}"

    def test_source_code_files_count_and_extensions(self):
        cc_files = list((ITRUST_DIR / "CC").glob("*.java"))
        assert len(cc_files) == 226
        for cc in cc_files:
            assert cc.stat().st_size > 0, f"Empty source file: {cc}"


class TestGroundTruthAdapters:
    """Verifies CSV and JSON ground-truth adapters on canonical iTrust links."""

    def test_csv_adapter_loads_exact_records(self):
        adapter = CsvGroundTruthAdapter()
        records = adapter.load_raw_records(ITRUST_DIR / "UC2JAVA.csv")

        assert len(records) == 286
        assert all(isinstance(r, RawTraceLinkRecord) for r in records)
        assert all(r.requirement_id.startswith("UC") for r in records)
        assert all(bool(r.artifact_id) for r in records)

        mapping = adapter.load(ITRUST_DIR / "UC2JAVA.csv")
        assert len(mapping) == 105
        assert sum(len(targets) for targets in mapping.values()) == 286

    def test_json_adapter_loads_identical_mapping(self):
        csv_adapter = CsvGroundTruthAdapter()
        json_adapter = JsonGroundTruthAdapter()

        csv_mapping = csv_adapter.load(ITRUST_DIR / "UC2JAVA.csv")
        json_mapping = json_adapter.load(ITRUST_DIR / "trace_links.json")

        assert csv_mapping == json_mapping

    def test_csv_adapter_header_support(self, tmp_path: Path):
        csv_file = tmp_path / "headered.csv"
        csv_file.write_text(
            "requirement_id,artifact_id,artifact_type\n"
            "UC1S1,AddPatientAction,source_code\n"
            "UC1S1,PatientDAO,source_code\n",
            encoding="utf-8",
        )
        adapter = CsvGroundTruthAdapter()
        records = adapter.load_raw_records(csv_file)
        assert len(records) == 2
        assert records[0].requirement_id == "UC1S1"
        assert records[0].artifact_id == "AddPatientAction"

    def test_csv_adapter_malformed_rows(self, tmp_path: Path):
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text("UC1S1\n", encoding="utf-8")
        adapter = CsvGroundTruthAdapter()
        with pytest.raises(ValueError, match="expected at least 2 columns"):
            adapter.load_raw_records(csv_file)

    def test_missing_ground_truth_file_raises_error(self, tmp_path: Path):
        adapter = CsvGroundTruthAdapter()
        with pytest.raises(FileNotFoundError):
            adapter.load_raw_records(tmp_path / "missing.csv")


class TestGranularityMappingAndFileChunker:
    """Verifies that FileChunker produces exact class-level granularity chunks."""

    def test_file_chunker_stem_mode(self):
        chunker = FileChunker(use_stem_as_id=True)
        art = Artifact(
            id="CC/AddPatientAction.java",
            file_path="CC/AddPatientAction.java",
            raw_content="package edu.ncsu;\npublic class AddPatientAction {}\n",
            content="package edu.ncsu;\npublic class AddPatientAction {}\n",
            artifact_type=ArtifactType.SOURCE_CODE,
        )
        chunks = chunker.chunk(art)
        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.id == "AddPatientAction"
        assert chunk.name == "AddPatientAction"
        assert chunk.parent_id == "CC/AddPatientAction.java"
        assert chunk.start_line == 1
        assert chunk.end_line == 2
        assert chunk.metadata.get("granularity") == "class"

    def test_file_chunker_path_mode(self):
        chunker = FileChunker(use_stem_as_id=False)
        art = Artifact(
            id="CC/AddPatientAction.java",
            file_path="CC/AddPatientAction.java",
            raw_content="public class AddPatientAction {}",
            content="public class AddPatientAction {}",
            artifact_type=ArtifactType.SOURCE_CODE,
        )
        chunks = chunker.chunk(art)
        assert len(chunks) == 1
        assert chunks[0].id == "CC/AddPatientAction.java"
        assert chunks[0].metadata.get("granularity") == "file"

    def test_file_chunker_empty_file_yields_no_chunks(self):
        chunker = FileChunker()
        art = Artifact(
            id="CC/Empty.java",
            file_path="CC/Empty.java",
            raw_content="   \n  \t  ",
            content="   \n  \t  ",
            artifact_type=ArtifactType.SOURCE_CODE,
        )
        assert chunker.chunk(art) == []


class TestProjectIngestionAndValidation:
    """Verifies construction, validation rules, and error handling for iTrust."""

    def test_itrust_ingestion_and_validation(self):
        manifest = BenchmarkProjectManifest.from_file(ITRUST_MANIFEST)
        adapter = ProjectIngestionAdapter()
        project = adapter.ingest_project(manifest, validate=True)

        assert isinstance(project, BenchmarkProject)
        assert project.project_id == "itrust"
        assert len(project.requirements) == 131
        assert len(project.source_artifacts) == 226
        assert len(project.source_files) == 226
        assert len(project.ground_truth) == 105
        assert sum(len(v) for v in project.ground_truth.values()) == 286

        # Check report
        report = validate_benchmark_project(project, raise_on_error=True)
        assert report.is_valid is True
        assert len(report.errors) == 0

    def test_deterministic_repeated_loading(self):
        manifest = BenchmarkProjectManifest.from_file(ITRUST_MANIFEST)
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
        manifest = BenchmarkProjectManifest.from_file(ITRUST_MANIFEST)
        project = ProjectIngestionAdapter().ingest_project(manifest, validate=False)

        # Inject non-existent requirement ID into ground truth
        corrupted_gt = dict(project.ground_truth)
        corrupted_gt["UC999_NON_EXISTENT"] = {"AddPatientAction"}

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
        manifest = BenchmarkProjectManifest.from_file(ITRUST_MANIFEST)
        project = ProjectIngestionAdapter().ingest_project(manifest, validate=False)

        # Inject non-existent target ID into ground truth
        corrupted_gt = dict(project.ground_truth)
        corrupted_gt["UC1S1"] = {"NonExistentClassAction"}

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

    def test_duplicate_links_in_raw_records_detected(self):
        manifest = BenchmarkProjectManifest.from_file(ITRUST_MANIFEST)
        project = ProjectIngestionAdapter().ingest_project(manifest, validate=False)

        dup_records = [
            RawTraceLinkRecord(
                requirement_id="UC1S1",
                artifact_id="AddPatientAction",
                artifact_type="source_code",
            ),
            RawTraceLinkRecord(
                requirement_id="UC1S1",
                artifact_id="AddPatientAction",
                artifact_type="source_code",
            ),
        ]
        with pytest.raises(BenchmarkValidationError, match="Duplicate ground-truth"):
            validate_benchmark_project(
                project, raw_records=dup_records, raise_on_error=True
            )

    def test_no_test_artifacts_in_itrust_source_corpus(self):
        manifest = BenchmarkProjectManifest.from_file(ITRUST_MANIFEST)
        project = ProjectIngestionAdapter().ingest_project(manifest, validate=True)

        for chunk in project.source_artifacts:
            sid = chunk.source_id.lower()
            assert not sid.startswith("test/"), f"Test chunk found: {sid}"
            assert not sid.startswith("tests/"), f"Test chunk found: {sid}"
            assert chunk.metadata.get("artifact_type") != "test_case", (
                f"Test artifact type found: {sid}"
            )


class TestSyntheticRegressionInvariant:
    """Verifies that sample_project baseline numbers remain frozen and identical."""

    def test_sample_project_baselines_remain_frozen(self):
        manifest = BenchmarkProjectManifest.from_file(SAMPLE_MANIFEST)
        project = ProjectIngestionAdapter().ingest_project(manifest, validate=True)
        runner = MultiProjectBenchmarkRunner([project], k_values=(1, 3, 5))

        # B0: TF-IDF
        b0_res = runner.run(TfidfRetriever()).project_results["sample_project"]
        assert round(b0_res.map, 4) == 0.7485
        assert round(b0_res.mrr, 4) == 0.8500
        assert round(b0_res.precision_at_k[1], 4) == 0.8000
        assert round(b0_res.precision_at_k[3], 4) == 0.3667
        assert round(b0_res.precision_at_k[5], 4) == 0.2400
        assert round(b0_res.recall_at_k[1], 4) == 0.5500
        assert round(b0_res.recall_at_k[3], 4) == 0.7500
        assert round(b0_res.recall_at_k[5], 4) == 0.8000

        # B1: BM25
        b1_res = runner.run(BM25Retriever()).project_results["sample_project"]
        assert round(b1_res.map, 4) == 0.7030
        assert round(b1_res.mrr, 4) == 0.8033
        assert round(b1_res.precision_at_k[1], 4) == 0.7000
        assert round(b1_res.precision_at_k[3], 4) == 0.3333
        assert round(b1_res.precision_at_k[5], 4) == 0.2600
        assert round(b1_res.recall_at_k[1], 4) == 0.5000
        assert round(b1_res.recall_at_k[3], 4) == 0.7000
        assert round(b1_res.recall_at_k[5], 4) == 0.8500

        # B2: Semantic
        b2_res = runner.run(SemanticRetriever()).project_results["sample_project"]
        assert round(b2_res.map, 4) == 0.7350
        assert round(b2_res.mrr, 4) == 0.8500
        assert round(b2_res.precision_at_k[1], 4) == 0.7000
        assert round(b2_res.precision_at_k[3], 4) == 0.4333
        assert round(b2_res.precision_at_k[5], 4) == 0.2800
        assert round(b2_res.recall_at_k[1], 4) == 0.4500
        assert round(b2_res.recall_at_k[3], 4) == 0.8500
        assert round(b2_res.recall_at_k[5], 4) == 0.9000

        # B3: Structural
        b3_run = runner.run(StructuralRetriever(alpha=0.5))
        b3_res = b3_run.project_results["sample_project"]
        assert round(b3_res.map, 4) == 0.3977

        assert round(b3_res.mrr, 4) == 0.4333
        assert round(b3_res.precision_at_k[1], 4) == 0.2000
        assert round(b3_res.precision_at_k[3], 4) == 0.2000
        assert round(b3_res.precision_at_k[5], 4) == 0.2200
        assert round(b3_res.recall_at_k[1], 4) == 0.1000
        assert round(b3_res.recall_at_k[3], 4) == 0.4000
        assert round(b3_res.recall_at_k[5], 4) == 0.7000


class TestITrustEvaluationDenominatorAndReporting:
    """Verifies that ranking metrics explicitly track 105 evaluable
    and 26 zero-link requirements.
    """

    def test_itrust_denominator_and_table_formatting(self):
        manifest = BenchmarkProjectManifest.from_file(ITRUST_MANIFEST)
        project = ProjectIngestionAdapter().ingest_project(manifest, validate=True)
        runner = MultiProjectBenchmarkRunner([project], k_values=(1, 3, 5))

        res = runner.run(TfidfRetriever())
        p_res = res.project_results["itrust"]

        # Structural dimensions & denominator breakdown
        assert p_res.num_requirements == 131
        assert p_res.num_evaluable_requirements == 105
        assert p_res.num_zero_link_requirements == 26
        assert p_res.num_source_chunks == 226
        assert p_res.num_ground_truth_links == 286

        # Ranking metrics computed over 105 evaluable requirements
        assert round(p_res.map, 4) == 0.3006
        assert round(p_res.mrr, 4) == 0.4194
        assert round(p_res.precision_at_k[1], 4) == 0.2286
        assert round(p_res.precision_at_k[3], 4) == 0.2413
        assert round(p_res.precision_at_k[5], 4) == 0.2000
        assert round(p_res.recall_at_k[1], 4) == 0.0895
        assert round(p_res.recall_at_k[3], 4) == 0.2825
        assert round(p_res.recall_at_k[5], 4) == 0.3913

        # Explicit table formatting check
        table = res.format_table()
        assert "Total Reqs" in table
        assert "Eval Reqs (Denom)" in table
        assert "Zero-Link Reqs" in table
        assert "Source Classes" in table
        assert "Gold Links" in table
        assert "131" in table
        assert "105" in table
        assert "26" in table
        assert "226" in table
        assert "286" in table
        assert "Note on Denominator" in table

    def test_itrust_b3_structural_results(self):
        manifest = BenchmarkProjectManifest.from_file(ITRUST_MANIFEST)
        project = ProjectIngestionAdapter().ingest_project(manifest, validate=True)
        runner = MultiProjectBenchmarkRunner([project], k_values=(1, 3, 5))

        res = runner.run(StructuralRetriever(alpha=0.5))
        p_res = res.project_results["itrust"]

        assert round(p_res.map, 4) == 0.1770
        assert round(p_res.mrr, 4) == 0.2675
        assert round(p_res.precision_at_k[1], 4) == 0.0857
        assert round(p_res.precision_at_k[3], 4) == 0.1333
        assert round(p_res.precision_at_k[5], 4) == 0.1238
        assert round(p_res.recall_at_k[1], 4) == 0.0247
        assert round(p_res.recall_at_k[3], 4) == 0.1569
        assert round(p_res.recall_at_k[5], 4) == 0.2316

    def test_itrust_b4_hybrid_results(self):
        manifest = BenchmarkProjectManifest.from_file(ITRUST_MANIFEST)
        project = ProjectIngestionAdapter().ingest_project(manifest, validate=True)
        runner = MultiProjectBenchmarkRunner([project], k_values=(1, 3, 5))

        res = runner.run(HybridRetriever(k=60))
        p_res = res.project_results["itrust"]

        assert round(p_res.map, 4) == 0.2386
        assert round(p_res.mrr, 4) == 0.3438
        assert round(p_res.precision_at_k[1], 4) == 0.1619
        assert round(p_res.precision_at_k[3], 4) == 0.1873
        assert round(p_res.precision_at_k[5], 4) == 0.1619
        assert round(p_res.recall_at_k[1], 4) == 0.0599
        assert round(p_res.recall_at_k[3], 4) == 0.2133
        assert round(p_res.recall_at_k[5], 4) == 0.3094
