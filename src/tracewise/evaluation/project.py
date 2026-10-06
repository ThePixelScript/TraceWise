"""Typed benchmark project abstraction for independent software projects."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from tracewise.preprocessing.models import ProcessedText


class BenchmarkProject(BaseModel):
    """Isolated software project ready for benchmark indexing and evaluation.

    Encapsulates preprocessed requirement queries, target source code chunks,
    source file paths, and independent ground truth links for a single project.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    project_id: str
    project_name: str
    requirements: list[ProcessedText]
    source_artifacts: list[ProcessedText]
    source_files: list[str] = Field(default_factory=list)
    ground_truth: dict[str, set[str]]
    metadata: dict[str, Any] = Field(default_factory=dict)
    configuration: dict[str, Any] = Field(default_factory=dict)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def num_requirements(self) -> int:
        """Total number of preprocessed requirement queries."""
        return len(self.requirements)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def num_source_chunks(self) -> int:
        """Total number of target source-code chunks."""
        return len(self.source_artifacts)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def num_source_files(self) -> int:
        """Total number of distinct source files."""
        return len(self.source_files)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def num_ground_truth_links(self) -> int:
        """Total number of ground-truth requirement -> source trace links."""
        return sum(len(targets) for targets in self.ground_truth.values())

    @property
    def requirement_ids(self) -> set[str]:
        """Set of all requirement source IDs in this project."""
        return {req.source_id for req in self.requirements}

    @property
    def source_chunk_ids(self) -> set[str]:
        """Set of all source-code chunk IDs in this project."""
        return {chunk.source_id for chunk in self.source_artifacts}


__all__ = ["BenchmarkProject"]
