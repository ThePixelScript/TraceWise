"""Integration tests verifying sample_project synthetic traceability fixtures.

Ensures that the sample_project fixture:
- Ingests cleanly via ArtifactIngestor
- Chunks cleanly via PythonChunker
- Contains 0 missing artifact IDs in trace_links.json
- Contains 0 duplicate (requirement_id, artifact_id, artifact_type) links
- Contains 0 missing artifact IDs in change_scenarios.json
- Preserves method/function-level granularity for source links
"""

import json
from pathlib import Path

import pytest

from tracewise import (
    ArtifactChunk,
    ArtifactIngestor,
    ArtifactType,
    IngestionRule,
    PythonChunker,
)


@pytest.fixture
def sample_project_dir() -> Path:
    fixture_dir = (
        Path(__file__).resolve().parent.parent / "data" / "fixtures" / "sample_project"
    )
    assert fixture_dir.exists(), f"Fixture directory not found: {fixture_dir}"
    return fixture_dir


@pytest.fixture
def ingested_sample_artifacts(sample_project_dir: Path):
    ingestor = ArtifactIngestor()
    rules = [
        IngestionRule(
            pattern="requirements/*.md", artifact_type=ArtifactType.REQUIREMENT
        ),
        IngestionRule(pattern="src/**/*.py", artifact_type=ArtifactType.SOURCE_CODE),
        IngestionRule(pattern="tests/*.py", artifact_type=ArtifactType.TEST_CASE),
    ]
    return ingestor.ingest(sample_project_dir, rules)


@pytest.fixture
def sample_chunks(ingested_sample_artifacts) -> list[ArtifactChunk]:
    chunker = PythonChunker()
    chunks: list[ArtifactChunk] = []
    for artifact in ingested_sample_artifacts:
        if artifact.artifact_type in (ArtifactType.SOURCE_CODE, ArtifactType.TEST_CASE):
            chunks.extend(chunker.chunk(artifact))
    return chunks


class TestSampleProjectFixture:
    def test_sample_project_ingestion(self, ingested_sample_artifacts):
        assert len(ingested_sample_artifacts) == 22

        by_type: dict[ArtifactType, int] = {}
        for artifact in ingested_sample_artifacts:
            by_type[artifact.artifact_type] = by_type.get(artifact.artifact_type, 0) + 1

        assert by_type[ArtifactType.REQUIREMENT] == 10
        assert by_type[ArtifactType.SOURCE_CODE] == 8
        assert by_type[ArtifactType.TEST_CASE] == 4

    def test_sample_project_chunking(self, sample_chunks: list[ArtifactChunk]):
        assert len(sample_chunks) == 53
        chunk_ids = [c.id for c in sample_chunks]
        assert len(chunk_ids) == len(set(chunk_ids)), "Duplicate chunk IDs found."

    def test_trace_links_artifact_ids_exist(
        self, sample_project_dir: Path, sample_chunks: list[ArtifactChunk]
    ):
        trace_links_file = sample_project_dir / "trace_links.json"
        with open(trace_links_file, encoding="utf-8") as f:
            links = json.load(f)

        assert len(links) == 33
        chunk_ids = {c.id for c in sample_chunks}

        missing = [
            (link["requirement_id"], link["artifact_id"])
            for link in links
            if link["artifact_id"] not in chunk_ids
        ]
        assert missing == [], f"Missing artifact IDs in trace_links.json: {missing}"

    def test_trace_links_no_duplicate_records(self, sample_project_dir: Path):
        trace_links_file = sample_project_dir / "trace_links.json"
        with open(trace_links_file, encoding="utf-8") as f:
            links = json.load(f)

        link_keys = [
            (link["requirement_id"], link["artifact_id"], link["artifact_type"])
            for link in links
        ]
        assert len(link_keys) == len(set(link_keys)), "Duplicate trace links found."

    def test_change_scenarios_artifact_ids_exist(
        self,
        sample_project_dir: Path,
        sample_chunks: list[ArtifactChunk],
        ingested_sample_artifacts,
    ):
        scenarios_file = sample_project_dir / "change_scenarios.json"
        with open(scenarios_file, encoding="utf-8") as f:
            scenarios = json.load(f)

        assert len(scenarios) == 3
        chunk_ids = {c.id for c in sample_chunks}
        req_stems = {
            Path(a.file_path).stem
            for a in ingested_sample_artifacts
            if a.artifact_type == ArtifactType.REQUIREMENT
        }

        missing: list[tuple[str, str, str]] = []
        for s in scenarios:
            sid = s["scenario_id"]
            for ca in s["changed_artifacts"]:
                if ca not in chunk_ids:
                    missing.append((sid, "changed_artifact", ca))
            for ia in s["expected_impacted_artifacts"]:
                if ia not in chunk_ids:
                    missing.append((sid, "impacted_artifact", ia))
            for req in s["expected_impacted_requirements"]:
                if req not in req_stems:
                    missing.append((sid, "impacted_requirement", req))

        assert missing == [], f"Missing IDs in change_scenarios.json: {missing}"

    def test_trace_links_source_granularity(
        self, sample_project_dir: Path, sample_chunks: list[ArtifactChunk]
    ):
        trace_links_file = sample_project_dir / "trace_links.json"
        with open(trace_links_file, encoding="utf-8") as f:
            links = json.load(f)

        chunk_by_id = {c.id: c for c in sample_chunks}
        for link in links:
            if link["artifact_type"] == "source_code":
                aid = link["artifact_id"]
                assert aid in chunk_by_id, f"Artifact {aid} not found in chunks."
                chunk = chunk_by_id[aid]
                c_type = chunk.metadata.get("chunk_type")
                assert c_type in ("function", "method"), (
                    f"Link {link['requirement_id']} -> {aid} has chunk_type "
                    f"'{c_type}', expected function or method."
                )
