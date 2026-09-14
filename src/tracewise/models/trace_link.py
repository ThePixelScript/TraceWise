"""Domain models for traceability links."""

from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TraceLinkStatus(str, Enum):
    """Lifecycle status of a traceability link."""

    PROPOSED = "PROPOSED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"

    @classmethod
    def _missing_(cls, value: object) -> "TraceLinkStatus | None":
        if isinstance(value, str):
            normalized = value.strip().upper()
            for member in cls:
                if member.value == normalized:
                    return member
        return None


class TraceLink(BaseModel):
    """A trace link connecting two software artifacts or artifact chunks."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    target_id: str
    status: TraceLinkStatus = TraceLinkStatus.PROPOSED
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_id", "target_id")
    @classmethod
    def validate_endpoints(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Endpoint ID cannot be empty.")
        return cleaned

    @model_validator(mode="after")
    def validate_distinct_endpoints(self) -> Self:
        if self.source_id == self.target_id:
            raise ValueError("source_id and target_id must be distinct.")
        return self
