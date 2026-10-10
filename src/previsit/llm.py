"""The only gateway to the language model.

Inputs are transcripts, sheets and module content. Lab results are never passed here
(hard rule; previsit.results does not import this module).
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from previsit.config import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Message = dict[str, str]

SAFETY_TASKS = frozenset({"safety", "scope_guard", "identity", "consent", "symptom_note"})
EXTRACTION_TASKS = frozenset({"sheet"})


class LLMError(RuntimeError):
    """The model could not produce a valid response."""


class LLMClient(Protocol):
    def complete_json(self, task: str, system: str, messages: list[Message], schema: type[T]) -> T: ...


class OpenAILLM:
    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI

        key = settings.openai_api_key.get_secret_value()
        if not key:
            raise LLMError("OPENAI_API_KEY is not set")
        self._client = OpenAI(api_key=key, timeout=45.0, max_retries=2)
        self._settings = settings

    def _model_for(self, task: str) -> str:
        if task in SAFETY_TASKS:
            return self._settings.safety_model
        if task in EXTRACTION_TASKS:
            return self._settings.extraction_model
        return self._settings.interview_model

    def _effort_for(self, task: str) -> str:
        if task in SAFETY_TASKS:
            return self._settings.safety_reasoning
        if task in EXTRACTION_TASKS:
            return self._settings.extraction_reasoning
        return self._settings.interview_reasoning

    def complete_json(self, task: str, system: str, messages: list[Message], schema: type[T]) -> T:
        model = self._model_for(task)
        started = time.monotonic()
        try:
            response = self._client.responses.parse(
                model=model,
                instructions=system,
                input=messages,
                text_format=schema,
                reasoning={"effort": self._effort_for(task)},
                store=False,
            )
        except Exception as exc:  # network, auth, rate limit, schema rejection
            logger.exception("LLM call failed: task=%s model=%s", task, model)
            raise LLMError(f"{task} call failed: {exc.__class__.__name__}") from exc
        logger.info("LLM %s (%s) took %.2fs", task, model, time.monotonic() - started)
        parsed = response.output_parsed
        if parsed is None:
            raise LLMError(f"{task} returned no parseable output")
        return parsed


Handler = Callable[[str, list[Message]], Any]


@dataclass
class FakeLLM:
    """Deterministic stand-in for tests. Each handler returns a schema instance or a dict for it."""

    handlers: dict[str, Handler]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete_json(self, task: str, system: str, messages: list[Message], schema: type[T]) -> T:
        self.calls.append({"task": task, "system": system, "messages": [dict(m) for m in messages]})
        if task not in self.handlers:
            raise LLMError(f"FakeLLM has no handler for task {task!r}")
        result = self.handlers[task](system, messages)
        return result if isinstance(result, schema) else schema.model_validate(result)
