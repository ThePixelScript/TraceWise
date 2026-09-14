"""Domain models for software artifacts and chunks."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    type: ArtifactType
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Artifact id cannot be empty.")
        return cleaned


class ArtifactChunk(BaseModel):
    """A segment or sub-unit of an artifact (e.g. section, function, test method)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    artifact_id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "artifact_id")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty.")
        return cleaned
