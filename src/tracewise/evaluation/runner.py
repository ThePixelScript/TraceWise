"""Benchmark runner for automated traceability retrieval evaluation."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tracewise.evaluation.ground_truth import load_ground_truth
from tracewise.evaluation.metrics import evaluate_retrieval
from tracewise.evaluation.models import EvaluationResult
from tracewise.ingestion.ingestor import ArtifactIngestor
from tracewise.ingestion.python_chunker import PythonChunker
from tracewise.ingestion.rules import IngestionRule
from tracewise.models.artifact import ArtifactType
from tracewise.preprocessing.preprocessor import Preprocessor
from tracewise.retrieval.base import BaseRetriever
from tracewise.retrieval.tfidf import TfidfRetriever


class BenchmarkRunner:
    """Orchestrates end-to-end benchmark evaluation for traceability retrievers.

    The runner follows strict architectural separation:
    1. Ingestion: Reads requirement specifications and source/test artifacts.
    2. Structural Chunking: Extracts functions, classes, and methods via Python AST.
    3. Preprocessing: Converts artifacts and chunks to canonical ProcessedText.
    4. Indexing: Builds the retriever's corpus index using preprocessed chunks.
    5. Query Retrieval: Retrieves candidate hypotheses without ground-truth knowledge.
    6. Evaluation: Independently loads ground truth and scores
       candidates against gold links.
    """

    DEFAULT_RULES: tuple[IngestionRule, ...] = (
        IngestionRule(
            pattern="requirements/*.md", artifact_type=ArtifactType.REQUIREMENT
        ),
        IngestionRule(pattern="src/**/*.py", artifact_type=ArtifactType.SOURCE_CODE),
        IngestionRule(pattern="tests/*.py", artifact_type=ArtifactType.TEST_CASE),
    )

    def __init__(
        self,
        project_root: Path | str,
        rules: Sequence[IngestionRule] | None = None,
        ground_truth_path: Path | str | None = None,
        k_values: Sequence[int] = (1, 3, 5, 10),
    ) -> None:
        """Initialize the benchmark runner with project and evaluation configurations.

        Args:
            project_root: Root directory of the benchmark project.
            rules: Ingestion rules to identify requirements, source, and tests.
            ground_truth_path: Path to ground-truth JSON file. Defaults to
                ``project_root / "trace_links.json"``.
            k_values: Cutoff values for Precision@k and Recall@k.
        """
        self.project_root = Path(project_root)
        if not self.project_root.is_dir():
            raise ValueError(
                f"Project root is not a valid directory: {self.project_root}"
            )

        self.rules = tuple(rules) if rules is not None else self.DEFAULT_RULES
        self.ground_truth_path = (
            Path(ground_truth_path)
            if ground_truth_path is not None
            else self.project_root / "trace_links.json"
        )
        self.k_values = tuple(sorted(k_values))

    def run(
        self,
        retriever: BaseRetriever,
        top_k: int | None = None,
        artifact_type_filter: str | None = None,
        dataset_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """Execute benchmark retrieval and evaluate against ground truth.

        Args:
            retriever: Configured BaseRetriever instance to benchmark.
            top_k: Maximum candidates to retrieve per query (None retrieves all).
            artifact_type_filter: Optional filter on ground-truth link type
                (e.g. 'source_code', 'test_case').
            dataset_name: Optional label for the benchmark dataset.
            metadata: Optional additional metadata to attach to the result.

        Returns:
            EvaluationResult containing aggregate and per-query IR metrics.
        """
        # 1. Ingest project artifacts
        ingestor = ArtifactIngestor()
        artifacts = ingestor.ingest(self.project_root, self.rules)

        # 2. Structural chunking of target artifacts and requirements
        chunker = PythonChunker()
        target_chunks = []
        requirement_artifacts = []

        if artifact_type_filter is not None:
            try:
                target_types = {ArtifactType(artifact_type_filter)}
            except ValueError:
                target_types = set()
        else:
            target_types = {ArtifactType.SOURCE_CODE, ArtifactType.TEST_CASE}

        for art in artifacts:
            if art.artifact_type in target_types:
                target_chunks.extend(chunker.chunk(art))
            elif art.artifact_type == ArtifactType.REQUIREMENT:
                requirement_artifacts.append(art)

        # 3. Preprocessing
        preprocessor = Preprocessor()
        target_docs = [preprocessor.process_chunk(chunk) for chunk in target_chunks]

        # 4. Retrieval indexing
        retriever.index(target_docs)

        # 5. Candidate retrieval per requirement
        query_candidates = {}
        for req in requirement_artifacts:
            req_id = Path(req.file_path).stem
            query_doc = preprocessor.process_text(
                source_id=req_id,
                text=req.content,
                metadata={
                    **req.metadata,
                    "artifact_type": req.artifact_type.value,
                },
            )
            candidates = retriever.retrieve(query_doc, top_k=top_k)
            query_candidates[req_id] = candidates

        # 6. Load ground truth
        ground_truth = load_ground_truth(
            self.ground_truth_path,
            artifact_type=artifact_type_filter,
        )

        # 7. Evaluate
        resolved_dataset_name = dataset_name or self.project_root.name
        run_metadata = {
            **(metadata or {}),
            "total_target_chunks": len(target_chunks),
            "total_requirements": len(requirement_artifacts),
            "artifact_type_filter": artifact_type_filter,
            "top_k_retrieved": top_k,
        }

        return evaluate_retrieval(
            retriever_name=retriever.retriever_name,
            query_candidates=query_candidates,
            ground_truth=ground_truth,
            dataset_name=resolved_dataset_name,
            k_values=self.k_values,
            metadata=run_metadata,
        )


def run_sample_project_benchmark(
    retriever: BaseRetriever | None = None,
    sample_project_dir: Path | str | None = None,
    k_values: Sequence[int] = (1, 3, 5, 10),
    top_k: int | None = None,
    artifact_type_filter: str | None = None,
) -> EvaluationResult:
    """Convenience helper to evaluate a retriever on the sample_project fixture."""
    if sample_project_dir is not None:
        root = Path(sample_project_dir)
    else:
        root = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "data"
            / "fixtures"
            / "sample_project"
        )

    if not root.exists():
        raise FileNotFoundError(
            f"sample_project fixture directory not found at: {root}"
        )

    active_retriever = retriever if retriever is not None else TfidfRetriever()
    runner = BenchmarkRunner(
        project_root=root,
        k_values=k_values,
    )
    return runner.run(
        retriever=active_retriever,
        top_k=top_k,
        artifact_type_filter=artifact_type_filter,
        dataset_name="sample_project",
    )


__all__ = ["BenchmarkRunner", "run_sample_project_benchmark"]
