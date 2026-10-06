"""Dataset and project manifest models for reproducible benchmark evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BenchmarkProjectManifest(BaseModel):
    """Declarative manifest defining a benchmark project configuration.

    Specifies how requirements, source artifacts, and ground-truth trace links
    are discovered and loaded for an independent benchmark project.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str
    project_name: str
    root_path: str | None = None
    requirement_source: str = "requirements/*.md"
    source_path: str = "src/**/*.py"
    ground_truth_path: str = "trace_links.json"
    ground_truth_format: str = "json"
    requirement_artifact_type: str = "requirement"
    source_artifact_type: str = "source_code"
    chunking_config: dict[str, Any] = Field(default_factory=dict)
    preprocessing_config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("project_id", "project_name")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty or whitespace.")
        return cleaned

    @classmethod
    def from_file(cls, manifest_path: Path | str) -> BenchmarkProjectManifest:
        """Load and parse a benchmark project manifest from a JSON or YAML file.

        Args:
            manifest_path: Path to the manifest file (.json, .yaml, or .yml).

        Returns:
            Validated BenchmarkProjectManifest instance.

        Raises:
            FileNotFoundError: If manifest_path does not exist.
            ValueError: If manifest content is invalid JSON/YAML or validation fails.
        """
        path = Path(manifest_path)
        if not path.is_file():
            raise FileNotFoundError(f"Manifest file not found: {path}")

        raw_text = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()

        data: Any
        if suffix in (".yaml", ".yml"):
            try:
                import yaml

                data = yaml.safe_load(raw_text)
            except Exception as exc:
                raise ValueError(
                    f"Failed to parse YAML manifest at {path}: {exc}"
                ) from exc
        else:
            try:
                data = json.loads(raw_text)
            except Exception as exc:
                # If JSON fails and yaml is installed, attempt fallback
                try:
                    import yaml

                    data = yaml.safe_load(raw_text)
                except Exception:
                    raise ValueError(
                        f"Failed to parse JSON manifest at {path}: {exc}"
                    ) from exc

        if not isinstance(data, dict):
            raise ValueError(
                f"Expected manifest mapping at {path}, got {type(data).__name__}."
            )

        # If root_path is unspecified, default to the directory containing the manifest
        if not data.get("root_path"):
            data["root_path"] = str(path.parent.resolve())

        return cls.model_validate(data)


__all__ = ["BenchmarkProjectManifest"]
