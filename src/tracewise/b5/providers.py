"""LLM provider interfaces and implementations for TraceWise B5."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LLMResponse(BaseModel):
    """Encapsulates raw text and runtime telemetry returned by an LLM provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str
    prompt_eval_duration_sec: float = 0.0
    eval_duration_sec: float = 0.0
    total_duration_sec: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMProviderError(Exception):
    """Raised when an LLM provider fails to generate a response."""


class LLMProvider(ABC):
    """Abstract interface defining the contract for B5 LLM generation."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the model powering this provider."""
        ...

    @abstractmethod
    def generate(self, prompt: str) -> LLMResponse:
        """Send a prompt to the model and return the resulting text response.

        Args:
            prompt: Formatted prompt text to evaluate.

        Returns:
            LLMResponse containing generation content and performance telemetry.

        Raises:
            LLMProviderError: If the backend fails or times out.
        """
        ...


class OllamaProvider(LLMProvider):
    """Ollama local inference backend provider for B5 reranking.

    Connects to the local Ollama REST API endpoint (default: http://localhost:11434).
    Uses strict deterministic generation options (temperature=0.0, think=False).
    """

    def __init__(
        self,
        model: str = "qwen3.5:9b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.0,
        think: bool = False,
        timeout: float = 180.0,
        options: dict[str, Any] | None = None,
    ) -> None:
        """Initialize Ollama provider with configurable parameters.

        Args:
            model: Ollama model tag. Default: 'qwen3.5:9b'.
            base_url: Base HTTP URL for the Ollama API.
            temperature: Sampling temperature. Frozen to 0.0 for deterministic
                evaluation.
            think: Thinking mode flag. Disabled (False) for direct structured JSON.
            timeout: Maximum HTTP socket timeout in seconds.
            options: Additional low-level generation options passed to Ollama.
        """
        self._model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = float(temperature)
        self.think = think
        self.timeout = float(timeout)
        default_options: dict[str, Any] = {"num_ctx": 8192}
        self.extra_options = {**default_options, **(options or {})}

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, prompt: str) -> LLMResponse:
        """Invoke Ollama's /api/generate endpoint with structured JSON mode."""
        url = f"{self.base_url}/api/generate"
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "think": self.think,
            "options": {
                "temperature": self.temperature,
                "think": self.think,
                **self.extra_options,
            },
        }

        req_body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            data=req_body,
            headers={"Content-Type": "application/json"},
        )

        t_start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                resp_bytes = resp.read()
                raw_json = json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise LLMProviderError(
                f"Ollama HTTP error {exc.code} for model '{self._model}': {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise LLMProviderError(
                f"Failed to connect to Ollama at {url}: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise LLMProviderError(
                f"Ollama request timed out after {self.timeout}s for "
                f"model '{self._model}'"
            ) from exc
        except json.JSONDecodeError as exc:
            raise LLMProviderError(
                f"Malformed JSON returned by Ollama server: {exc}"
            ) from exc
        except Exception as exc:
            raise LLMProviderError(
                f"Unexpected Ollama communication error: {exc}"
            ) from exc

        t_end = time.perf_counter()
        measured_duration = t_end - t_start

        content = raw_json.get("response", "")
        # Ollama returns timing metrics in nanoseconds
        prompt_eval_ns = raw_json.get("prompt_eval_duration", 0)
        eval_ns = raw_json.get("eval_duration", 0)
        total_ns = raw_json.get("total_duration", 0)

        prompt_eval_sec = prompt_eval_ns / 1e9 if prompt_eval_ns else 0.0
        eval_sec = eval_ns / 1e9 if eval_ns else 0.0
        total_sec = total_ns / 1e9 if total_ns else measured_duration

        return LLMResponse(
            content=content,
            prompt_eval_duration_sec=prompt_eval_sec,
            eval_duration_sec=eval_sec,
            total_duration_sec=total_sec,
            metadata={
                "model": raw_json.get("model", self._model),
                "prompt_eval_count": raw_json.get("prompt_eval_count", 0),
                "eval_count": raw_json.get("eval_count", 0),
                "done": raw_json.get("done", True),
            },
        )


class MockLLMProvider(LLMProvider):
    """Deterministic mock provider for unit tests without a running Ollama server."""

    def __init__(
        self,
        default_response: str | None = None,
        responses: list[str | Exception] | None = None,
        model: str = "mock-qwen3.5:9b",
    ) -> None:
        """Initialize mock provider.

        Args:
            default_response: Static response to return when response queue is empty.
            responses: Sequence of response strings or Exception instances to raise.
            model: Nominal model name.
        """
        self._model = model
        self.default_response = default_response
        self._responses: list[str | Exception] = list(responses or [])
        self.calls: list[str] = []

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def queue_response(self, response: str | Exception) -> None:
        """Append a canned response or exception to the queue."""
        self._responses.append(response)

    def generate(self, prompt: str) -> LLMResponse:
        self.calls.append(prompt)
        if self._responses:
            next_item = self._responses.pop(0)
            if isinstance(next_item, Exception):
                raise next_item
            return LLMResponse(
                content=next_item,
                prompt_eval_duration_sec=0.01,
                eval_duration_sec=0.01,
                total_duration_sec=0.02,
                metadata={"mock": True},
            )

        if self.default_response is not None:
            return LLMResponse(
                content=self.default_response,
                prompt_eval_duration_sec=0.01,
                eval_duration_sec=0.01,
                total_duration_sec=0.02,
                metadata={"mock": True},
            )

        raise LLMProviderError("MockLLMProvider has no responses queued.")


__all__ = [
    "LLMProvider",
    "LLMProviderError",
    "LLMResponse",
    "MockLLMProvider",
    "OllamaProvider",
]
