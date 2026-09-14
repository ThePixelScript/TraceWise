"""Domain models for software artifacts and chunks."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tracewise.models.artifact_chunk import ArtifactChunk


class ArtifactType(str, Enum):
    """Supported software artifact types."""

    REQUIREMENT = "REQUIREMENT"
    SOURCE_CODE = "SOURCE_CODE"
    TEST_CASE = "TEST_CASE"

    @classmethod
    def _missing_(cls, value: object) -> "ArtifactType | None":
        if isinstance(value, str):
            normalized = value.strip().upper()
            for member in cls:
                if member.value == normalized:
                    return member
        return None


class Artifact(BaseModel):
    """A software artifact (e.g. requirement, code file, test case)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    artifact_type: ArtifactType
    file_path: str
    raw_content: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Artifact id cannot be empty.")
        return cleaned


__all__ = ["Artifact", "ArtifactChunk", "ArtifactType"]
