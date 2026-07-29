import asyncio
import json
from collections.abc import Sequence

import pytest

from app.providers.tts_minimax import MiniMaxTTS


class FakeWebSocket:
    def __init__(self, responses: Sequence[dict]) -> None:
        self.responses = iter(responses)
        self.sent: list[dict] = []
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    async def recv(self) -> str:
        return json.dumps(next(self.responses))


class FakeConnection:
    def __init__(self, websocket: FakeWebSocket) -> None:
        self.websocket = websocket

    async def __aenter__(self) -> FakeWebSocket:
        return self.websocket

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self.websocket.closed = True


class FakeConnector:
    def __init__(self, responses: Sequence[dict]) -> None:
        self.websocket = FakeWebSocket(responses)
        self.url = ""
        self.kwargs: dict = {}
        self.calls = 0

    def __call__(self, url: str, **kwargs) -> FakeConnection:
        self.calls += 1
        self.url = url
        self.kwargs = kwargs
        return FakeConnection(self.websocket)


def successful_responses() -> list[dict]:
    return [
        {"event": "connected_success"},
        {"event": "task_started", "base_resp": {"status_code": 0}},
        {
            "event": "task_continued",
            "data": {"audio": b"first-".hex()},
            "is_final": False,
            "base_resp": {"status_code": 0},
        },
        {
            "event": "task_continued",
            "data": {"audio": b"second".hex()},
            "is_final": True,
            "base_resp": {"status_code": 0},
        },
    ]


async def test_minimax_adapter_sends_contract_and_collects_mp3_chunks():
    connector = FakeConnector(successful_responses())
    tts = MiniMaxTTS(
        api_key="test-key",
        model="speech-2.8-turbo",
        endpoint="wss://tts.example.test/custom/ws",
        connector=connector,
    )

    segment = await tts.synthesize("**你好** [1]", "cloned-voice-id")

    assert segment.ok
    assert segment.audio == b"first-second"
    assert segment.mime_type == "audio/mpeg"
    assert segment.visemes[0].text == "你好"
    assert connector.url == "wss://tts.example.test/custom/ws"
    assert connector.kwargs["additional_headers"] == {"Authorization": "Bearer test-key"}
    assert connector.kwargs["proxy"] is None
    assert connector.websocket.closed

    start, continued, finish = connector.websocket.sent
    assert start["event"] == "task_start"
    assert start["model"] == "speech-2.8-turbo"
    assert start["voice_setting"]["voice_id"] == "cloned-voice-id"
    assert start["audio_setting"] == {
        "sample_rate": 32000,
        "bitrate": 128000,
        "format": "mp3",
        "channel": 1,
    }
    assert continued == {"event": "task_continue", "text": "你好"}
    assert finish == {"event": "task_finish"}


async def test_minimax_official_endpoint_is_used_when_endpoint_is_empty():
    connector = FakeConnector(successful_responses())
    tts = MiniMaxTTS(api_key="test-key", connector=connector)

    segment = await tts.synthesize("测试。", "voice-id")

    assert segment.ok
    assert connector.url == "wss://api.minimaxi.com/ws/v1/t2a_v2"


@pytest.mark.parametrize(
    "response",
    [
        {"event": "task_failed", "base_resp": {"status_code": 1004}},
        {
            "event": "task_continued",
            "data": {"audio": "not-hex"},
            "is_final": True,
            "base_resp": {"status_code": 0},
        },
    ],
)
async def test_minimax_failure_degrades_without_raising(response):
    connector = FakeConnector(
        [
            {"event": "connected_success"},
            {"event": "task_started", "base_resp": {"status_code": 0}},
            response,
        ]
    )
    tts = MiniMaxTTS(api_key="test-key", connector=connector)

    segment = await tts.synthesize("仍然显示字幕。", "voice-id")

    assert not segment.ok
    assert segment.audio == b""
    assert connector.websocket.closed


async def test_empty_spoken_text_skips_minimax_connection():
    connector = FakeConnector(successful_responses())
    tts = MiniMaxTTS(api_key="test-key", connector=connector)

    segment = await tts.synthesize("[1] ***", "voice-id")

    assert segment.ok
    assert segment.audio == b""
    assert connector.calls == 0


async def test_cancellation_propagates_and_closes_upstream_connection():
    entered = asyncio.Event()

    class BlockingWebSocket(FakeWebSocket):
        async def recv(self) -> str:
            if not entered.is_set():
                entered.set()
                return json.dumps({"event": "connected_success"})
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    websocket = BlockingWebSocket([])

    def connector(url: str, **kwargs) -> FakeConnection:
        return FakeConnection(websocket)

    tts = MiniMaxTTS(api_key="test-key", connector=connector)
    task = asyncio.create_task(tts.synthesize("这次会被停止。", "voice-id"))
    await entered.wait()
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert websocket.closed
