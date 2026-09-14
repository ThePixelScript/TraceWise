"""Unit tests for TraceWise domain models: creation, validation, and serialization."""

import pytest
from pydantic import ValidationError

from tracewise import (
    Artifact,
    ArtifactChunk,
    ArtifactType,
    TraceLink,
    TraceLinkStatus,
)


class TestArtifactType:
    def test_enum_values(self):
        assert ArtifactType.REQUIREMENT == "REQUIREMENT"
        assert ArtifactType.SOURCE_CODE == "SOURCE_CODE"
        assert ArtifactType.TEST_CASE == "TEST_CASE"

    def test_case_insensitive_lookup(self):
        assert ArtifactType("requirement") == ArtifactType.REQUIREMENT
        assert ArtifactType("Source_Code") == ArtifactType.SOURCE_CODE
        assert ArtifactType("test_case") == ArtifactType.TEST_CASE

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError):
            ArtifactType("UNKNOWN_TYPE")


class TestArtifact:
    def test_artifact_creation_minimal(self):
        artifact = Artifact(
            id="REQ-001",
            type=ArtifactType.REQUIREMENT,
            content="The system shall authenticate users via OAuth2.",
        )
        assert artifact.id == "REQ-001"
        assert artifact.type == ArtifactType.REQUIREMENT
        assert artifact.content == "The system shall authenticate users via OAuth2."
        assert artifact.metadata == {}

    def test_artifact_creation_with_metadata(self):
        artifact = Artifact(
            id="SRC-auth.py",
            type="source_code",
            content="def login(): pass",
            metadata={"path": "src/auth.py", "language": "python"},
        )
        assert artifact.id == "SRC-auth.py"
        assert artifact.type == ArtifactType.SOURCE_CODE
        assert artifact.metadata["path"] == "src/auth.py"

    def test_artifact_id_stripped(self):
        artifact = Artifact(
            id="  REQ-002  ",
            type=ArtifactType.REQUIREMENT,
            content="Some requirement",
        )
        assert artifact.id == "REQ-002"

    def test_artifact_empty_id_raises_validation_error(self):
        with pytest.raises(ValidationError):
            Artifact(
                id="",
                type=ArtifactType.REQUIREMENT,
                content="Valid content",
            )

        with pytest.raises(ValidationError):
            Artifact(
                id="   ",
                type=ArtifactType.REQUIREMENT,
                content="Valid content",
            )

    def test_artifact_invalid_type_raises(self):
        with pytest.raises(ValidationError):
            Artifact(
                id="REQ-003",
                type="INVALID_TYPE",
                content="Some requirement",
            )

    def test_artifact_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            Artifact(
                id="REQ-004",
                type=ArtifactType.REQUIREMENT,
                content="Some content",
                unknown_attribute="not_allowed",
            )

    def test_artifact_serialization_roundtrip(self):
        artifact = Artifact(
            id="TC-101",
            type=ArtifactType.TEST_CASE,
            content="def test_oauth_flow(): assert True",
            metadata={"framework": "pytest"},
        )
        data = artifact.model_dump()
        assert data["id"] == "TC-101"
        assert data["type"] == ArtifactType.TEST_CASE
        assert data["metadata"]["framework"] == "pytest"

        json_str = artifact.model_dump_json()
        reconstructed = Artifact.model_validate_json(json_str)
        assert reconstructed == artifact


class TestArtifactChunk:
    def test_artifact_chunk_creation(self):
        chunk = ArtifactChunk(
            id="SRC-auth.py#login",
            artifact_id="SRC-auth.py",
            content=(
                "def login(username, password):\n"
                "    return authenticate(username, password)"
            ),
            metadata={"start_line": 10, "end_line": 12},
        )
        assert chunk.id == "SRC-auth.py#login"
        assert chunk.artifact_id == "SRC-auth.py"
        assert chunk.metadata["start_line"] == 10

    def test_artifact_chunk_empty_id_raises(self):
        with pytest.raises(ValidationError):
            ArtifactChunk(
                id="",
                artifact_id="SRC-auth.py",
                content="def test(): pass",
            )

        with pytest.raises(ValidationError):
            ArtifactChunk(
                id="SRC-auth.py#test",
                artifact_id="",
                content="def test(): pass",
            )

    def test_artifact_chunk_serialization_roundtrip(self):
        chunk = ArtifactChunk(
            id="REQ-001#sec1",
            artifact_id="REQ-001",
            content="Section 1: Authentication Requirements",
        )
        json_str = chunk.model_dump_json()
        reconstructed = ArtifactChunk.model_validate_json(json_str)
        assert reconstructed == chunk


