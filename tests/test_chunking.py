"""Comprehensive tests for deterministic Python structural artifact chunking."""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from tracewise import (
    Artifact,
    ArtifactChunk,
    ArtifactType,
    BaseChunker,
    ChunkingError,
    PythonChunker,
    PythonParsingError,
    UnsupportedArtifactTypeError,
)


@pytest.fixture
def chunker() -> PythonChunker:
    return PythonChunker()


def _make_artifact(
    code: str,
    file_path: str = "src/example.py",
    artifact_type: ArtifactType = ArtifactType.SOURCE_CODE,
    artifact_id: str | None = None,
) -> Artifact:
    return Artifact(
        id=artifact_id or file_path,
        artifact_type=artifact_type,
        file_path=file_path,
        raw_content=code,
        content=code,
    )


class TestPythonChunkerBaseContract:
    def test_implements_base_chunker(self, chunker: PythonChunker):
        assert isinstance(chunker, BaseChunker)

    def test_unsupported_artifact_type_raises(self, chunker: PythonChunker):
        art = _make_artifact(
            code="def foo(): pass\n",
            file_path="docs/spec.md",
            artifact_type=ArtifactType.REQUIREMENT,
        )
        with pytest.raises(UnsupportedArtifactTypeError, match="unsupported type"):
            chunker.chunk(art)

    def test_non_python_extension_raises(self, chunker: PythonChunker):
        art = _make_artifact(
            code="public class Foo {}\n",
            file_path="src/Foo.java",
            artifact_type=ArtifactType.SOURCE_CODE,
        )
        with pytest.raises(UnsupportedArtifactTypeError, match="not a Python"):
            chunker.chunk(art)


