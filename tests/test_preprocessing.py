"""Unit tests for the TraceWise preprocessing pipeline.

Covers normalization, identifier splitting, tokenization,
the ProcessedText model, and the Preprocessor orchestrator.
"""

import copy

import pytest
from pydantic import ValidationError

from tracewise.models.artifact import Artifact, ArtifactType
from tracewise.models.artifact_chunk import ArtifactChunk
from tracewise.preprocessing import (
    Preprocessor,
    ProcessedText,
    normalize_case,
    normalize_text,
    normalize_unicode,
    normalize_whitespace,
    split_identifier,
    tokenize,
)

# -----------------------------------------------------------------------
# Normalization
# -----------------------------------------------------------------------


class TestNormalizeUnicode:
    def test_nfc_normalization(self):
        # é as combining sequence (e + combining acute) → single codepoint
        decomposed = "caf\u0065\u0301"
        composed = "caf\u00e9"
        assert normalize_unicode(decomposed) == composed

    def test_already_nfc(self):
        text = "hello world"
        assert normalize_unicode(text) == text

    def test_empty_string(self):
        assert normalize_unicode("") == ""


class TestNormalizeCase:
    def test_lowercase_conversion(self):
        assert normalize_case("Hello WORLD") == "hello world"

    def test_already_lowercase(self):
        assert normalize_case("hello") == "hello"

    def test_mixed_case_with_numbers(self):
        assert normalize_case("HTTP401") == "http401"

    def test_empty_string(self):
        assert normalize_case("") == ""


class TestNormalizeWhitespace:
    def test_collapse_spaces(self):
        assert normalize_whitespace("hello   world") == "hello world"

    def test_collapse_tabs(self):
        assert normalize_whitespace("hello\t\tworld") == "hello world"

    def test_collapse_newlines(self):
        assert normalize_whitespace("hello\n\nworld") == "hello world"

    def test_mixed_whitespace(self):
        assert normalize_whitespace("  hello \t\n  world  ") == "hello world"

    def test_empty_string(self):
        assert normalize_whitespace("") == ""

    def test_whitespace_only(self):
        assert normalize_whitespace("   \t\n  ") == ""


class TestNormalizeText:
    def test_full_pipeline(self):
        text = "  Hello   WORLD  "
        assert normalize_text(text) == "hello world"

    def test_unicode_and_case_and_whitespace(self):
        text = "Caf\u0065\u0301   TEST"
        result = normalize_text(text)
        assert result == "caf\u00e9 test"

    def test_preserves_numbers(self):
        assert normalize_text("HTTP 401") == "http 401"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_whitespace_only_string(self):
        assert normalize_text("   ") == ""

    def test_requirement_prose(self):
        text = (
            "The system SHALL authenticate users by verifying "
            "their email address and password."
        )
        expected = (
            "the system shall authenticate users by verifying "
            "their email address and password."
        )
        assert normalize_text(text) == expected


# -----------------------------------------------------------------------
# Identifier splitting
# -----------------------------------------------------------------------


class TestSplitIdentifier:
    def test_camel_case(self):
        assert split_identifier("authenticateUser") == ["authenticate", "user"]

    def test_pascal_case(self):
        assert split_identifier("AuthenticationService") == [
            "authentication",
            "service",
        ]

    def test_snake_case(self):
        assert split_identifier("get_user_profile") == ["get", "user", "profile"]

    def test_kebab_case(self):
        assert split_identifier("test-case-id") == ["test", "case", "id"]

    def test_acronym_at_start(self):
        assert split_identifier("HTTPResponse") == ["http", "response"]

    def test_acronym_in_middle(self):
        assert split_identifier("parseHTTPResponse") == [
            "parse",
            "http",
            "response",
        ]

    def test_acronym_with_digits(self):
        assert split_identifier("SHA256Hasher") == ["sha256", "hasher"]

    def test_get_json_data(self):
        assert split_identifier("getJSONData") == ["get", "json", "data"]

    def test_oauth2_client(self):
        # O is a single uppercase letter, then Auth2 is camelCase, then Client
        result = split_identifier("OAuth2Client")
        assert "auth2" in result or "auth" in result
        assert "client" in result

    def test_dunder_init(self):
        assert split_identifier("__init__") == ["init"]

    def test_dunder_main(self):
        assert split_identifier("__main__") == ["main"]

    def test_leading_underscores(self):
        assert split_identifier("_private_method") == ["private", "method"]

    def test_short_tokens_preserved(self):
        assert split_identifier("id") == ["id"]
        assert split_identifier("ip") == ["ip"]
        assert split_identifier("db") == ["db"]
        assert split_identifier("v2") == ["v2"]

    def test_empty_string(self):
        assert split_identifier("") == []

    def test_underscores_only(self):
        assert split_identifier("___") == []

    def test_single_word(self):
        assert split_identifier("authenticate") == ["authenticate"]

    def test_all_uppercase(self):
        assert split_identifier("HTTP") == ["http"]

    def test_mixed_snake_and_camel(self):
        assert split_identifier("get_userName") == ["get", "user", "name"]

    def test_process_user_data(self):
        assert split_identifier("process_user_data") == ["process", "user", "data"]

    def test_numbers_in_identifier(self):
        assert split_identifier("base64Encode") == ["base64", "encode"]


