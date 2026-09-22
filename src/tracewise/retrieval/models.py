"""Domain models for candidate retrieval and ranking."""

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RetrievalCandidate(BaseModel):
    """A candidate traceability link produced by a retriever."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str
    target_id: str
    score: float
    rank: int
    retriever_name: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("query_id", "target_id", "retriever_name")
    @classmethod
    def validate_non_empty_identifiers(cls, v: str, info: Any) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError(f"RetrievalCandidate {info.field_name} cannot be empty.")
        return cleaned

    @field_validator("rank")
    @classmethod
    def validate_rank(cls, v: int) -> int:
        if v < 1:
            raise ValueError(
                f"RetrievalCandidate rank must be greater than or equal to 1, got {v}."
            )
        return v

    @field_validator("score")
    @classmethod
    def validate_score(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError(
                f"RetrievalCandidate score must be a finite float (got {v})."
            )
        return v
