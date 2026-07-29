"""Azure Speech TTS adapter.

The REST endpoint returns sentence audio without a phoneme-boundary stream, so
the adapter reports sentence-level timing rather than claiming precise visemes.
`synthesize()` degrades provider failures to text and subtitles.
"""

from __future__ import annotations

import logging
import xml.sax.saxutils as saxutils

import httpx

from app.models import AudioSegment, Viseme
from app.text import to_speech_text

log = logging.getLogger(__name__)

_OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"


class AzureTTS:
    name = "azure"

    def __init__(
        self,
        *,
        api_key: str,
        region: str,
        endpoint: str = "",
        timeout_s: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = endpoint or (
            f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        )
        self._client = httpx.AsyncClient(
            headers={
                "Ocp-Apim-Subscription-Key": api_key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": _OUTPUT_FORMAT,
                "User-Agent": "open-digital-mentor",
            },
            timeout=httpx.Timeout(timeout_s, connect=8.0),
            transport=transport,
        )

    async def synthesize(self, text: str, voice: str) -> AudioSegment:
        spoken = to_speech_text(text)
        if not spoken:
            return AudioSegment(audio=b"", mime_type="audio/mpeg", ok=True)

        ssml = _build_ssml(spoken, voice)
        try:
            response = await self._client.post(self._url, content=ssml.encode("utf-8"))
            if response.status_code >= 400:
                log.warning(
                    "TTS failed with %s; degrading to text-only for this segment",
                    response.status_code,
                )
                return AudioSegment(audio=b"", mime_type="audio/mpeg", ok=False)

            # The REST endpoint returns audio only. Without a boundary stream
            # we emit a single sentence-level viseme window and let the
            # frontend fall back to amplitude-driven mouth movement inside it.
            # This is the declared degradation, not "precise sync".
            return AudioSegment(
                audio=response.content,
                mime_type="audio/mpeg",
                visemes=[Viseme(offset_s=0.0, duration_s=0.0, text=spoken)],
                ok=True,
            )
        except httpx.HTTPError as exc:
            log.warning("TTS request error: %s; degrading to text-only", exc)
            return AudioSegment(audio=b"", mime_type="audio/mpeg", ok=False)

    async def aclose(self) -> None:
        await self._client.aclose()


def _build_ssml(text: str, voice: str) -> str:
    safe = saxutils.escape(text)
    lang = "-".join(voice.split("-")[:2]) if "-" in voice else "zh-CN"
    voice_attr = saxutils.quoteattr(voice)
    lang_attr = saxutils.quoteattr(lang)
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang={lang_attr}>'
        f'<voice name={voice_attr}>{safe}</voice>'
        f"</speak>"
    )
