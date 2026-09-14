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
    def test_artifact_creation_all_required_fields(self):
        artifact = Artifact(
            id="REQ-001",
            artifact_type=ArtifactType.REQUIREMENT,
            file_path="docs/reqs.md",
            raw_content="The system shall authenticate users via OAuth2.",
            content="The system shall authenticate users via OAuth2.",
        )
        assert artifact.id == "REQ-001"
        assert artifact.artifact_type == ArtifactType.REQUIREMENT
        assert artifact.file_path == "docs/reqs.md"
        assert artifact.raw_content == (
            "The system shall authenticate users via OAuth2."
        )
        assert artifact.content == "The system shall authenticate users via OAuth2."
        assert artifact.metadata == {}

    def test_artifact_creation_with_metadata(self):
        artifact = Artifact(
            id="src/auth.py",
            artifact_type=ArtifactType.SOURCE_CODE,
            file_path="src/auth.py",
            raw_content="def login(): pass",
            content="def login(): pass",
            metadata={"language": "python"},
        )
        assert artifact.id == "src/auth.py"
        assert artifact.artifact_type == ArtifactType.SOURCE_CODE
        assert artifact.file_path == "src/auth.py"
        assert artifact.metadata["language"] == "python"

    def test_artifact_id_stripped(self):
        artifact = Artifact(
            id="  REQ-002  ",
            artifact_type=ArtifactType.REQUIREMENT,
            file_path="docs/reqs.md",
            raw_content="Some requirement",
            content="Some requirement",
        )
        assert artifact.id == "REQ-002"

    def test_artifact_empty_id_raises_validation_error(self):
        with pytest.raises(ValidationError):
            Artifact(
                id="",
                artifact_type=ArtifactType.REQUIREMENT,
                file_path="docs/reqs.md",
                raw_content="Valid content",
                content="Valid content",
            )

        with pytest.raises(ValidationError):
            Artifact(
                id="   ",
                artifact_type=ArtifactType.REQUIREMENT,
                file_path="docs/reqs.md",
                raw_content="Valid content",
                content="Valid content",
            )

    def test_artifact_invalid_type_raises(self):
        with pytest.raises(ValidationError):
            Artifact(
                id="REQ-003",
                artifact_type="INVALID_TYPE",
                file_path="docs/reqs.md",
                raw_content="Some requirement",
                content="Some requirement",
            )

    def test_artifact_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            Artifact(
                id="REQ-004",
                artifact_type=ArtifactType.REQUIREMENT,
                file_path="docs/reqs.md",
                raw_content="Some content",
                content="Some content",
                unknown_attribute="not_allowed",
            )

    def test_artifact_serialization_roundtrip(self):
        artifact = Artifact(
            id="TC-101",
            artifact_type=ArtifactType.TEST_CASE,
            file_path="tests/test_auth.py",
            raw_content="def test_oauth_flow(): assert True",
            content="def test_oauth_flow(): assert True",
            metadata={"framework": "pytest"},
        )
        data = artifact.model_dump()
        assert data["id"] == "TC-101"
        assert data["artifact_type"] == ArtifactType.TEST_CASE
        assert data["file_path"] == "tests/test_auth.py"
        assert data["raw_content"] == "def test_oauth_flow(): assert True"
        assert data["content"] == "def test_oauth_flow(): assert True"
        assert data["metadata"]["framework"] == "pytest"

        json_str = artifact.model_dump_json()
        reconstructed = Artifact.model_validate_json(json_str)
        assert reconstructed == artifact

    def test_missing_file_path_raises_validation_error(self):
        with pytest.raises(ValidationError, match="file_path"):
            Artifact(
                id="REQ-005",
                artifact_type=ArtifactType.REQUIREMENT,
                raw_content="Content",
                content="Content",
            )

    def test_missing_raw_content_raises_validation_error(self):
        with pytest.raises(ValidationError, match="raw_content"):
            Artifact(
                id="REQ-006",
                artifact_type=ArtifactType.REQUIREMENT,
                file_path="docs/reqs.md",
                content="Content",
            )

    def test_missing_content_raises_validation_error(self):
        with pytest.raises(ValidationError, match="content"):
            Artifact(
                id="REQ-007",
                artifact_type=ArtifactType.REQUIREMENT,
                file_path="docs/reqs.md",
                raw_content="Content",
            )

    def test_legacy_type_field_forbidden(self):
        with pytest.raises(ValidationError):
            Artifact(
                id="REQ-008",
                type=ArtifactType.REQUIREMENT,
                file_path="docs/reqs.md",
                raw_content="Content",
                content="Content",
            )


