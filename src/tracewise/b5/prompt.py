"""Prompt construction, JSON schema validation, and parsing for TraceWise B5."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

B5_PROMPT_VERSION = "1.0.0"
# Frozen a-priori candidate code window: ~250 tokens per candidate
# (fits 20 candidates in 8k context window)
B5_MAX_CODE_CHARS: int = 1000


class B5ValidationError(Exception):
    """Raised when an LLM response violates the strict B5 output schema."""


class B5CandidateItem(BaseModel):
    """Normalized candidate code artifact supplied to the B5 LLM prompt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_id: str
    file_path: str | None = None
    code_text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class B5PromptBuilder:
    """Constructs the single fixed prompt template for B5 LLM relevance assessment.

    The prompt strictly separates:
    1. Requirement specification
    2. Candidate source-code snippets with identifiers
    3. Ordinal 0–3 relevance scale definition
    4. Strict JSON schema and output requirements

    No ground truth, test labels, or evaluation metrics are ever exposed.
    """

    def __init__(
        self,
        max_code_chars: int = B5_MAX_CODE_CHARS,
        version: str = B5_PROMPT_VERSION,
    ) -> None:
        """Initialize the fixed prompt builder.

        Args:
            max_code_chars: Maximum code characters retained per candidate before
                truncating with a safe budget marker.
            version: Prompt version identifier for experiment tracking.
        """
        self.max_code_chars = max_code_chars
        self.version = version

    def format_candidate_block(self, index: int, candidate: B5CandidateItem) -> str:
        """Format an individual candidate source-code snippet for the prompt."""
        code = candidate.code_text.strip()
        if len(code) > self.max_code_chars:
            code = (
                f"{code[: self.max_code_chars]}\n"
                "// [... remaining source code truncated for token budget ...]"
            )

        location = candidate.file_path or candidate.target_id
        return (
            f"Candidate [{index}]:\n"
            f"- target_id: {candidate.target_id}\n"
            f"- source_identifier: {location}\n"
            "```\n"
            f"{code}\n"
            "```"
        )

    def build_prompt(
        self,
        requirement_id: str,
        requirement_text: str,
        candidates: Sequence[B5CandidateItem],
    ) -> str:
        """Build the complete, fixed B5 prompt string for a single requirement query.

        Args:
            requirement_id: Unique identifier of the requirement.
            requirement_text: Natural language requirement description.
            candidates: Sequence of BM25-retrieved candidates to judge.

        Returns:
            The complete prompt text formatted for LLM consumption.
        """
        candidate_blocks = "\n\n".join(
            self.format_candidate_block(idx + 1, cand)
            for idx, cand in enumerate(candidates)
        )
        num_candidates = len(candidates)

        return (
            "You are an expert software traceability evaluator.\n"
            "Your task is to judge whether candidate source-code artifacts implement "
            "or support a given software requirement.\n\n"
            "### REQUIREMENT SPECIFICATION\n"
            f"Identifier: {requirement_id}\n"
            "Description:\n"
            f"{requirement_text.strip()}\n\n"
            f"### CANDIDATE SOURCE-CODE ARTIFACTS ({num_candidates} retrieved)\n"
            "Below are the retrieved source-code candidates. Evaluate each candidate "
            "strictly based on the supplied code and requirement description:\n\n"
            f"{candidate_blocks}\n\n"
            "### RELEVANCE SCORING SCALE (0–3)\n"
            "Assign exactly one integer score to each candidate using "
            "this ordinal scale:\n"
            "0 = unrelated: The code has no functional or semantic relation to "
            "the requirement.\n"
            "1 = weak/indirect relation: Mentions peripheral concepts, general "
            "utilities, or shared data types, but does not implement the requirement.\n"
            "2 = plausible/partial implementation: Implements a component, helper "
            "workflow, or partial sub-function of the requirement.\n"
            "3 = strong/direct implementation: Directly implements the core business "
            "logic, transaction, or feature specified in the requirement.\n\n"
            "### STRICT OUTPUT REQUIREMENTS\n"
            "1. Output valid JSON ONLY. Do not write any conversational text, "
            "explanations, or prose outside JSON.\n"
            f"2. You MUST include every candidate from the list above "
            f"({num_candidates} candidates total).\n"
            "3. Do NOT invent, hallucinate, or alter any target_id.\n"
            "4. Every candidate must be assigned exactly one integer score in "
            "{0, 1, 2, 3}.\n"
            "5. Conform strictly to the following JSON schema:\n"
            "{\n"
            '  "candidates": [\n'
            '    {"target_id": "<target_id>", "score": 0}\n'
            "  ]\n"
            "}\n"
        )


