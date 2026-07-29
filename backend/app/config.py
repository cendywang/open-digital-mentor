"""Configuration, loaded from the single repo-root `.env`.

Security-sensitive defaults are enforced here: mock mode needs no credentials
or network access, the server binds to loopback, and browser origins use an
explicit allowlist.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> <repo root>
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"


class Mode(StrEnum):
    MOCK = "mock"
    LIVE = "live"


class LLMProviderName(StrEnum):
    MOCK = "mock"
    OPENAI_COMPATIBLE = "openai_compatible"


class TTSProviderName(StrEnum):
    MOCK = "mock"
    MINIMAX = "minimax"
    AZURE = "azure"


class RetrieverName(StrEnum):
    MOCK = "mock"
    LOCAL = "local"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
    )

    # -- mode ---------------------------------------------------------------
    mode: Mode = Field(default=Mode.MOCK, alias="ODM_MODE")

    # -- server -------------------------------------------------------------
    host: str = Field(default="127.0.0.1", alias="ODM_HOST")
    port: int = Field(default=8000, alias="ODM_PORT")
    allowed_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        alias="ODM_ALLOWED_ORIGINS",
    )

    # -- llm ----------------------------------------------------------------
    llm_provider: LLMProviderName = Field(default=LLMProviderName.MOCK, alias="ODM_LLM_PROVIDER")
    llm_base_url: str = Field(default="", alias="ODM_LLM_BASE_URL")
    llm_api_key: str = Field(default="", alias="ODM_LLM_API_KEY")
    llm_model: str = Field(default="", alias="ODM_LLM_MODEL")
    llm_temperature: float = Field(default=0.2, alias="ODM_LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=2048, alias="ODM_LLM_MAX_TOKENS")

    # -- tts ----------------------------------------------------------------
    tts_provider: TTSProviderName = Field(default=TTSProviderName.MOCK, alias="ODM_TTS_PROVIDER")
    tts_endpoint: str = Field(default="", alias="ODM_TTS_ENDPOINT")
    tts_api_key: str = Field(default="", alias="ODM_TTS_API_KEY")
    tts_region: str = Field(default="", alias="ODM_TTS_REGION")
    tts_voice: str = Field(default="", alias="ODM_TTS_VOICE")
    tts_model: str = Field(default="speech-2.8-turbo", alias="ODM_TTS_MODEL")

    # -- retriever ----------------------------------------------------------
    # The bundled YAML corpus is offline too, and becomes the useful default
    # once M0.2 turns the renderer demo into a knowledge mentor.
    retriever: RetrieverName = Field(default=RetrieverName.LOCAL, alias="ODM_RETRIEVER")
    knowledge_dir: str = Field(default="knowledge", alias="ODM_KNOWLEDGE_DIR")
    retriever_top_k: int = Field(default=4, alias="ODM_RETRIEVER_TOP_K")
    retriever_min_score: float = Field(default=0.15, alias="ODM_RETRIEVER_MIN_SCORE")

    # -- limits -------------------------------------------------------------
    max_message_chars: int = Field(default=2000, alias="ODM_MAX_MESSAGE_CHARS")
    max_connections_per_ip: int = Field(default=5, alias="ODM_MAX_CONNECTIONS_PER_IP")
    max_concurrent_tts_per_session: int = Field(
        default=3, alias="ODM_MAX_CONCURRENT_TTS_PER_SESSION"
    )

    # -- logging ------------------------------------------------------------
    log_message_body: bool = Field(default=False, alias="ODM_LOG_MESSAGE_BODY")
    log_level: str = Field(default="INFO", alias="ODM_LOG_LEVEL")

    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    # -- derived ------------------------------------------------------------
    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def knowledge_path(self) -> Path:
        p = Path(self.knowledge_dir)
        return p if p.is_absolute() else REPO_ROOT / p

    @property
    def is_mock(self) -> bool:
        """True only when *nothing* will reach the network.

        `ODM_MODE=mock` forces every provider to mock regardless of the
        individual provider settings, so a half-configured `.env` can never
        silently start spending money.
        """
        return self.mode is Mode.MOCK

    def effective_llm_provider(self) -> LLMProviderName:
        return LLMProviderName.MOCK if self.is_mock else self.llm_provider

    def effective_tts_provider(self) -> TTSProviderName:
        return TTSProviderName.MOCK if self.is_mock else self.tts_provider

    def effective_retriever(self) -> RetrieverName:
        # The local retriever reads files off disk — no network — so it is
        # allowed in mock mode if the user explicitly asked for it.
        return self.retriever

    def binds_publicly(self) -> bool:
        return self.host not in ("127.0.0.1", "localhost", "::1")

    def validation_errors(self) -> list[str]:
        """Config problems worth refusing to start over. Empty in mock mode."""
        errs: list[str] = []
        if self.is_mock:
            return errs
        if self.effective_llm_provider() is LLMProviderName.OPENAI_COMPATIBLE:
            if not self.llm_base_url:
                errs.append("ODM_LLM_BASE_URL is required when ODM_LLM_PROVIDER=openai_compatible")
            if not self.llm_model:
                errs.append("ODM_LLM_MODEL is required when ODM_LLM_PROVIDER=openai_compatible")
        tts_provider = self.effective_tts_provider()
        if tts_provider in (TTSProviderName.MINIMAX, TTSProviderName.AZURE):
            if not self.tts_api_key:
                errs.append(f"ODM_TTS_API_KEY is required when ODM_TTS_PROVIDER={tts_provider}")
            if not self.tts_voice:
                errs.append(f"ODM_TTS_VOICE is required when ODM_TTS_PROVIDER={tts_provider}")
        if tts_provider is TTSProviderName.MINIMAX and not self.tts_model:
            errs.append("ODM_TTS_MODEL is required when ODM_TTS_PROVIDER=minimax")
        if (
            tts_provider is TTSProviderName.AZURE
            and not self.tts_endpoint
            and not self.tts_region
        ):
            errs.append(
                "ODM_TTS_REGION is required when ODM_TTS_PROVIDER=azure "
                "and ODM_TTS_ENDPOINT is empty"
            )
        return errs


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
