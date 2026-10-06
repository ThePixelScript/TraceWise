"""Validation rules and diagnostic reporting for benchmark datasets."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tracewise.evaluation.project import BenchmarkProject


class BenchmarkValidationError(ValueError):
    """Raised when a benchmark dataset or project violates integrity rules."""


@dataclass(frozen=True)
class ValidationReport:
    """Diagnostic report detailing validation status, errors, and warnings."""

    project_id: str
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Formatted human-readable summary of validation findings."""
        status = "PASSED" if self.is_valid else "FAILED"
        lines = [f"Validation {status} for project '{self.project_id}':"]
        if self.errors:
            lines.append("  Errors:")
            for err in self.errors:
                lines.append(f"    - {err}")
        if self.warnings:
            lines.append("  Warnings:")
            for warn in self.warnings:
                lines.append(f"    - {warn}")
        return "\n".join(lines)


def validate_benchmark_project(
    project: BenchmarkProject,
    raw_records: list[Any] | None = None,
    raise_on_error: bool = True,
) -> ValidationReport:
    """Validate benchmark project integrity before indexing or retrieval.

    Enforces the following research and architectural invariants:
    1. Requirement corpus is non-empty.
    2. Source-code chunk corpus is non-empty.
    3. Requirement IDs are strictly unique.
    4. Source-code chunk IDs are strictly unique.
    5. All ground-truth links reference valid requirement IDs.
    6. All ground-truth links reference valid source-code chunk IDs.
    7. No test artifacts enter a Requirements -> Source Code benchmark.
    8. No duplicate ground-truth links exist.

    Args:
        project: BenchmarkProject instance to inspect.
        raw_records: Optional sequence of raw trace link records to detect
            exact duplicate links before set consolidation.
        raise_on_error: Whether to raise BenchmarkValidationError immediately
            if any rule is violated. Defaults to True.

    Returns:
        ValidationReport with all identified errors and warnings.

    Raises:
        BenchmarkValidationError: If raise_on_error is True and any error is found.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Non-empty requirement corpus
    if not project.requirements:
        errors.append("Requirement corpus is empty (0 requirements found).")

    # 2. Non-empty source corpus
    if not project.source_artifacts:
        errors.append("Source-code target corpus is empty (0 source chunks found).")

    # 3. Requirement ID uniqueness
    req_ids: list[str] = [req.source_id for req in project.requirements]
    seen_reqs: set[str] = set()
    dup_reqs: set[str] = set()
    for rid in req_ids:
        if rid in seen_reqs:
            dup_reqs.add(rid)
        seen_reqs.add(rid)
    if dup_reqs:
        errors.append(f"Duplicate requirement IDs detected: {sorted(dup_reqs)}.")

    # 4. Source-code chunk ID uniqueness
    chunk_ids: list[str] = [chunk.source_id for chunk in project.source_artifacts]
    seen_chunks: set[str] = set()
    dup_chunks: set[str] = set()
    for cid in chunk_ids:
        if cid in seen_chunks:
            dup_chunks.add(cid)
        seen_chunks.add(cid)
    if dup_chunks:
        errors.append(f"Duplicate source chunk IDs detected: {sorted(dup_chunks)}.")

    valid_req_set = seen_reqs
    valid_chunk_set = seen_chunks

    # 5 & 6. Ground-truth references valid requirement and source targets
    missing_reqs_in_gt: set[str] = set()
    missing_chunks_in_gt: set[str] = set()

    for q_id, target_set in project.ground_truth.items():
        if q_id not in valid_req_set:
            missing_reqs_in_gt.add(q_id)
        for t_id in target_set:
            if t_id not in valid_chunk_set:
                missing_chunks_in_gt.add(t_id)

    if missing_reqs_in_gt:
        errors.append(
            f"Ground-truth references non-existent requirement ID(s): "
            f"{sorted(missing_reqs_in_gt)}."
        )
    if missing_chunks_in_gt:
        errors.append(
            f"Ground-truth references non-existent source target ID(s): "
            f"{sorted(missing_chunks_in_gt)}."
        )

    # 7. No test artifacts enter Requirements -> Source Code benchmark
    test_artifacts: list[str] = []
    for chunk in project.source_artifacts:
        sid = chunk.source_id.lower()
        art_type = chunk.metadata.get("artifact_type", "")
        if (
            art_type == "test_case"
            or sid.startswith("tests/")
            or sid.startswith("test/")
        ):
            test_artifacts.append(chunk.source_id)

    if test_artifacts:
        errors.append(
            f"Test artifacts detected in source-code target corpus "
            f"({len(test_artifacts)} chunks): {test_artifacts[:5]}."
        )

    # 8. Duplicate ground-truth links detection from raw records
    if raw_records is not None:
        seen_pairs: set[tuple[str, str]] = set()
        dup_pairs: list[tuple[str, str]] = []
        for rec in raw_records:
            req_id = getattr(rec, "requirement_id", None)
            art_id = getattr(rec, "artifact_id", None)
            if req_id is not None and art_id is not None:
                pair = (str(req_id).strip(), str(art_id).strip())
                if pair in seen_pairs:
                    dup_pairs.append(pair)
                seen_pairs.add(pair)
        if dup_pairs:
            errors.append(
                f"Duplicate ground-truth trace link(s) detected: {dup_pairs}."
            )

    is_valid = len(errors) == 0
    report = ValidationReport(
        project_id=project.project_id,
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
    )

    if not is_valid and raise_on_error:
        raise BenchmarkValidationError(report.summary())

    return report


__all__ = ["BenchmarkValidationError", "ValidationReport", "validate_benchmark_project"]
