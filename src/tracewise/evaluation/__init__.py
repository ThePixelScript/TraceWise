"""Evaluation metrics, ground-truth loaders, and benchmark runners for TraceWise."""

from tracewise.evaluation.adapters import (
    BaseGroundTruthAdapter,
    CsvGroundTruthAdapter,
    JsonGroundTruthAdapter,
    ProjectIngestionAdapter,
    RawTraceLinkRecord,
)
from tracewise.evaluation.ground_truth import load_ground_truth
from tracewise.evaluation.manifest import BenchmarkProjectManifest
from tracewise.evaluation.metrics import (
    average_precision,
    evaluate_query,
    evaluate_retrieval,
    mean_average_precision,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from tracewise.evaluation.models import EvaluationResult, QueryEvaluationResult
from tracewise.evaluation.multi_runner import (
    MultiProjectBenchmarkResult,
    MultiProjectBenchmarkRunner,
    ProjectBenchmarkResult,
)
from tracewise.evaluation.project import BenchmarkProject
from tracewise.evaluation.runner import BenchmarkRunner, run_sample_project_benchmark
from tracewise.evaluation.validation import (
    BenchmarkValidationError,
    ValidationReport,
    validate_benchmark_project,
)

__all__ = [
    "BaseGroundTruthAdapter",
    "BenchmarkProject",
    "BenchmarkProjectManifest",
    "BenchmarkRunner",
    "BenchmarkValidationError",
    "CsvGroundTruthAdapter",
    "EvaluationResult",
    "JsonGroundTruthAdapter",
    "MultiProjectBenchmarkResult",
    "MultiProjectBenchmarkRunner",
    "ProjectBenchmarkResult",
    "ProjectIngestionAdapter",
    "QueryEvaluationResult",
    "RawTraceLinkRecord",
    "ValidationReport",
    "average_precision",
    "evaluate_query",
    "evaluate_retrieval",
    "load_ground_truth",
    "mean_average_precision",
    "mean_reciprocal_rank",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
    "run_sample_project_benchmark",
    "validate_benchmark_project",
]
