"""Provider construction. The only place that maps config -> implementation.

To add your own: implement the Protocol in `base.py`, add a branch here, add
the enum value in `config.py`. Nothing else in the codebase needs to know.
"""

from __future__ import annotations

import logging

from app.config import LLMProviderName, RetrieverName, Settings, TTSProviderName
from app.providers.base import LLMProvider, Retriever, TTSProvider
from app.providers.mock import MockLLM, MockRetriever, MockTTS

log = logging.getLogger(__name__)

__all__ = [
    "LLMProvider",
    "Retriever",
    "TTSProvider",
    "build_llm",
    "build_retriever",
    "build_tts",
]


def build_llm(settings: Settings) -> LLMProvider:
    provider = settings.effective_llm_provider()
    if provider is LLMProviderName.MOCK:
        return MockLLM()

    # Imported lazily so mock mode never even loads the networking adapter.
    from app.providers.llm_openai import OpenAICompatibleLLM

    return OpenAICompatibleLLM(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )


def build_tts(settings: Settings) -> TTSProvider:
    provider = settings.effective_tts_provider()
    if provider is TTSProviderName.MOCK:
        return MockTTS()

    if provider is TTSProviderName.MINIMAX:
        from app.providers.tts_minimax import MiniMaxTTS

        return MiniMaxTTS(
            api_key=settings.tts_api_key,
            model=settings.tts_model,
            endpoint=settings.tts_endpoint,
        )

    from app.providers.tts_azure import AzureTTS

    return AzureTTS(
        api_key=settings.tts_api_key,
        region=settings.tts_region,
        endpoint=settings.tts_endpoint,
    )


def build_retriever(settings: Settings) -> Retriever:
    if settings.effective_retriever() is RetrieverName.MOCK:
        return MockRetriever()

    from app.knowledge import KnowledgeError
    from app.providers.retriever_local import LocalRetriever

    try:
        return LocalRetriever(settings.knowledge_path)
    except KnowledgeError as exc:
        # A broken corpus should not take the whole service down — the avatar
        # and the refusal path still work. Say so loudly instead.
        log.error(
            "failed to load knowledge from %s (%s); falling back to MockRetriever",
            settings.knowledge_path,
            exc,
        )
        return MockRetriever()
