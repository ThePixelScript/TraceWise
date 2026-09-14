"""Domain model for structural artifact chunks."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ArtifactChunk(BaseModel):
    """A structural segment or sub-unit inside an artifact."""

    model_config = ConfigDict(extra="forbid")

    id: str
    parent_id: str
    name: str
    raw_content: str
    content: str
    start_line: int
    end_line: int
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "parent_id", "name")
    @classmethod
    def validate_non_empty_identifiers(cls, v: str, info: Any) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError(f"ArtifactChunk {info.field_name} cannot be empty.")
        return cleaned

    @field_validator("start_line")
    @classmethod
    def validate_start_line(cls, v: int) -> int:
        if v < 1:
            raise ValueError(
                "ArtifactChunk start_line must be greater than or equal to 1."
            )
        return v

    @model_validator(mode="after")
    def validate_line_range(self) -> "ArtifactChunk":
        if self.end_line < self.start_line:
            raise ValueError(
                f"ArtifactChunk end_line ({self.end_line}) cannot be less than "
                f"start_line ({self.start_line})."
            )
        return self
