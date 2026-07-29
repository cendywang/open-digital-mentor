"""MiniMax streaming WebSocket TTS adapter.

The application protocol delivers one complete sentence-sized audio segment,
so this adapter collects MiniMax's MP3 frames before returning. The upstream
connection is still cancellable: cancelling ``synthesize`` closes its WebSocket
immediately and prevents further billable work.

Provider failures never take down the text answer. They return ``ok=False`` so
the existing subtitle-only degradation path remains available.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from websockets.asyncio.client import connect

from app.models import AudioSegment, Viseme
from app.text import to_speech_text

log = logging.getLogger(__name__)

_DEFAULT_URL = "wss://api.minimaxi.com/ws/v1/t2a_v2"


class _WebSocket(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...


class MiniMaxProtocolError(RuntimeError):
    """The upstream connection succeeded but returned an invalid task event."""


class MiniMaxTTS:
    name = "minimax"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "speech-2.8-turbo",
        endpoint: str = "",
        timeout_s: float = 30.0,
        connector: Callable[..., AbstractAsyncContextManager[_WebSocket]] | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._url = endpoint or _DEFAULT_URL
        self._timeout_s = timeout_s
        self._connect = connector or connect

    async def synthesize(self, text: str, voice: str) -> AudioSegment:
        spoken = to_speech_text(text)
        if not spoken:
            return AudioSegment(audio=b"", mime_type="audio/mpeg", ok=True)

        try:
            async with asyncio.timeout(self._timeout_s):
                audio = await self._synthesize(spoken, voice)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning(
                "MiniMax TTS failed (%s); degrading to text-only",
                type(exc).__name__,
            )
            return AudioSegment(audio=b"", mime_type="audio/mpeg", ok=False)

        if not audio:
            log.warning("MiniMax TTS returned no audio; degrading to text-only")
            return AudioSegment(audio=b"", mime_type="audio/mpeg", ok=False)

        return AudioSegment(
            audio=audio,
            mime_type="audio/mpeg",
            visemes=[Viseme(offset_s=0.0, duration_s=0.0, text=spoken)],
            ok=True,
        )

    async def _synthesize(self, spoken: str, voice: str) -> bytes:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with self._connect(
            self._url,
            additional_headers=headers,
            open_timeout=min(self._timeout_s, 8.0),
            close_timeout=2.0,
            max_size=8 * 1024 * 1024,
            proxy=None,
        ) as websocket:
            await _expect_event(websocket, "connected_success")
            await websocket.send(
                json.dumps(
                    {
                        "event": "task_start",
                        "model": self._model,
                        "voice_setting": {
                            "voice_id": voice,
                            "speed": 1,
                            "vol": 1,
                            "pitch": 0,
                            "english_normalization": False,
                        },
                        "audio_setting": {
                            "sample_rate": 32000,
                            "bitrate": 128000,
                            "format": "mp3",
                            "channel": 1,
                        },
                    },
                    ensure_ascii=False,
                )
            )
            await _expect_event(websocket, "task_started")
            await websocket.send(
                json.dumps(
                    {"event": "task_continue", "text": spoken},
                    ensure_ascii=False,
                )
            )

            audio = bytearray()
            while True:
                message = await _receive_event(websocket)
                data = message.get("data")
                encoded = data.get("audio") if isinstance(data, dict) else None
                if encoded:
                    if not isinstance(encoded, str):
                        raise MiniMaxProtocolError("audio payload is not a hex string")
                    try:
                        audio.extend(bytes.fromhex(encoded))
                    except ValueError as exc:
                        raise MiniMaxProtocolError("audio payload is not valid hex") from exc

                if message.get("is_final") is True:
                    break

            try:
                await websocket.send(json.dumps({"event": "task_finish"}))
            except Exception as exc:
                # Audio is already complete. A close-race must not discard it.
                log.debug("MiniMax task_finish raced connection close (%s)", type(exc).__name__)
            return bytes(audio)

    async def aclose(self) -> None:
        # Connections are scoped to synthesize() so cancellation can close the
        # exact billable task without affecting other concurrent sentences.
        return None


async def _expect_event(websocket: _WebSocket, expected: str) -> dict[str, Any]:
    message = await _receive_event(websocket)
    actual = message.get("event")
    if actual != expected:
        raise MiniMaxProtocolError(f"expected {expected}, received {actual!r}")
    return message


async def _receive_event(websocket: _WebSocket) -> dict[str, Any]:
    raw = await websocket.recv()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise MiniMaxProtocolError("event is not a JSON object")

    base_response = parsed.get("base_resp")
    status = base_response.get("status_code") if isinstance(base_response, dict) else None
    if status not in (None, 0):
        raise MiniMaxProtocolError(f"upstream status {status}")
    if parsed.get("event") == "task_failed":
        raise MiniMaxProtocolError("upstream task failed")
    return parsed