class TestTraceLinkStatus:
    def test_enum_values(self):
        assert TraceLinkStatus.PROPOSED == "PROPOSED"
        assert TraceLinkStatus.VERIFIED == "VERIFIED"
        assert TraceLinkStatus.REJECTED == "REJECTED"

    def test_case_insensitive_lookup(self):
        assert TraceLinkStatus("proposed") == TraceLinkStatus.PROPOSED
        assert TraceLinkStatus("Verified") == TraceLinkStatus.VERIFIED
        assert TraceLinkStatus("rejected") == TraceLinkStatus.REJECTED

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError):
            TraceLinkStatus("UNKNOWN_STATUS")


class TestTraceLink:
    def test_trace_link_creation_minimal(self):
        link = TraceLink(
            source_id="REQ-001",
            target_id="SRC-auth.py",
        )
        assert link.source_id == "REQ-001"
        assert link.target_id == "SRC-auth.py"
        assert link.status == TraceLinkStatus.PROPOSED
        assert link.metadata == {}

    def test_trace_link_source_id_validation(self):
        with pytest.raises(ValidationError):
            TraceLink(source_id="", target_id="SRC-001")

        with pytest.raises(ValidationError):
            TraceLink(source_id="   ", target_id="SRC-001")

    def test_trace_link_target_id_validation(self):
        with pytest.raises(ValidationError):
            TraceLink(source_id="REQ-001", target_id="")

        with pytest.raises(ValidationError):
            TraceLink(source_id="REQ-001", target_id="   ")

    def test_trace_link_endpoint_whitespace_stripped(self):
        link = TraceLink(
            source_id="  REQ-001  ",
            target_id="  SRC-auth.py  ",
        )
        assert link.source_id == "REQ-001"
        assert link.target_id == "SRC-auth.py"

    def test_trace_link_same_endpoints_raises(self):
        with pytest.raises(ValidationError, match="must be distinct"):
            TraceLink(
                source_id="REQ-001",
                target_id="REQ-001",
            )

    def test_trace_link_status_default(self):
        link = TraceLink(source_id="REQ-001", target_id="SRC-001")
        assert link.status == TraceLinkStatus.PROPOSED

    def test_trace_link_status_string_coercion(self):
        link = TraceLink(
            source_id="REQ-001",
            target_id="TC-101",
            status="verified",
        )
        assert link.status == TraceLinkStatus.VERIFIED

    def test_trace_link_metadata_storage(self):
        link = TraceLink(
            source_id="REQ-001",
            target_id="SRC-auth.py#login",
            status=TraceLinkStatus.VERIFIED,
            metadata={"verified_by": "reviewer_1"},
        )
        assert link.metadata["verified_by"] == "reviewer_1"

    def test_trace_link_algorithm_scores_in_metadata(self):
        link = TraceLink(
            source_id="REQ-001",
            target_id="SRC-auth.py",
            metadata={
                "retrieval_method": "tfidf",
                "raw_score": 0.82,
            },
        )
        assert link.metadata["retrieval_method"] == "tfidf"
        assert link.metadata["raw_score"] == 0.82

    def test_trace_link_serialization_roundtrip(self):
        link = TraceLink(
            source_id="REQ-001",
            target_id="SRC-001",
            status=TraceLinkStatus.PROPOSED,
            metadata={"confidence": "high"},
        )
        json_str = link.model_dump_json()
        reconstructed = TraceLink.model_validate_json(json_str)
        assert reconstructed == link

    def test_trace_link_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            TraceLink(
                source_id="REQ-001",
                target_id="SRC-001",
                extra_field="invalid",
            )

        with pytest.raises(ValidationError):
            TraceLink(
                source_id="REQ-001",
                target_id="SRC-001",
                score=0.85,
            )
