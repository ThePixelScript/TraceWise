"""Domain model for preprocessed text representations."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProcessedText(BaseModel):
    """A preprocessed text representation ready for retrieval indexing.

    Holds the original text alongside its normalized form and extracted
    tokens.  The ``original_text`` field is always preserved exactly as
    received so that upstream content is never lost.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str
    original_text: str
    normalized_text: str
    tokens: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("ProcessedText source_id cannot be empty.")
        return cleaned


__all__ = ["ProcessedText"]