class TestArtifactChunk:
    def test_artifact_chunk_creation_minimal(self):
        chunk = ArtifactChunk(
            id="src/auth.py#login",
            parent_id="src/auth.py",
            name="login",
            raw_content="def login():\n    pass\n",
            content="def login():\n    pass\n",
            start_line=1,
            end_line=2,
        )
        assert chunk.id == "src/auth.py#login"
        assert chunk.parent_id == "src/auth.py"
        assert chunk.name == "login"
        assert chunk.raw_content == "def login():\n    pass\n"
        assert chunk.content == "def login():\n    pass\n"
        assert chunk.start_line == 1
        assert chunk.end_line == 2
        assert chunk.metadata == {}

    def test_artifact_chunk_creation_with_metadata(self):
        chunk = ArtifactChunk(
            id="src/auth.py#AuthService.login",
            parent_id="src/auth.py#AuthService",
            name="login",
            raw_content="def login(self): pass",
            content="def login(self): pass",
            start_line=10,
            end_line=10,
            metadata={"chunk_type": "method", "is_async": False, "docstring": ""},
        )
        assert chunk.id == "src/auth.py#AuthService.login"
        assert chunk.parent_id == "src/auth.py#AuthService"
        assert chunk.metadata["chunk_type"] == "method"
        assert chunk.metadata["is_async"] is False

    def test_artifact_chunk_whitespace_identifiers_stripped(self):
        chunk = ArtifactChunk(
            id="  src/auth.py#login  ",
            parent_id="  src/auth.py  ",
            name="  login  ",
            raw_content="def login(): pass",
            content="def login(): pass",
            start_line=1,
            end_line=1,
        )
        assert chunk.id == "src/auth.py#login"
        assert chunk.parent_id == "src/auth.py"
        assert chunk.name == "login"

    def test_artifact_chunk_empty_identifiers_raise(self):
        valid_kwargs = {
            "id": "src/auth.py#login",
            "parent_id": "src/auth.py",
            "name": "login",
            "raw_content": "def login(): pass",
            "content": "def login(): pass",
            "start_line": 1,
            "end_line": 1,
        }
        for field in ("id", "parent_id", "name"):
            with pytest.raises(ValidationError):
                ArtifactChunk(**{**valid_kwargs, field: ""})
            with pytest.raises(ValidationError):
                ArtifactChunk(**{**valid_kwargs, field: "   "})

    def test_artifact_chunk_invalid_start_line_raises(self):
        with pytest.raises(ValidationError):
            ArtifactChunk(
                id="src/auth.py#login",
                parent_id="src/auth.py",
                name="login",
                raw_content="def login(): pass",
                content="def login(): pass",
                start_line=0,
                end_line=1,
            )

    def test_artifact_chunk_end_line_before_start_line_raises(self):
        with pytest.raises(ValidationError):
            ArtifactChunk(
                id="src/auth.py#login",
                parent_id="src/auth.py",
                name="login",
                raw_content="def login(): pass",
                content="def login(): pass",
                start_line=5,
                end_line=4,
            )

    def test_artifact_chunk_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            ArtifactChunk(
                id="src/auth.py#login",
                parent_id="src/auth.py",
                name="login",
                raw_content="def login(): pass",
                content="def login(): pass",
                start_line=1,
                end_line=1,
                extra_field="disallowed",
            )

    def test_artifact_chunk_serialization_roundtrip(self):
        chunk = ArtifactChunk(
            id="src/auth.py#login",
            parent_id="src/auth.py",
            name="login",
            raw_content="def login(): pass",
            content="def login(): pass",
            start_line=1,
            end_line=1,
            metadata={
                "chunk_type": "function",
                "is_async": False,
                "docstring": "Login.",
            },
        )
        json_str = chunk.model_dump_json()
        reconstructed = ArtifactChunk.model_validate_json(json_str)
        assert reconstructed == chunk
        dumped = chunk.model_dump()
        assert dumped["id"] == "src/auth.py#login"
        assert dumped["parent_id"] == "src/auth.py"
        assert dumped["name"] == "login"
        assert dumped["start_line"] == 1
        assert dumped["end_line"] == 1


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
