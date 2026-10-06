"""Ground-truth dataset adapters and project ingestion adapters."""

from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tracewise.evaluation.manifest import BenchmarkProjectManifest
from tracewise.evaluation.project import BenchmarkProject
from tracewise.evaluation.validation import validate_benchmark_project
from tracewise.ingestion.chunker import BaseChunker
from tracewise.ingestion.file_chunker import FileChunker
from tracewise.ingestion.ingestor import ArtifactIngestor
from tracewise.ingestion.python_chunker import PythonChunker
from tracewise.ingestion.rules import IngestionRule
from tracewise.models.artifact import ArtifactType
from tracewise.preprocessing.models import ProcessedText
from tracewise.preprocessing.preprocessor import Preprocessor


class RawTraceLinkRecord(BaseModel):
    """Normalized raw ground-truth trace link representation."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    requirement_id: str
    artifact_id: str
    artifact_type: str | None = None
    row_index: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseGroundTruthAdapter(ABC):
    """Abstract base adapter for loading and validating ground-truth datasets."""

    @abstractmethod
    def load(
        self,
        source_path: Path | str,
        artifact_type: str | None = None,
        **kwargs: Any,
    ) -> dict[str, set[str]]:
        """Load ground truth into query_id -> set[target_id] mapping.

        Args:
            source_path: Path to ground-truth data file.
            artifact_type: Optional filter for artifact_type (e.g. 'source_code').
            **kwargs: Extra format-specific options.

        Returns:
            Deterministic dictionary mapping query_id to sets of exact target IDs.
        """
        ...

    @abstractmethod
    def load_raw_records(
        self,
        source_path: Path | str,
        artifact_type: str | None = None,
        **kwargs: Any,
    ) -> list[RawTraceLinkRecord]:
        """Load raw individual link records for validation and duplicate checking.

        Args:
            source_path: Path to ground-truth data file.
            artifact_type: Optional filter for artifact_type.
            **kwargs: Extra format-specific options.

        Returns:
            List of RawTraceLinkRecord instances in order of appearance.
        """
        ...


class JsonGroundTruthAdapter(BaseGroundTruthAdapter):
    """Standard JSON ground-truth loader supporting TraceWise link datasets."""

    def load_raw_records(
        self,
        source_path: Path | str,
        artifact_type: str | None = None,
        **kwargs: Any,
    ) -> list[RawTraceLinkRecord]:
        path = Path(source_path)
        if not path.is_file():
            raise FileNotFoundError(f"Ground-truth file not found: {path}")

        try:
            raw_data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(
                f"Malformed JSON in ground-truth file {path}: {exc}"
            ) from exc

        if not isinstance(raw_data, list):
            raise ValueError(
                f"Expected list of trace links in {path}, "
                f"got {type(raw_data).__name__}."
            )

        records: list[RawTraceLinkRecord] = []
        for idx, entry in enumerate(raw_data):
            if not isinstance(entry, dict):
                raise ValueError(
                    f"Malformed record at index {idx} in {path}: expected dict, "
                    f"got {type(entry).__name__}."
                )

            req_id = entry.get("requirement_id")
            art_id = entry.get("artifact_id")

            if not req_id or not isinstance(req_id, str) or not req_id.strip():
                raise ValueError(
                    f"Malformed record at index {idx} in {path}: "
                    "missing or invalid 'requirement_id'."
                )
            if not art_id or not isinstance(art_id, str) or not art_id.strip():
                raise ValueError(
                    f"Malformed record at index {idx} in {path}: "
                    "missing or invalid 'artifact_id'."
                )

            entry_type = entry.get("artifact_type")
            if artifact_type is not None and entry_type != artifact_type:
                continue

            records.append(
                RawTraceLinkRecord(
                    requirement_id=req_id.strip(),
                    artifact_id=art_id.strip(),
                    artifact_type=entry_type,
                    row_index=idx,
                    metadata={
                        k: v
                        for k, v in entry.items()
                        if k not in ("requirement_id", "artifact_id", "artifact_type")
                    },
                )
            )

        return records

    def load(
        self,
        source_path: Path | str,
        artifact_type: str | None = None,
        **kwargs: Any,
    ) -> dict[str, set[str]]:
        records = self.load_raw_records(
            source_path, artifact_type=artifact_type, **kwargs
        )
        mapping: dict[str, set[str]] = {}
        for rec in records:
            mapping.setdefault(rec.requirement_id, set()).add(rec.artifact_id)
        return {k: mapping[k] for k in sorted(mapping.keys())}


class CsvGroundTruthAdapter(BaseGroundTruthAdapter):
    """CSV ground-truth loader supporting pairwise requirement-to-artifact links.

    Handles both headered CSVs (e.g. requirement_id,artifact_id,...) and headerless
    pairwise CSVs (e.g. UC2JAVA.csv: UC1S1,AddPatientAction).
    """

    def load_raw_records(
        self,
        source_path: Path | str,
        artifact_type: str | None = None,
        **kwargs: Any,
    ) -> list[RawTraceLinkRecord]:
        path = Path(source_path)
        if not path.is_file():
            raise FileNotFoundError(f"Ground-truth file not found: {path}")

        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                rows = [
                    row for row in reader if row and any(cell.strip() for cell in row)
                ]
        except Exception as exc:
            raise ValueError(
                f"Failed to read CSV ground truth at {path}: {exc}"
            ) from exc

        if not rows:
            return []

        # Check if row 0 is a header
        first_row = [c.strip().lower() for c in rows[0]]
        has_header = False
        req_col = 0
        art_col = 1
        type_col = None

        if len(first_row) >= 2:
            if any(
                term in first_row[0] for term in ("req", "source", "query", "uc")
            ) and any(
                term in first_row[1]
                for term in ("art", "target", "code", "class", "file")
            ):
                has_header = True
            elif first_row[0] in ("requirement_id", "source_id") and first_row[1] in (
                "artifact_id",
                "target_id",
            ):
                has_header = True

            if has_header and len(first_row) >= 3 and "type" in first_row[2]:
                type_col = 2

        data_rows = rows[1:] if has_header else rows
        start_idx = 1 if has_header else 0

        records: list[RawTraceLinkRecord] = []
        for offset, row in enumerate(data_rows):
            idx = start_idx + offset
            if len(row) < 2:
                raise ValueError(
                    f"Malformed record at row {idx} in {path}: "
                    f"expected at least 2 columns, got {len(row)}."
                )
            req_id = row[req_col].strip()
            art_id = row[art_col].strip()
            if not req_id:
                raise ValueError(
                    f"Malformed record at row {idx} in {path}: "
                    "missing or empty requirement ID."
                )
            if not art_id:
                raise ValueError(
                    f"Malformed record at row {idx} in {path}: "
                    "missing or empty artifact ID."
                )

            entry_type = (
                row[type_col].strip()
                if type_col is not None and len(row) > type_col
                else None
            )
            if (
                artifact_type is not None
                and entry_type is not None
                and entry_type != artifact_type
            ):
                continue

            records.append(
                RawTraceLinkRecord(
                    requirement_id=req_id,
                    artifact_id=art_id,
                    artifact_type=entry_type or artifact_type,
                    row_index=idx,
                    metadata={"source_row": row},
                )
            )

        return records

    def load(
        self,
        source_path: Path | str,
        artifact_type: str | None = None,
        **kwargs: Any,
    ) -> dict[str, set[str]]:
        records = self.load_raw_records(
            source_path, artifact_type=artifact_type, **kwargs
        )
        mapping: dict[str, set[str]] = {}
        for rec in records:
            mapping.setdefault(rec.requirement_id, set()).add(rec.artifact_id)
        return {k: mapping[k] for k in sorted(mapping.keys())}


class ProjectIngestionAdapter:
    """Transforms a benchmark software project into a normalized BenchmarkProject.

    Reuses existing TraceWise pipeline components:
    - ArtifactIngestor (filesystem traversal, path normalization, ingestion rules)
    - PythonChunker or FileChunker (AST extraction or whole-file/class extraction)
    - Preprocessor (text normalization, code tokenization, ProcessedText creation)
    """

    def __init__(
        self,
        ingestor: ArtifactIngestor | None = None,
        chunker: BaseChunker | None = None,
        preprocessor: Preprocessor | None = None,
        default_ground_truth_adapter: BaseGroundTruthAdapter | None = None,
    ) -> None:
        self.ingestor = ingestor or ArtifactIngestor()
        self.chunker = chunker
        self.preprocessor = preprocessor or Preprocessor()
        self.default_gt_adapter = (
            default_ground_truth_adapter or JsonGroundTruthAdapter()
        )

    def ingest_project(
        self,
        manifest: BenchmarkProjectManifest,
        root_dir: Path | str | None = None,
        ground_truth_adapter: BaseGroundTruthAdapter | None = None,
        validate: bool = True,
    ) -> BenchmarkProject:
        """Ingest and normalize a project defined by a manifest.

        Args:
            manifest: BenchmarkProjectManifest describing project structure.
            root_dir: Optional root directory override.
                If None, uses manifest.root_path.
            ground_truth_adapter: Optional custom ground truth adapter.
            validate: Whether to run dataset validation rules immediately.

        Returns:
            Fully initialized and validated BenchmarkProject.

        Raises:
            FileNotFoundError: If project root or ground-truth file is missing.
            BenchmarkValidationError: If validation fails and validate is True.
        """
        root = (
            Path(root_dir) if root_dir is not None else Path(manifest.root_path or ".")
        )
        if not root.is_dir():
            raise FileNotFoundError(f"Project root directory not found: {root}")

        gt_adapter = ground_truth_adapter
        if gt_adapter is None:
            fmt = manifest.ground_truth_format.lower()
            if fmt == "csv":
                gt_adapter = CsvGroundTruthAdapter()
            else:
                gt_adapter = self.default_gt_adapter

        # 1. Ingest requirements
        req_rule = IngestionRule(
            pattern=manifest.requirement_source,
            artifact_type=ArtifactType(manifest.requirement_artifact_type),
        )
        req_artifacts = self.ingestor.ingest(root, (req_rule,))

        preprocessed_requirements: list[ProcessedText] = []
        for req in req_artifacts:
            req_id = Path(req.file_path).stem
            query_doc = self.preprocessor.process_text(
                source_id=req_id,
                text=req.content,
                metadata={
                    **req.metadata,
                    "artifact_type": req.artifact_type.value,
                    "file_path": req.file_path,
                },
            )
            preprocessed_requirements.append(query_doc)

        # Deterministically sort requirements by source_id
        preprocessed_requirements.sort(key=lambda d: d.source_id)

        # 2. Ingest source code artifacts
        src_rule = IngestionRule(
            pattern=manifest.source_path,
            artifact_type=ArtifactType(manifest.source_artifact_type),
        )
        src_artifacts = self.ingestor.ingest(root, (src_rule,))

        source_files = sorted({art.file_path for art in src_artifacts})

        # 3. Extract structural chunks from source code
        chunker = self.chunker
        if chunker is None:
            strategy = manifest.chunking_config.get("strategy")
            granularity = manifest.chunking_config.get("granularity")
            if strategy in ("file", "class") or granularity in ("file", "class"):
                use_stem = manifest.chunking_config.get("use_stem_as_id", True)
                chunker = FileChunker(use_stem_as_id=use_stem)
            else:
                chunker = PythonChunker()
        elif manifest.chunking_config.get("strategy") in (
            "file",
            "class",
        ) or manifest.chunking_config.get("granularity") in ("file", "class"):
            use_stem = manifest.chunking_config.get("use_stem_as_id", True)
            chunker = FileChunker(use_stem_as_id=use_stem)

        source_chunks = []
        for art in src_artifacts:
            source_chunks.extend(chunker.chunk(art))

        # 4. Preprocess source chunks into canonical ProcessedText
        preprocessed_sources: list[ProcessedText] = [
            self.preprocessor.process_chunk(chunk) for chunk in source_chunks
        ]
        # Deterministically sort chunks by source_id
        preprocessed_sources.sort(key=lambda d: d.source_id)

        # 5. Load ground truth
        gt_path = Path(manifest.ground_truth_path)
        if not gt_path.is_absolute():
            gt_path = root / gt_path

        raw_records = gt_adapter.load_raw_records(
            gt_path,
            artifact_type=manifest.source_artifact_type,
        )
        ground_truth: dict[str, set[str]] = {}
        for rec in raw_records:
            ground_truth.setdefault(rec.requirement_id, set()).add(rec.artifact_id)
        ground_truth = {k: ground_truth[k] for k in sorted(ground_truth.keys())}

        project = BenchmarkProject(
            project_id=manifest.project_id,
            project_name=manifest.project_name,
            requirements=preprocessed_requirements,
            source_artifacts=preprocessed_sources,
            source_files=source_files,
            ground_truth=ground_truth,
            metadata=manifest.metadata,
            configuration={
                "requirement_source": manifest.requirement_source,
                "source_path": manifest.source_path,
                "ground_truth_path": str(gt_path),
                "chunking_config": manifest.chunking_config,
                "preprocessing_config": manifest.preprocessing_config,
            },
        )

        if validate:
            validate_benchmark_project(
                project=project,
                raw_records=raw_records,
                raise_on_error=True,
            )

        return project

    @classmethod
    def from_manifest_file(
        cls,
        manifest_path: Path | str,
        validate: bool = True,
    ) -> BenchmarkProject:
        """Convenience factory to load and ingest a project from a manifest file."""
        manifest = BenchmarkProjectManifest.from_file(manifest_path)
        adapter = cls()
        return adapter.ingest_project(manifest, validate=validate)


__all__ = [
    "BaseGroundTruthAdapter",
    "CsvGroundTruthAdapter",
    "JsonGroundTruthAdapter",
    "ProjectIngestionAdapter",
    "RawTraceLinkRecord",
]