class TestPythonChunkerStructuralExtraction:
    def test_1_empty_python_file(self, chunker: PythonChunker):
        # Empty file
        empty_art = _make_artifact("")
        assert chunker.chunk(empty_art) == []

        # Whitespace-only file
        ws_art = _make_artifact("   \n\t  \n  ")
        assert chunker.chunk(ws_art) == []

        # Comments only (no functions/classes)
        comments_art = _make_artifact("# Just a comment\n# Another comment\n")
        assert chunker.chunk(comments_art) == []

    def test_2_one_top_level_function(self, chunker: PythonChunker):
        code = "def calculate_sum(a: int, b: int) -> int:\n    return a + b\n"
        art = _make_artifact(code, file_path="src/math_ops.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 1
        fn = chunks[0]
        assert fn.id == "src/math_ops.py#calculate_sum"
        assert fn.parent_id == "src/math_ops.py"
        assert fn.name == "calculate_sum"
        assert fn.start_line == 1
        assert fn.end_line == 2
        assert fn.raw_content == code
        assert fn.content == code
        assert fn.metadata["chunk_type"] == "function"
        assert fn.metadata["is_async"] is False
        assert fn.metadata["docstring"] == ""

    def test_3_one_async_function(self, chunker: PythonChunker):
        code = "async def fetch_data(url: str) -> bytes:\n    return b'result'\n"
        art = _make_artifact(code, file_path="src/network.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 1
        fn = chunks[0]
        assert fn.id == "src/network.py#fetch_data"
        assert fn.parent_id == "src/network.py"
        assert fn.name == "fetch_data"
        assert fn.start_line == 1
        assert fn.end_line == 2
        assert fn.raw_content == code
        assert fn.content == code
        assert fn.metadata["chunk_type"] == "function"
        assert fn.metadata["is_async"] is True
        assert fn.metadata["docstring"] == ""

    def test_4_one_class(self, chunker: PythonChunker):
        code = "class EmptyService:\n    pass\n"
        art = _make_artifact(code, file_path="src/service.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 1
        cls = chunks[0]
        assert cls.id == "src/service.py#EmptyService"
        assert cls.parent_id == "src/service.py"
        assert cls.name == "EmptyService"
        assert cls.start_line == 1
        assert cls.end_line == 2
        assert cls.raw_content == code
        assert cls.content == code
        assert cls.metadata["chunk_type"] == "class"
        assert cls.metadata["docstring"] == ""
        assert "is_async" not in cls.metadata

    def test_5_class_with_multiple_methods(self, chunker: PythonChunker):
        code = (
            "class Calculator:\n"
            "    def add(self, a, b):\n"
            "        return a + b\n"
            "\n"
            "    def subtract(self, a, b):\n"
            "        return a - b\n"
        )
        art = _make_artifact(code, file_path="src/calc.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 3
        cls_chunk = chunks[0]
        m1 = chunks[1]
        m2 = chunks[2]

        # Class chunk
        assert cls_chunk.id == "src/calc.py#Calculator"
        assert cls_chunk.parent_id == "src/calc.py"
        assert cls_chunk.name == "Calculator"
        assert cls_chunk.start_line == 1
        assert cls_chunk.end_line == 6
        assert cls_chunk.raw_content == code
        assert cls_chunk.metadata["chunk_type"] == "class"

        # Method 1
        assert m1.id == "src/calc.py#Calculator.add"
        assert m1.parent_id == "src/calc.py#Calculator"
        assert m1.name == "add"
        assert m1.start_line == 2
        assert m1.end_line == 3
        expected_m1 = "    def add(self, a, b):\n        return a + b\n"
        assert m1.raw_content == expected_m1
        assert m1.content == expected_m1
        assert m1.metadata["chunk_type"] == "method"
        assert m1.metadata["is_async"] is False

        # Method 2
        assert m2.id == "src/calc.py#Calculator.subtract"
        assert m2.parent_id == "src/calc.py#Calculator"
        assert m2.name == "subtract"
        assert m2.start_line == 5
        assert m2.end_line == 6
        expected_m2 = "    def subtract(self, a, b):\n        return a - b\n"
        assert m2.raw_content == expected_m2
        assert m2.content == expected_m2
        assert m2.metadata["chunk_type"] == "method"
        assert m2.metadata["is_async"] is False

    def test_6_async_method(self, chunker: PythonChunker):
        code = (
            "class Client:\n"
            "    async def send(self, data: bytes) -> bool:\n"
            "        return True\n"
        )
        art = _make_artifact(code, file_path="src/client.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 2
        cls_chunk, method_chunk = chunks

        assert cls_chunk.id == "src/client.py#Client"
        assert method_chunk.id == "src/client.py#Client.send"
        assert method_chunk.parent_id == "src/client.py#Client"
        assert method_chunk.name == "send"
        assert method_chunk.start_line == 2
        assert method_chunk.end_line == 3
        assert method_chunk.metadata["chunk_type"] == "method"
        assert method_chunk.metadata["is_async"] is True

    def test_7_decorated_function(self, chunker: PythonChunker):
        code = (
            "# Top comment\n"
            "@decorator_one\n"
            "@decorator_two(param='val')\n"
            "def worker():\n"
            "    pass\n"
        )
        art = _make_artifact(code, file_path="src/tasks.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 1
        fn = chunks[0]
        assert fn.id == "src/tasks.py#worker"
        assert fn.start_line == 2
        assert fn.end_line == 5
        expected_slice = (
            "@decorator_one\n@decorator_two(param='val')\ndef worker():\n    pass\n"
        )
        assert fn.raw_content == expected_slice
        assert fn.content == expected_slice

    def test_8_decorated_class(self, chunker: PythonChunker):
        code = (
            "@dataclass\n"
            "@register('user')\n"
            "class UserRecord:\n"
            "    id: int\n"
            "    name: str\n"
        )
        art = _make_artifact(code, file_path="src/models.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 1
        cls = chunks[0]
        assert cls.id == "src/models.py#UserRecord"
        assert cls.start_line == 1
        assert cls.end_line == 5
        assert cls.raw_content == code

    def test_9_decorated_method(self, chunker: PythonChunker):
        code = (
            "class Handler:\n"
            "    @property\n"
            "    @lru_cache(maxsize=128)\n"
            "    def cached_val(self):\n"
            "        return 42\n"
        )
        art = _make_artifact(code, file_path="src/handler.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 2
        method = chunks[1]
        assert method.id == "src/handler.py#Handler.cached_val"
        assert method.parent_id == "src/handler.py#Handler"
        assert method.start_line == 2
        assert method.end_line == 5
        expected_method = (
            "    @property\n"
            "    @lru_cache(maxsize=128)\n"
            "    def cached_val(self):\n"
            "        return 42\n"
        )
        assert method.raw_content == expected_method
        assert method.content == expected_method

    def test_10_multiline_function_signature(self, chunker: PythonChunker):
        code = (
            "def complex_operation(\n"
            "    alpha: int,\n"
            "    beta: str,\n"
            "    gamma: float = 1.0,\n"
            ") -> bool:\n"
            "    return True\n"
        )
        art = _make_artifact(code, file_path="src/ops.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 1
        fn = chunks[0]
        assert fn.id == "src/ops.py#complex_operation"
        assert fn.start_line == 1
        assert fn.end_line == 6
        assert fn.raw_content == code
        assert fn.content == code

    def test_11_multiline_class_declaration(self, chunker: PythonChunker):
        code = "class ComplexService(\n    BaseService,\n    Protocol,\n):\n    pass\n"
        art = _make_artifact(code, file_path="src/service.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 1
        cls = chunks[0]
        assert cls.id == "src/service.py#ComplexService"
        assert cls.start_line == 1
        assert cls.end_line == 5
        assert cls.raw_content == code

    def test_12_function_with_docstring(self, chunker: PythonChunker):
        code = (
            "def authenticate():\n"
            '    """Authenticate caller credentials.\n'
            "\n"
            "    Returns True if valid.\n"
            '    """\n'
            "    return True\n"
        )
        art = _make_artifact(code, file_path="src/auth.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 1
        fn = chunks[0]
        assert (
            fn.metadata["docstring"]
            == "Authenticate caller credentials.\n\nReturns True if valid."
        )

    def test_13_class_with_docstring(self, chunker: PythonChunker):
        code = 'class Registry:\n    """Central symbol registry."""\n    pass\n'
        art = _make_artifact(code, file_path="src/reg.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 1
        cls = chunks[0]
        assert cls.metadata["docstring"] == "Central symbol registry."

    def test_14_method_with_docstring(self, chunker: PythonChunker):
        code = (
            "class Store:\n"
            "    def get(self, key: str):\n"
            '        """Retrieve key value."""\n'
            "        return None\n"
        )
        art = _make_artifact(code, file_path="src/store.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 2
        method = chunks[1]
        assert method.metadata["docstring"] == "Retrieve key value."

    def test_15_nested_function_is_not_emitted(self, chunker: PythonChunker):
        code = (
            "def outer_func():\n"
            "    def inner_func():\n"
            "        return 1\n"
            "    return inner_func()\n"
        )
        art = _make_artifact(code, file_path="src/nested.py")
        chunks = chunker.chunk(art)

        # Only the top-level outer_func is emitted
        assert len(chunks) == 1
        assert chunks[0].name == "outer_func"
        assert chunks[0].id == "src/nested.py#outer_func"
        assert chunks[0].start_line == 1
        assert chunks[0].end_line == 4
        # inner_func remains part of outer_func's raw_content
        assert "def inner_func():" in chunks[0].raw_content

    def test_16_nested_class_is_not_emitted(self, chunker: PythonChunker):
        code = (
            "class OuterClass:\n"
            "    class InnerClass:\n"
            "        pass\n"
            "    def method(self):\n"
            "        pass\n"
        )
        art = _make_artifact(code, file_path="src/nested_cls.py")
        chunks = chunker.chunk(art)

        # Only OuterClass and OuterClass.method are emitted, not InnerClass
        assert len(chunks) == 2
        assert chunks[0].name == "OuterClass"
        assert chunks[0].id == "src/nested_cls.py#OuterClass"
        assert chunks[1].name == "method"
        assert chunks[1].id == "src/nested_cls.py#OuterClass.method"
        # InnerClass remains inside OuterClass's raw_content
        assert "class InnerClass:" in chunks[0].raw_content

    def test_17_class_and_method_chunks_intentionally_overlap(
        self, chunker: PythonChunker
    ):
        code = (
            "class Account:\n"
            "    def deposit(self, amount: int):\n"
            "        self.balance += amount\n"
        )
        art = _make_artifact(code, file_path="src/account.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 2
        cls_chunk = chunks[0]
        method_chunk = chunks[1]

        # Both span line 2 and 3
        assert cls_chunk.start_line == 1
        assert cls_chunk.end_line == 3
        assert method_chunk.start_line == 2
        assert method_chunk.end_line == 3

        # Method source is a strict substring of class source
        assert method_chunk.raw_content in cls_chunk.raw_content
        assert method_chunk.raw_content == (
            "    def deposit(self, amount: int):\n        self.balance += amount\n"
        )

    def test_18_exact_start_line_and_end_line(self, chunker: PythonChunker):
        code = (
            "# Line 1\n"
            "# Line 2\n"
            "def fn_a():\n"
            "    pass\n"
            "# Line 5\n"
            "def fn_b():\n"
            "    x = 1\n"
            "    y = 2\n"
            "    return x + y\n"
        )
        art = _make_artifact(code, file_path="src/lines.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 2
        assert chunks[0].name == "fn_a"
        assert chunks[0].start_line == 3
        assert chunks[0].end_line == 4

        assert chunks[1].name == "fn_b"
        assert chunks[1].start_line == 6
        assert chunks[1].end_line == 9

    def test_19_exact_raw_content_preservation(self, chunker: PythonChunker):
        # Preserves irregular intra-line spaces, trailing spaces,
        # and exact newlines without normalization
        code = (
            "def irregular(  x: int,   y: int = 42  ) -> int:\n"
            '    """Irregular docstring with spaces."""   \n'
            "    res = x + y   \n"
            "    return res  \n"
        )
        art = _make_artifact(code, file_path="src/irregular.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 1
        fn = chunks[0]
        assert fn.raw_content == code
        assert fn.content == code
        # Assert exact preservation of intra-line and trailing spaces
        assert "def irregular(  x: int,   y: int = 42  ) -> int:\n" in fn.raw_content
        assert '    """Irregular docstring with spaces."""   \n' in fn.raw_content
        assert "    res = x + y   \n" in fn.raw_content
        assert "    return res  \n" in fn.raw_content

    def test_20_deterministic_ids(self, chunker: PythonChunker):
        code = "def step_one(): pass\nclass Flow:\n    def step_two(self): pass\n"
        art1 = _make_artifact(code, file_path="src/flow.py")
        art2 = _make_artifact(code, file_path="src/flow.py")

        chunks1 = chunker.chunk(art1)
        chunks2 = chunker.chunk(art2)

        assert [c.id for c in chunks1] == [c.id for c in chunks2]
        assert [c.parent_id for c in chunks1] == [c.parent_id for c in chunks2]
        assert [c.id for c in chunks1] == [
            "src/flow.py#step_one",
            "src/flow.py#Flow",
            "src/flow.py#Flow.step_two",
        ]
        assert [c.parent_id for c in chunks1] == [
            "src/flow.py",
            "src/flow.py",
            "src/flow.py#Flow",
        ]

    def test_21_windows_style_filesystem_path_preserved_as_is(
        self, chunker: PythonChunker
    ):
        code = "def win_func(): pass\n"
        # If artifact has Windows-style file_path, chunker preserves it as-is
        art = _make_artifact(
            code, file_path="src\\win\\task.py", artifact_id="src\\win\\task.py"
        )
        chunks = chunker.chunk(art)

        assert len(chunks) == 1
        assert chunks[0].id == "src\\win\\task.py#win_func"
        assert chunks[0].parent_id == "src\\win\\task.py"

    def test_22_syntax_error_raises_dedicated_exception(self, chunker: PythonChunker):
        code = "def broken_syntax(:\n    pass\n"
        art = _make_artifact(code, file_path="src/broken.py")

        with pytest.raises(PythonParsingError) as exc_info:
            chunker.chunk(art)

        # Exception must be a ChunkingError and mention file path
        assert issubclass(PythonParsingError, ChunkingError)
        assert "src/broken.py" in str(exc_info.value)
        assert "Syntax error" in str(exc_info.value)

    def test_23_malformed_missing_end_lineno_raises_exception(
        self, chunker: PythonChunker
    ):
        code = "def sample(): pass\n"
        art = _make_artifact(code, file_path="src/sample.py")

        # Mock ast.parse to return a FunctionDef node with end_lineno=None
        import ast

        original_parse = ast.parse

        def mock_parse(source, filename):
            tree = original_parse(source, filename=filename)
            tree.body[0].end_lineno = None
            return tree

        with patch(
            "tracewise.ingestion.python_chunker.ast.parse", side_effect=mock_parse
        ):
            with pytest.raises(
                PythonParsingError, match="invalid or missing end_lineno"
            ):
                chunker.chunk(art)

        # Also test end_lineno < start_line
        def mock_parse_inverted(source, filename):
            tree = original_parse(source, filename=filename)
            tree.body[0].end_lineno = tree.body[0].lineno - 1
            return tree

        with patch(
            "tracewise.ingestion.python_chunker.ast.parse",
            side_effect=mock_parse_inverted,
        ):
            with pytest.raises(
                PythonParsingError, match="invalid or missing end_lineno"
            ):
                chunker.chunk(art)

    def test_24_extra_artifact_chunk_fields_are_rejected(self):
        with pytest.raises(ValidationError):
            ArtifactChunk(
                id="src/a.py#fn",
                parent_id="src/a.py",
                name="fn",
                raw_content="def fn(): pass",
                content="def fn(): pass",
                start_line=1,
                end_line=1,
                unexpected_extra_field="rejected",
            )

    def test_25_invalid_artifact_chunk_line_ranges_are_rejected(self):
        # start_line < 1
        with pytest.raises(ValidationError, match="start_line"):
            ArtifactChunk(
                id="src/a.py#fn",
                parent_id="src/a.py",
                name="fn",
                raw_content="def fn(): pass",
                content="def fn(): pass",
                start_line=0,
                end_line=1,
            )

        # end_line < start_line
        with pytest.raises(ValidationError, match="cannot be less than start_line"):
            ArtifactChunk(
                id="src/a.py#fn",
                parent_id="src/a.py",
                name="fn",
                raw_content="def fn(): pass",
                content="def fn(): pass",
                start_line=10,
                end_line=9,
            )


class TestPythonChunkerTestCaseArtifact:
    def test_test_case_artifact_is_supported(self, chunker: PythonChunker):
        code = "def test_something():\n    assert True\n"
        art = _make_artifact(
            code, file_path="tests/test_foo.py", artifact_type=ArtifactType.TEST_CASE
        )
        chunks = chunker.chunk(art)

        assert len(chunks) == 1
        assert chunks[0].id == "tests/test_foo.py#test_something"
        assert chunks[0].name == "test_something"
        assert chunks[0].metadata["chunk_type"] == "function"


class TestPythonChunkerCollisionHandling:
    def test_duplicate_top_level_functions(self, chunker: PythonChunker):
        code = "def process():\n    pass\n\ndef process():\n    pass\n"
        art = _make_artifact(code, file_path="src/example.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 2
        fn1, fn2 = chunks

        assert fn1.id == "src/example.py#process@L1"
        assert fn1.parent_id == "src/example.py"
        assert fn1.name == "process"
        assert fn1.start_line == 1

        assert fn2.id == "src/example.py#process@L4"
        assert fn2.parent_id == "src/example.py"
        assert fn2.name == "process"
        assert fn2.start_line == 4

        # IDs must be distinct
        assert fn1.id != fn2.id

    def test_duplicate_top_level_class_and_function(self, chunker: PythonChunker):
        code = (
            "def Entity():\n"
            "    return None\n"
            "\n"
            "class Entity:\n"
            "    def get(self):\n"
            "        return 1\n"
        )
        art = _make_artifact(code, file_path="src/entity.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 3
        fn, cls_chunk, method = chunks

        assert fn.id == "src/entity.py#Entity@L1"
        assert fn.parent_id == "src/entity.py"
        assert fn.metadata["chunk_type"] == "function"

        assert cls_chunk.id == "src/entity.py#Entity@L4"
        assert cls_chunk.parent_id == "src/entity.py"
        assert cls_chunk.metadata["chunk_type"] == "class"

        # Method is unique within class; parent_id points to class chunk ID
        assert method.id == "src/entity.py#Entity.get"
        assert method.parent_id == "src/entity.py#Entity@L4"
        assert method.metadata["chunk_type"] == "method"

    def test_duplicate_methods_within_class(self, chunker: PythonChunker):
        code = (
            "class Service:\n"
            "    def run(self):\n"
            "        pass\n"
            "\n"
            "    def run(self):\n"
            "        pass\n"
        )
        art = _make_artifact(code, file_path="src/service.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 3
        cls_chunk, m1, m2 = chunks

        # Service class is unique, retains clean ID
        assert cls_chunk.id == "src/service.py#Service"
        assert cls_chunk.parent_id == "src/service.py"

        # Duplicate methods receive start_line discriminators
        assert m1.id == "src/service.py#Service.run@L2"
        assert m1.parent_id == "src/service.py#Service"
        assert m1.start_line == 2

        assert m2.id == "src/service.py#Service.run@L5"
        assert m2.parent_id == "src/service.py#Service"
        assert m2.start_line == 5

        assert m1.id != m2.id

    def test_three_or_more_duplicate_definitions(self, chunker: PythonChunker):
        code = (
            "def worker():\n"
            "    pass\n"
            "\n"
            "def worker():\n"
            "    pass\n"
            "\n"
            "def worker():\n"
            "    pass\n"
        )
        art = _make_artifact(code, file_path="src/workers.py")
        chunks = chunker.chunk(art)

        assert len(chunks) == 3
        assert [c.id for c in chunks] == [
            "src/workers.py#worker@L1",
            "src/workers.py#worker@L4",
            "src/workers.py#worker@L7",
        ]
        assert len({c.id for c in chunks}) == 3

    def test_deterministic_ids_across_repeated_chunking(self, chunker: PythonChunker):
        code = (
            "def task():\n"
            "    pass\n"
            "def task():\n"
            "    pass\n"
            "class Engine:\n"
            "    def exec(self): pass\n"
            "    def exec(self): pass\n"
        )
        art = _make_artifact(code, file_path="src/task.py")
        run1 = chunker.chunk(art)
        run2 = chunker.chunk(art)

        assert [c.id for c in run1] == [c.id for c in run2]
        assert [c.parent_id for c in run1] == [c.parent_id for c in run2]

    def test_unique_ids_across_all_returned_chunks(self, chunker: PythonChunker):
        code = (
            "def unique_func():\n"
            "    pass\n"
            "\n"
            "def dup_func():\n"
            "    pass\n"
            "\n"
            "def dup_func():\n"
            "    pass\n"
            "\n"
            "class Service:\n"
            "    def unique_method(self):\n"
            "        pass\n"
            "    def dup_method(self):\n"
            "        pass\n"
            "    def dup_method(self):\n"
            "        pass\n"
        )
        art = _make_artifact(code, file_path="src/mixed.py")
        chunks = chunker.chunk(art)

        # All generated IDs must be strictly unique
        ids = [c.id for c in chunks]
        assert len(ids) == len(set(ids))

        # Unique symbols must retain their clean unadorned IDs
        assert "src/mixed.py#unique_func" in ids
        assert "src/mixed.py#Service" in ids
        assert "src/mixed.py#Service.unique_method" in ids

        # Duplicate symbols must have source-line discriminator
        assert "src/mixed.py#dup_func@L4" in ids
        assert "src/mixed.py#dup_func@L7" in ids
        assert "src/mixed.py#Service.dup_method@L13" in ids
        assert "src/mixed.py#Service.dup_method@L15" in ids