def _strip_markdown_code_fences(text: str) -> str:
    """Strip markdown code fence wrapper (```json ... ```) if present."""
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return cleaned


def parse_and_validate_b5_response(
    raw_response: str,
    expected_target_ids: Sequence[str],
) -> dict[str, int]:
    """Parse and validate LLM output against the strict B5 candidate schema.

    Validation rules:
    - Exactly one output entry per supplied candidate
    - No unknown target IDs
    - No duplicate target IDs
    - All expected target IDs present
    - Score must be integer strictly in {0, 1, 2, 3} (rejects floats, bools, strings)
    - Returns deterministic dict mapping target_id -> integer score

    Args:
        raw_response: Raw text returned by the LLM backend.
        expected_target_ids: Target IDs supplied in the query prompt.

    Returns:
        Mapping of target_id to validated integer score in {0, 1, 2, 3}.

    Raises:
        B5ValidationError: If JSON is malformed or violates any schema invariant.
    """
    cleaned = _strip_markdown_code_fences(raw_response)
    if not cleaned:
        raise B5ValidationError("LLM returned an empty response.")

    try:
        data = json.loads(cleaned)
    except Exception as exc:
        raise B5ValidationError(f"Malformed JSON in LLM response: {exc}") from exc

    if not isinstance(data, dict):
        raise B5ValidationError(
            f"Expected JSON object at top level, got {type(data).__name__}."
        )

    if "candidates" not in data:
        raise B5ValidationError(
            "Missing required top-level 'candidates' key in response."
        )

    candidate_list = data["candidates"]
    if not isinstance(candidate_list, list):
        raise B5ValidationError(
            f"Expected 'candidates' to be a list, got {type(candidate_list).__name__}."
        )

    expected_set = set(expected_target_ids)
    if len(candidate_list) != len(expected_target_ids):
        raise B5ValidationError(
            f"Expected {len(expected_target_ids)} candidates in response, "
            f"got {len(candidate_list)}."
        )

    scores: dict[str, int] = {}
    seen_ids: set[str] = set()

    for idx, item in enumerate(candidate_list):
        if not isinstance(item, dict):
            raise B5ValidationError(
                f"Candidate entry at index {idx} is not a JSON object: {item}."
            )

        if "target_id" not in item:
            raise B5ValidationError(
                f"Candidate entry at index {idx} missing 'target_id' field."
            )

        if "score" not in item:
            raise B5ValidationError(
                f"Candidate entry at index {idx} missing 'score' field."
            )

        target_id = item["target_id"]
        if not isinstance(target_id, str) or not target_id.strip():
            raise B5ValidationError(
                f"Candidate at index {idx} has invalid target_id: {target_id}."
            )
        target_id = target_id.strip()

        if target_id not in expected_set:
            raise B5ValidationError(
                f"Unknown target_id '{target_id}' found in model response."
            )

        if target_id in seen_ids:
            raise B5ValidationError(
                f"Duplicate target_id '{target_id}' in model response."
            )
        seen_ids.add(target_id)

        raw_score = item["score"]
        # In Python, bool is a subclass of int (isinstance(True, int) == True).
        # We must explicitly check type(raw_score) is int.
        if type(raw_score) is not int or raw_score not in (0, 1, 2, 3):
            raise B5ValidationError(
                f"Invalid score {raw_score!r} for candidate '{target_id}'. "
                "Score must be an integer in {0, 1, 2, 3}."
            )

        scores[target_id] = raw_score

    missing = expected_set - seen_ids
    if missing:
        raise B5ValidationError(
            f"Response is missing required candidate target IDs: {sorted(missing)}."
        )

    return scores


__all__ = [
    "B5_MAX_CODE_CHARS",
    "B5_PROMPT_VERSION",
    "B5CandidateItem",
    "B5PromptBuilder",
    "B5ValidationError",
    "parse_and_validate_b5_response",
]
