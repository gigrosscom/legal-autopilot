from .base import Attachment, LLMError, LLMProvider
from .redacting import RedactingLLM

__all__ = ["Attachment", "LLMError", "LLMProvider", "RedactingLLM", "build_provider"]


def build_provider(settings) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            model=settings.llm_model,
            api_key=settings.anthropic_api_key,
            refusal_fallback=settings.llm_refusal_fallback or None,
        )
    if settings.llm_provider == "mock":
        from .mock import HeuristicMockProvider

        return HeuristicMockProvider()
    raise ValueError(f"unknown LLM_PROVIDER {settings.llm_provider!r}")
