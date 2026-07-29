"""Mock mode must remain fully offline.

Any attempt to create a socket during a full mock pipeline run fails the suite.
"""

import socket

import pytest
from fastapi.testclient import TestClient

from app.config import Mode, Settings, get_settings
from app.main import create_app
from app.pipeline import MentorPipeline
from app.providers import build_llm, build_retriever, build_tts


class NetworkAccessDenied(AssertionError):
    pass


@pytest.fixture
def no_network(monkeypatch):
    """Ban outbound traffic, not sockets outright.

    asyncio's own event loop builds a self-pipe with `socket.socketpair()`,
    so banning socket construction would fail on the runtime rather than on
    the code under test. Connecting and name resolution are what actually
    reach the outside world.
    """

    def deny(*args, **kwargs):
        raise NetworkAccessDenied("mock mode attempted to reach the network")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    yield


def mock_settings() -> Settings:
    return Settings(_env_file=None, ODM_MODE="mock")  # type: ignore[arg-type]


async def test_full_turn_runs_without_network(no_network):
    settings = mock_settings()
    assert settings.is_mock

    pipeline = MentorPipeline(
        retriever=build_retriever(settings),
        llm=build_llm(settings),
        tts=build_tts(settings),
        settings=settings,
    )

    events = [e async for e in pipeline.run("t1", "自贸区和内地主体怎么选")]
    assert any(e.type == "audio" and e.audio for e in events)
    assert any(e.type == "turn.end" for e in events)


async def test_refusal_path_runs_without_network(no_network):
    settings = mock_settings()
    pipeline = MentorPipeline(
        retriever=build_retriever(settings),
        llm=build_llm(settings),
        tts=build_tts(settings),
        settings=settings,
    )
    events = [e async for e in pipeline.run("t1", "写一个快速排序")]
    assert next(e for e in events if e.type == "retrieval").refused


def test_websocket_app_runs_full_mock_turn_without_network(no_network, monkeypatch):
    """Exercise lifespan, provider wiring, protocol parsing and serialization together."""
    monkeypatch.setenv("ODM_MODE", "mock")
    monkeypatch.setenv("ODM_LLM_PROVIDER", "mock")
    monkeypatch.setenv("ODM_TTS_PROVIDER", "mock")
    monkeypatch.setenv("ODM_RETRIEVER", "mock")
    get_settings.cache_clear()

    try:
        app = create_app()
        with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
            hello = websocket.receive_json()
            assert hello["type"] == "hello"
            assert hello["mode"] == "mock"
            assert hello["providers"] == {
                "llm": "mock",
                "tts": "mock",
                "retriever": "mock",
            }

            websocket.send_json(
                {
                    "type": "ask",
                    "turn_id": "m01-integration",
                    "question": "自贸区和内地主体怎么选？",
                }
            )

            events = []
            for _ in range(200):
                event = websocket.receive_json()
                events.append(event)
                if event["type"] == "turn.end":
                    break

        kinds = [event["type"] for event in events]
        retrieval = next(event for event in events if event["type"] == "retrieval")
        audio = [event for event in events if event["type"] == "audio"]

        assert kinds[0] == "turn.start"
        assert kinds[-1] == "turn.end"
        assert retrieval["refused"] is False
        assert retrieval["citations"]
        assert audio and all(event["audio"] for event in audio)
    finally:
        get_settings.cache_clear()


def test_mode_mock_overrides_misconfigured_live_providers():
    """A half-edited .env must never silently start spending money."""
    settings = Settings(  # type: ignore[arg-type]
        _env_file=None,
        ODM_MODE="mock",
        ODM_LLM_PROVIDER="openai_compatible",
        ODM_LLM_BASE_URL="https://api.example.com/v1",
        ODM_LLM_API_KEY="not-a-real-key",
        ODM_LLM_MODEL="gpt-whatever",
        ODM_TTS_PROVIDER="azure",
    )
    assert settings.mode is Mode.MOCK
    assert build_llm(settings).name == "mock"
    assert build_tts(settings).name == "mock"


def test_default_offline_mode_uses_the_replaceable_local_corpus():
    settings = mock_settings()
    retriever = build_retriever(settings)
    assert retriever.name == "local"
    assert retriever.size >= 20


def test_live_mode_reports_missing_credentials():
    settings = Settings(  # type: ignore[arg-type]
        _env_file=None,
        ODM_MODE="live",
        ODM_LLM_PROVIDER="openai_compatible",
    )
    errors = settings.validation_errors()
    assert any("ODM_LLM_BASE_URL" in e for e in errors)
    assert any("ODM_LLM_MODEL" in e for e in errors)


def test_live_minimax_reports_missing_key_and_voice():
    settings = Settings(  # type: ignore[arg-type]
        _env_file=None,
        ODM_MODE="live",
        ODM_TTS_PROVIDER="minimax",
    )
    errors = settings.validation_errors()
    assert any("ODM_TTS_API_KEY" in e for e in errors)
    assert any("ODM_TTS_VOICE" in e for e in errors)


def test_live_azure_custom_endpoint_does_not_require_region():
    settings = Settings(  # type: ignore[arg-type]
        _env_file=None,
        ODM_MODE="live",
        ODM_TTS_PROVIDER="azure",
        ODM_TTS_API_KEY="not-a-real-key",
        ODM_TTS_VOICE="zh-CN-XiaoxiaoNeural",
        ODM_TTS_ENDPOINT="https://tts.example.test/custom/speech",
    )
    assert not any("ODM_TTS_REGION" in error for error in settings.validation_errors())


def test_live_azure_official_endpoint_requires_region():
    settings = Settings(  # type: ignore[arg-type]
        _env_file=None,
        ODM_MODE="live",
        ODM_TTS_PROVIDER="azure",
        ODM_TTS_API_KEY="not-a-real-key",
        ODM_TTS_VOICE="zh-CN-XiaoxiaoNeural",
    )
    assert any("ODM_TTS_REGION" in error for error in settings.validation_errors())


def test_default_bind_is_loopback():
    assert not mock_settings().binds_publicly()
    public = Settings(_env_file=None, ODM_HOST="0.0.0.0")  # type: ignore[arg-type] # noqa: S104
    assert public.binds_publicly()


def test_cors_is_never_wildcard():
    assert "*" not in mock_settings().origins
