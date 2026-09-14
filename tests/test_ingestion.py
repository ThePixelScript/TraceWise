"""Comprehensive unit tests for the TraceWise artifact ingestion pipeline.

Verifies all Milestone 1A acceptance criteria and edge cases.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from tracewise import (
    AmbiguousRuleError,
    ArtifactIngestor,
    ArtifactType,
    IngestionEncodingError,
    IngestionFileError,
    IngestionRule,
    normalize_posix_path,
)


class TestPathNormalization:
    def test_normalize_posix_path_windows_separators(self):
        assert normalize_posix_path("src\\auth\\service.py") == "src/auth/service.py"

    def test_normalize_posix_path_forward_slashes(self):
        assert normalize_posix_path("src/auth/service.py") == "src/auth/service.py"

    def test_normalize_posix_path_strips_leading_dotslash(self):
        assert normalize_posix_path("./src/auth/service.py") == "src/auth/service.py"
        assert normalize_posix_path(".\\src\\auth\\service.py") == "src/auth/service.py"

    def test_normalize_posix_path_pathlib_object(self):
        p = Path("src") / "auth" / "service.py"
        assert normalize_posix_path(p) == "src/auth/service.py"


class TestIngestionRuleValidation:
    def test_valid_rule_creation(self):
        rule = IngestionRule(
            pattern="src/**/*.py",
            artifact_type=ArtifactType.SOURCE_CODE,
        )
        assert rule.pattern == "src/**/*.py"
        assert rule.artifact_type == ArtifactType.SOURCE_CODE

    def test_rule_creation_string_type_coercion(self):
        rule = IngestionRule(pattern="*.md", artifact_type="requirement")
        assert rule.artifact_type == ArtifactType.REQUIREMENT

    def test_empty_pattern_raises_validation_error(self):
        with pytest.raises(ValidationError):
            IngestionRule(pattern="", artifact_type=ArtifactType.SOURCE_CODE)

        with pytest.raises(ValidationError):
            IngestionRule(pattern="   ", artifact_type=ArtifactType.SOURCE_CODE)

    def test_pattern_with_null_byte_raises_validation_error(self):
        with pytest.raises(ValidationError):
            IngestionRule(
                pattern="src/*\x00.py",
                artifact_type=ArtifactType.SOURCE_CODE,
            )

    def test_rule_is_hashable_and_frozen(self):
        r1 = IngestionRule(pattern="*.py", artifact_type=ArtifactType.SOURCE_CODE)
        r2 = IngestionRule(pattern="*.py", artifact_type=ArtifactType.SOURCE_CODE)
        assert hash(r1) == hash(r2)
        assert len({r1, r2}) == 1


class TestArtifactIngestion:
    def test_single_requirement_file(self, tmp_path: Path):
        req_file = tmp_path / "SRS.md"
        req_file.write_text(
            "# Requirements\nThe system shall authenticate users.",
            encoding="utf-8",
            newline="\n",
        )

        ingestor = ArtifactIngestor()
        rules = [IngestionRule(pattern="*.md", artifact_type=ArtifactType.REQUIREMENT)]
        artifacts = ingestor.ingest(tmp_path, rules)

        assert len(artifacts) == 1
        art = artifacts[0]
        assert art.id == "SRS.md"
        assert art.file_path == "SRS.md"
        assert art.artifact_type == ArtifactType.REQUIREMENT
        assert art.raw_content == (
            "# Requirements\nThe system shall authenticate users."
        )
        assert art.content == art.raw_content

    def test_multiple_source_files(self, tmp_path: Path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "app.py").write_text("def run(): pass", encoding="utf-8")
        (src_dir / "util.py").write_text("def helper(): pass", encoding="utf-8")

        ingestor = ArtifactIngestor()
        rules = [
            IngestionRule(pattern="src/*.py", artifact_type=ArtifactType.SOURCE_CODE)
        ]
        artifacts = ingestor.ingest(tmp_path, rules)

        assert len(artifacts) == 2
        assert [a.id for a in artifacts] == ["src/app.py", "src/util.py"]
        assert all(a.artifact_type == ArtifactType.SOURCE_CODE for a in artifacts)

    def test_test_case_files(self, tmp_path: Path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_auth.py").write_text(
            "def test_login(): assert True", encoding="utf-8"
        )

        ingestor = ArtifactIngestor()
        rules = [
            IngestionRule(pattern="tests/*.py", artifact_type=ArtifactType.TEST_CASE)
        ]
        artifacts = ingestor.ingest(tmp_path, rules)

        assert len(artifacts) == 1
        assert artifacts[0].id == "tests/test_auth.py"
        assert artifacts[0].artifact_type == ArtifactType.TEST_CASE

    def test_recursive_discovery(self, tmp_path: Path):
        nested_dir = tmp_path / "src" / "core" / "auth"
        nested_dir.mkdir(parents=True)
        (nested_dir / "jwt.py").write_text("SECRET = 'test'", encoding="utf-8")

        ingestor = ArtifactIngestor()
        rules = [
            IngestionRule(pattern="src/**/*.py", artifact_type=ArtifactType.SOURCE_CODE)
        ]
        artifacts = ingestor.ingest(tmp_path, rules)

        assert len(artifacts) == 1
        assert artifacts[0].id == "src/core/auth/jwt.py"
        assert artifacts[0].file_path == "src/core/auth/jwt.py"

    def test_posix_id_generation_on_windows(self, tmp_path: Path):
        subdir = tmp_path / "modules" / "submodule"
        subdir.mkdir(parents=True)
        target_file = subdir / "service.py"
        target_file.write_text("class Service: pass", encoding="utf-8")

        ingestor = ArtifactIngestor()
        rules = [
            IngestionRule(
                pattern="modules/**/*.py", artifact_type=ArtifactType.SOURCE_CODE
            )
        ]
        artifacts = ingestor.ingest(tmp_path, rules)

        assert len(artifacts) == 1
        art = artifacts[0]
        # Ensure forward slashes only regardless of Windows host
        assert "\\" not in art.id
        assert "\\" not in art.file_path
        assert "\\" not in art.metadata["relative_path"]
        assert art.id == "modules/submodule/service.py"
        assert art.file_path == "modules/submodule/service.py"

    def test_deterministic_ordering(self, tmp_path: Path):
        # Create files in non-alphabetical order
        (tmp_path / "z.py").write_text("z = 1", encoding="utf-8")
        (tmp_path / "a.py").write_text("a = 1", encoding="utf-8")
        (tmp_path / "m.py").write_text("m = 1", encoding="utf-8")

        ingestor = ArtifactIngestor()
        rules = [IngestionRule(pattern="*.py", artifact_type=ArtifactType.SOURCE_CODE)]
        artifacts = ingestor.ingest(tmp_path, rules)

        ids = [a.id for a in artifacts]
        assert ids == ["a.py", "m.py", "z.py"]

    def test_raw_content_preserved_exactly(self, tmp_path: Path):
        content = "def calculate(a, b):\n\t# Tabs & spaces\n    return a + b\n\r\n"
        code_file = tmp_path / "calc.py"
        code_file.write_bytes(content.encode("utf-8"))

        ingestor = ArtifactIngestor()
        rules = [IngestionRule(pattern="*.py", artifact_type=ArtifactType.SOURCE_CODE)]
        artifacts = ingestor.ingest(tmp_path, rules)

        assert len(artifacts) == 1
        assert artifacts[0].raw_content == content

    def test_content_initially_equals_raw_content(self, tmp_path: Path):
        code_file = tmp_path / "test.py"
        code_file.write_text("x = 100\n", encoding="utf-8", newline="\n")

        ingestor = ArtifactIngestor()
        rules = [IngestionRule(pattern="*.py", artifact_type=ArtifactType.SOURCE_CODE)]
        artifacts = ingestor.ingest(tmp_path, rules)

        assert artifacts[0].content == artifacts[0].raw_content
        assert artifacts[0].content == "x = 100\n"

    def test_metadata_contains_path_extension_language(self, tmp_path: Path):
        (tmp_path / "logic.py").write_text("pass", encoding="utf-8")
        (tmp_path / "doc.md").write_text("# Title", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("Some text", encoding="utf-8")

        ingestor = ArtifactIngestor()
        rules = [
            IngestionRule(pattern="*.py", artifact_type=ArtifactType.SOURCE_CODE),
            IngestionRule(pattern="*.md", artifact_type=ArtifactType.REQUIREMENT),
            IngestionRule(pattern="*.txt", artifact_type=ArtifactType.REQUIREMENT),
        ]
        artifacts = ingestor.ingest(tmp_path, rules)

        meta_by_id = {a.id: a.metadata for a in artifacts}

        assert meta_by_id["logic.py"]["relative_path"] == "logic.py"
        assert meta_by_id["logic.py"]["extension"] == ".py"
        assert meta_by_id["logic.py"]["language"] == "python"

        assert meta_by_id["doc.md"]["relative_path"] == "doc.md"
        assert meta_by_id["doc.md"]["extension"] == ".md"
        assert meta_by_id["doc.md"]["language"] == "markdown"

        assert meta_by_id["notes.txt"]["relative_path"] == "notes.txt"
        assert meta_by_id["notes.txt"]["extension"] == ".txt"
        assert meta_by_id["notes.txt"]["language"] == "text"

    def test_excluded_directories_are_ignored(self, tmp_path: Path):
        # Create files in excluded dirs
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config.txt").write_text("git config", encoding="utf-8")

        venv_dir = tmp_path / ".venv" / "lib"
        venv_dir.mkdir(parents=True)
        (venv_dir / "site.py").write_text("venv code", encoding="utf-8")

        pycache_dir = tmp_path / "src" / "__pycache__"
        pycache_dir.mkdir(parents=True)
        (pycache_dir / "cache.py").write_text("bytecode", encoding="utf-8")

        node_dir = tmp_path / "node_modules"
        node_dir.mkdir()
        (node_dir / "package.txt").write_text("node modules", encoding="utf-8")

        # Valid source file
        (tmp_path / "src" / "valid.py").write_text("valid = True", encoding="utf-8")

        ingestor = ArtifactIngestor()
        rules = [
            IngestionRule(pattern="**/*.py", artifact_type=ArtifactType.SOURCE_CODE),
            IngestionRule(pattern="**/*.txt", artifact_type=ArtifactType.REQUIREMENT),
        ]
        artifacts = ingestor.ingest(tmp_path, rules)

        ids = [a.id for a in artifacts]
        assert ids == ["src/valid.py"]

    def test_unsupported_extensions_are_ignored(self, tmp_path: Path):
        (tmp_path / "data.csv").write_text("a,b,c", encoding="utf-8")
        (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (tmp_path / "config.json").write_text("{}", encoding="utf-8")
        (tmp_path / "valid.py").write_text("x = 1", encoding="utf-8")

        ingestor = ArtifactIngestor()
        rules = [IngestionRule(pattern="**/*", artifact_type=ArtifactType.SOURCE_CODE)]
        artifacts = ingestor.ingest(tmp_path, rules)

        assert len(artifacts) == 1
        assert artifacts[0].id == "valid.py"

    def test_nonexistent_root(self, tmp_path: Path):
        nonexistent = tmp_path / "does_not_exist"
        ingestor = ArtifactIngestor()
        rules = [IngestionRule(pattern="*.py", artifact_type=ArtifactType.SOURCE_CODE)]

        with pytest.raises(ValueError, match="does not exist"):
            ingestor.ingest(nonexistent, rules)

    def test_root_is_a_file_instead_of_directory(self, tmp_path: Path):
        file_root = tmp_path / "file.txt"
        file_root.write_text("not a directory", encoding="utf-8")

        ingestor = ArtifactIngestor()
        rules = [IngestionRule(pattern="*.txt", artifact_type=ArtifactType.REQUIREMENT)]

        with pytest.raises(ValueError, match="not a directory"):
            ingestor.ingest(file_root, rules)

    def test_empty_rules(self, tmp_path: Path):
        ingestor = ArtifactIngestor()
        with pytest.raises(ValueError, match="Rule collection cannot be empty"):
            ingestor.ingest(tmp_path, [])

    def test_invalid_utf8(self, tmp_path: Path):
        bad_file = tmp_path / "corrupted.py"
        bad_file.write_bytes(b"\xff\xfe\x00\x00\x80\x81")

        ingestor = ArtifactIngestor()
        rules = [IngestionRule(pattern="*.py", artifact_type=ArtifactType.SOURCE_CODE)]

        with pytest.raises(IngestionEncodingError, match="not valid UTF-8"):
            ingestor.ingest(tmp_path, rules)

    def test_unreadable_file_raises_ingestion_file_error(self, tmp_path: Path):
        (tmp_path / "broken.py").write_text("code = 1", encoding="utf-8")
        ingestor = ArtifactIngestor()
        rules = [IngestionRule(pattern="*.py", artifact_type=ArtifactType.SOURCE_CODE)]

        with (
            patch.object(
                Path, "read_bytes", side_effect=OSError("Simulated read error")
            ),
            pytest.raises(IngestionFileError, match="Failed to read file"),
        ):
            ingestor.ingest(tmp_path, rules)

    def test_ambiguous_matching_rules(self, tmp_path: Path):
        (tmp_path / "test_auth.py").write_text(
            "def test_login(): pass", encoding="utf-8"
        )

        ingestor = ArtifactIngestor()
        rules = [
            IngestionRule(pattern="*.py", artifact_type=ArtifactType.SOURCE_CODE),
            IngestionRule(pattern="test_*.py", artifact_type=ArtifactType.TEST_CASE),
        ]

        with pytest.raises(AmbiguousRuleError, match="Ambiguous rule match"):
            ingestor.ingest(tmp_path, rules)

    def test_duplicate_file_discovery_does_not_create_duplicate_artifacts(
        self, tmp_path: Path
    ):
        (tmp_path / "service.py").write_text("class Service: pass", encoding="utf-8")

        ingestor = ArtifactIngestor()
        # Duplicate identical rules in configuration
        rules = [
            IngestionRule(pattern="*.py", artifact_type=ArtifactType.SOURCE_CODE),
            IngestionRule(pattern="*.py", artifact_type=ArtifactType.SOURCE_CODE),
        ]
        artifacts = ingestor.ingest(tmp_path, rules)

        assert len(artifacts) == 1
        assert artifacts[0].id == "service.py"
