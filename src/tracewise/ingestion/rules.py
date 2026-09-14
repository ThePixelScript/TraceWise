"""Ingestion rule configuration for mapping file patterns to artifact types."""

from pydantic import BaseModel, ConfigDict, field_validator

from tracewise.models import ArtifactType


class IngestionRule(BaseModel):
    """A rule mapping a filesystem glob pattern to an ArtifactType."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pattern: str
    artifact_type: ArtifactType

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        """Validate that the pattern is a non-empty string without null bytes."""
        if not isinstance(v, str):
            raise ValueError("Pattern must be a string.")
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Pattern cannot be empty.")
        if "\x00" in cleaned:
            raise ValueError("Pattern cannot contain null bytes.")
        return cleaned

    def __hash__(self) -> int:
        return hash((self.pattern, self.artifact_type))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IngestionRule):
            return False
        return (
            self.pattern == other.pattern and self.artifact_type == other.artifact_type
        )