# -----------------------------------------------------------------------
# Tokenization
# -----------------------------------------------------------------------


class TestTokenize:
    def test_simple_text(self):
        assert tokenize("hello world") == ["hello", "world"]

    def test_punctuation_removed(self):
        assert tokenize("hello, world!") == ["hello", "world"]

    def test_numbers_preserved(self):
        assert tokenize("http 401 error") == ["http", "401", "error"]

    def test_identifier_splitting_in_text(self):
        tokens = tokenize("authenticateUser get_profile")
        assert tokens == ["authenticate", "user", "get", "profile"]

    def test_kebab_in_text(self):
        tokens = tokenize("test-case-id works")
        assert tokens == ["test", "case", "id", "works"]

    def test_empty_string(self):
        assert tokenize("") == []

    def test_punctuation_only(self):
        assert tokenize("...!!!???") == []

    def test_http_401_response(self):
        tokens = tokenize("generate an http-401 response")
        assert tokens == ["generate", "an", "http", "401", "response"]

    def test_code_with_parentheses(self):
        tokens = tokenize("def authenticate_user(email, password):")
        assert "def" in tokens
        assert "authenticate" in tokens
        assert "user" in tokens
        assert "email" in tokens
        assert "password" in tokens

    def test_comment_text(self):
        tokens = tokenize("# verify the user's credentials")
        assert "verify" in tokens
        assert "the" in tokens
        assert "user" in tokens
        assert "s" in tokens
        assert "credentials" in tokens

    def test_docstring_text(self):
        text = '"""Authenticate a user by email and password."""'
        tokens = tokenize(text)
        assert "authenticate" in tokens
        assert "user" in tokens
        assert "email" in tokens
        assert "password" in tokens

    def test_mixed_content(self):
        text = "def parseHTTPResponse(self): return 401"
        tokens = tokenize(text)
        assert "def" in tokens
        assert "parse" in tokens
        assert "http" in tokens
        assert "response" in tokens
        assert "self" in tokens
        assert "return" in tokens
        assert "401" in tokens


# -----------------------------------------------------------------------
# ProcessedText model
# -----------------------------------------------------------------------


class TestProcessedText:
    def test_creation(self):
        pt = ProcessedText(
            source_id="REQ-001",
            original_text="Hello World",
            normalized_text="hello world",
            tokens=["hello", "world"],
        )
        assert pt.source_id == "REQ-001"
        assert pt.original_text == "Hello World"
        assert pt.normalized_text == "hello world"
        assert pt.tokens == ["hello", "world"]
        assert pt.metadata == {}

    def test_creation_with_metadata(self):
        pt = ProcessedText(
            source_id="src/auth.py#login",
            original_text="def login():",
            normalized_text="def login():",
            tokens=["def", "login"],
            metadata={"artifact_type": "SOURCE_CODE"},
        )
        assert pt.metadata["artifact_type"] == "SOURCE_CODE"

    def test_empty_source_id_raises(self):
        with pytest.raises(ValidationError, match="source_id"):
            ProcessedText(
                source_id="",
                original_text="text",
                normalized_text="text",
                tokens=["text"],
            )

    def test_whitespace_source_id_raises(self):
        with pytest.raises(ValidationError, match="source_id"):
            ProcessedText(
                source_id="   ",
                original_text="text",
                normalized_text="text",
                tokens=["text"],
            )

    def test_source_id_stripped(self):
        pt = ProcessedText(
            source_id="  REQ-001  ",
            original_text="text",
            normalized_text="text",
            tokens=["text"],
        )
        assert pt.source_id == "REQ-001"

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            ProcessedText(
                source_id="REQ-001",
                original_text="text",
                normalized_text="text",
                tokens=["text"],
                tfidf_vector=[0.1, 0.2],  # type: ignore[call-arg]
            )

    def test_default_empty_tokens(self):
        pt = ProcessedText(
            source_id="REQ-001",
            original_text="",
            normalized_text="",
        )
        assert pt.tokens == []

    def test_default_empty_metadata(self):
        pt = ProcessedText(
            source_id="REQ-001",
            original_text="text",
            normalized_text="text",
        )
        assert pt.metadata == {}


