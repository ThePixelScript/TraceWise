"""Domain models for evaluation results and metric representations."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QueryEvaluationResult(BaseModel):
    """Evaluation metrics for a single query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str
    num_relevant: int
    num_retrieved: int
    precision_at_k: dict[int, float]
    recall_at_k: dict[int, float]
    average_precision: float
    reciprocal_rank: float

    @field_validator("query_id")
    @classmethod
    def validate_query_id(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("QueryEvaluationResult query_id cannot be empty.")
        return cleaned

    @field_validator("num_relevant", "num_retrieved")
    @classmethod
    def validate_non_negative_counts(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"Count cannot be negative, got {v}.")
        return v

    @field_validator("average_precision", "reciprocal_rank")
    @classmethod
    def validate_bounded_metric(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"Metric value must be between 0.0 and 1.0, got {v}.")
        return v


class EvaluationResult(BaseModel):
    """Aggregate benchmark evaluation results for a retriever across queries."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    retriever_name: str
    dataset_name: str
    num_queries: int
    mean_average_precision: float
    mean_reciprocal_rank: float
    mean_precision_at_k: dict[int, float]
    mean_recall_at_k: dict[int, float]
    query_results: dict[str, QueryEvaluationResult] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("retriever_name", "dataset_name")
    @classmethod
    def validate_non_empty_identifiers(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Identifier cannot be empty.")
        return cleaned

    @field_validator("num_queries")
    @classmethod
    def validate_num_queries(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"num_queries cannot be negative, got {v}.")
        return v

    @field_validator("mean_average_precision", "mean_reciprocal_rank")
    @classmethod
    def validate_bounded_metric(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"Metric value must be between 0.0 and 1.0, got {v}.")
        return v


__all__ = ["EvaluationResult", "QueryEvaluationResult"]
