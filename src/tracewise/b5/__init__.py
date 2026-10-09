"""TraceWise Milestone B5: Controlled LLM-assisted RAG reranking baseline.

B5 implements a controlled retrieve-then-rerank pipeline:
Requirement -> frozen B1 BM25 -> top-20 source-code candidates -> local LLM
relevance assessment -> candidate reranking -> evaluation.
"""

from tracewise.b5.benchmark import (
    B5BenchmarkResult,
    format_b5_comparison_table,
    run_b5_evaluation,
)
from tracewise.b5.prompt import (
    B5_MAX_CODE_CHARS,
    B5_PROMPT_VERSION,
    B5CandidateItem,
    B5PromptBuilder,
    B5ValidationError,
    parse_and_validate_b5_response,
)
from tracewise.b5.providers import (
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    MockLLMProvider,
    OllamaProvider,
)
from tracewise.b5.reranker import B5RerankRetriever

__all__ = [
    "B5BenchmarkResult",
    "B5CandidateItem",
    "B5PromptBuilder",
    "B5RerankRetriever",
    "B5ValidationError",
    "B5_MAX_CODE_CHARS",
    "B5_PROMPT_VERSION",
    "LLMProvider",
    "LLMProviderError",
    "LLMResponse",
    "MockLLMProvider",
    "OllamaProvider",
    "format_b5_comparison_table",
    "parse_and_validate_b5_response",
    "run_b5_evaluation",
]