# -----------------------------------------------------------------------
# Preprocessor
# -----------------------------------------------------------------------


def _make_artifact(
    artifact_id: str = "test-artifact",
    artifact_type: ArtifactType = ArtifactType.SOURCE_CODE,
    content: str = "def hello(): pass",
) -> Artifact:
    """Helper to build an Artifact for testing."""
    return Artifact(
        id=artifact_id,
        artifact_type=artifact_type,
        file_path="src/test.py",
        raw_content=content,
        content=content,
    )


def _make_chunk(
    chunk_id: str = "src/test.py#hello",
    parent_id: str = "test-artifact",
    name: str = "hello",
    content: str = "def hello(): pass",
) -> ArtifactChunk:
    """Helper to build an ArtifactChunk for testing."""
    return ArtifactChunk(
        id=chunk_id,
        parent_id=parent_id,
        name=name,
        raw_content=content,
        content=content,
        start_line=1,
        end_line=1,
        metadata={"chunk_type": "function"},
    )


class TestPreprocessor:
    def test_process_text_basic(self):
        p = Preprocessor()
        result = p.process_text("test-id", "Hello World")
        assert result.source_id == "test-id"
        assert result.original_text == "Hello World"
        assert result.normalized_text == "hello world"
        assert result.tokens == ["hello", "world"]

    def test_process_text_preserves_original(self):
        p = Preprocessor()
        original = "  Generate an HTTP-401 Response.  "
        result = p.process_text("test-id", original)
        assert result.original_text == original
        assert result.original_text is not result.normalized_text

    def test_process_text_with_metadata(self):
        p = Preprocessor()
        result = p.process_text("test-id", "text", metadata={"custom": "value"})
        assert result.metadata == {"custom": "value"}

    def test_process_text_empty_string(self):
        p = Preprocessor()
        result = p.process_text("test-id", "")
        assert result.original_text == ""
        assert result.normalized_text == ""
        assert result.tokens == []

    def test_process_text_whitespace_only(self):
        p = Preprocessor()
        result = p.process_text("test-id", "   \t\n  ")
        assert result.original_text == "   \t\n  "
        assert result.normalized_text == ""
        assert result.tokens == []

    def test_process_artifact(self):
        p = Preprocessor()
        artifact = _make_artifact(
            artifact_id="src/auth/service.py",
            artifact_type=ArtifactType.SOURCE_CODE,
            content="def authenticate_user(email, password): pass",
        )
        result = p.process_artifact(artifact)
        assert result.source_id == "src/auth/service.py"
        assert "authenticate" in result.tokens
        assert "user" in result.tokens
        assert "email" in result.tokens
        assert "password" in result.tokens
        assert result.metadata["artifact_type"] == "SOURCE_CODE"

    def test_process_artifact_requirement(self):
        p = Preprocessor()
        artifact = _make_artifact(
            artifact_id="REQ-001",
            artifact_type=ArtifactType.REQUIREMENT,
            content="The system shall authenticate users via email.",
        )
        result = p.process_artifact(artifact)
        assert result.source_id == "REQ-001"
        assert result.metadata["artifact_type"] == "REQUIREMENT"
        assert "authenticate" in result.tokens
        assert "users" in result.tokens

    def test_process_chunk(self):
        p = Preprocessor()
        chunk = _make_chunk(
            chunk_id="src/auth/service.py#AuthService.login",
            content="def login(self, email, password): pass",
        )
        result = p.process_chunk(chunk)
        assert result.source_id == "src/auth/service.py#AuthService.login"
        assert "login" in result.tokens
        assert result.metadata["chunk_type"] == "function"

    def test_no_mutation_of_artifact(self):
        p = Preprocessor()
        artifact = _make_artifact()
        original_dict = artifact.model_dump()
        p.process_artifact(artifact)
        assert artifact.model_dump() == original_dict

    def test_no_mutation_of_chunk(self):
        p = Preprocessor()
        chunk = _make_chunk()
        original_dict = chunk.model_dump()
        p.process_chunk(chunk)
        assert chunk.model_dump() == original_dict

    def test_no_mutation_deep_copy_equivalence(self):
        p = Preprocessor()
        artifact = _make_artifact(content="def complex_func(): pass")
        artifact_copy = copy.deepcopy(artifact)
        p.process_artifact(artifact)
        assert artifact.model_dump() == artifact_copy.model_dump()

    def test_determinism(self):
        p = Preprocessor()
        text = "parseHTTPResponse authenticate_user SHA256"
        r1 = p.process_text("test-id", text)
        r2 = p.process_text("test-id", text)
        assert r1.normalized_text == r2.normalized_text
        assert r1.tokens == r2.tokens

    def test_determinism_across_instances(self):
        p1 = Preprocessor()
        p2 = Preprocessor()
        text = "Generate an HTTP-401 response."
        r1 = p1.process_text("test-id", text)
        r2 = p2.process_text("test-id", text)
        assert r1.normalized_text == r2.normalized_text
        assert r1.tokens == r2.tokens


