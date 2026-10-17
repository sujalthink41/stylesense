"""Groq: OpenAI-compatible API on fast, cheap open models. Same adapter, different endpoint.

Reasoning models (gpt-oss, qwen3) think before answering and those tokens are billed and count
toward max_completion_tokens; extraction tasks don't need it, so effort is kept low.
"""

from typing import Any

from stylesense.integrations.llm.openai_provider import OpenAIProvider

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_REASONING_PREFIXES = ("openai/gpt-oss", "qwen/")


class GroqProvider(OpenAIProvider):
    name = "groq"
    supports_prompt_cache_key = False  # Groq answers 400 to it

    def __init__(self, api_key: str, *, base_url: str = GROQ_BASE_URL) -> None:
        super().__init__(api_key, base_url=base_url)

    def _extra_options(self, model: str) -> dict[str, Any]:
        if model.startswith(_REASONING_PREFIXES):
            return {"reasoning_effort": "low"}
        return {}
