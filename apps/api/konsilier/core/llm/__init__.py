from .base import Attachment, LLMError, LLMProvider
from .redacting import RedactingLLM

__all__ = ["Attachment", "LLMError", "LLMProvider", "RedactingLLM", "build_provider"]


def build_provider(settings) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            model=settings.llm_model,
            fast_model=settings.llm_fast_model or None,
            api_key=settings.anthropic_api_key,
            refusal_fallback=settings.llm_refusal_fallback or None,
        )
    if settings.llm_provider == "gemini":
        from .gemini_provider import GeminiProvider

        if not settings.gemini_api_key:  # keep the site up: rule-based answers until the key is set
            import logging

            from .mock import HeuristicMockProvider

            logging.getLogger(__name__).error("LLM_PROVIDER=gemini but GEMINI_API_KEY is empty: using the rule-based mock")
            return HeuristicMockProvider()
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    if settings.llm_provider == "mock":
        from .mock import HeuristicMockProvider

        return HeuristicMockProvider()
    raise ValueError(f"unknown LLM_PROVIDER {settings.llm_provider!r}")