# -----------------------------------------------------------------------
# Requirement text preprocessing
# -----------------------------------------------------------------------


class TestRequirementPreprocessing:
    def test_requirement_prose(self):
        p = Preprocessor()
        text = (
            "The system shall authenticate users by verifying their "
            "email address and password against stored credentials."
        )
        result = p.process_text("REQ-001", text)
        assert "authenticate" in result.tokens
        assert "users" in result.tokens
        assert "email" in result.tokens
        assert "password" in result.tokens
        assert "credentials" in result.tokens

    def test_requirement_with_http_code(self):
        p = Preprocessor()
        text = (
            "When authentication fails, the system shall return "
            "HTTP status code 401 (Unauthorized)."
        )
        result = p.process_text("REQ-003", text)
        assert "401" in result.tokens
        assert "http" in result.tokens
        assert "unauthorized" in result.tokens

    def test_requirement_with_duration(self):
        p = Preprocessor()
        text = (
            "Access tokens shall expire after a configurable duration. "
            "The default expiration duration shall be 3600 seconds."
        )
        result = p.process_text("REQ-005", text)
        assert "3600" in result.tokens
        assert "expire" in result.tokens
        assert "tokens" in result.tokens


# -----------------------------------------------------------------------
# Python/source code preprocessing
# -----------------------------------------------------------------------


class TestCodePreprocessing:
    def test_function_definition(self):
        p = Preprocessor()
        code = '''def authenticate_user(email, password):
    """Authenticate a user by email and password."""
    if not verify_password(password, stored_hash):
        return AuthenticationResult(success=False, status_code=401)
    return AuthenticationResult(success=True, token=token)
'''
        result = p.process_text("src/auth/service.py#authenticate_user", code)
        assert "authenticate" in result.tokens
        assert "user" in result.tokens
        assert "email" in result.tokens
        assert "password" in result.tokens
        assert "401" in result.tokens
        assert "verify" in result.tokens

    def test_class_definition(self):
        p = Preprocessor()
        code = '''class RateLimiter:
    """Enforces rate limiting on repeated failed authentication attempts."""
    DEFAULT_MAX_FAILURES = 5
'''
        result = p.process_text("src/security/rate_limiter.py#RateLimiter", code)
        assert "rate" in result.tokens
        assert "limiter" in result.tokens
        assert "5" in result.tokens
        assert "authentication" in result.tokens

    def test_test_function(self):
        p = Preprocessor()
        code = '''def test_invalid_password_returns_401():
    """Verify that a wrong password returns HTTP 401 Unauthorized."""
    result = service.authenticate_user("alice@example.com", "wrong")
    assert result.status_code == 401
'''
        result = p.process_text(
            "tests/test_auth.py#test_invalid_password_returns_401", code
        )
        assert "invalid" in result.tokens
        assert "password" in result.tokens
        assert "401" in result.tokens
        assert "authenticate" in result.tokens


# -----------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------


class TestEdgeCases:
    def test_unicode_characters(self):
        p = Preprocessor()
        result = p.process_text("test", "Stra\u00dfe caf\u00e9")
        assert result.normalized_text == "stra\u00dfe caf\u00e9"

    def test_numbers_only(self):
        p = Preprocessor()
        result = p.process_text("test", "401 200 500")
        assert result.tokens == ["401", "200", "500"]

    def test_single_character_tokens(self):
        p = Preprocessor()
        result = p.process_text("test", "a b c")
        assert result.tokens == ["a", "b", "c"]

    def test_mixed_separators(self):
        p = Preprocessor()
        result = p.process_text("test", "camelCase snake_case kebab-case")
        assert "camel" in result.tokens
        assert "case" in result.tokens
        assert "snake" in result.tokens
        assert "kebab" in result.tokens

    def test_multiline_code(self):
        p = Preprocessor()
        code = "def foo():\n    x = 42\n    return x\n"
        result = p.process_text("test", code)
        assert "foo" in result.tokens
        assert "42" in result.tokens
        assert "return" in result.tokens

    def test_original_text_never_modified(self):
        p = Preprocessor()
        original = "  CamelCase\t\tSNAKE_CASE  \n"
        result = p.process_text("test", original)
        assert result.original_text == original
        assert result.original_text == "  CamelCase\t\tSNAKE_CASE  \n"
