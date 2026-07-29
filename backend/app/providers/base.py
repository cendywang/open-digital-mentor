"""The three provider interfaces.

Everything replaceable in this project sits behind one of these. If you want
to plug in your own vector store, your own model gateway, or your own voice,
you implement one Protocol and register it in `app/providers/__init__.py` —
no other file needs to change.

Note what is deliberately absent: there is no tool interface, no code
execution, no browser, and no filesystem access. This pipeline structurally
cannot do any of them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from app.models import AudioSegment, Message, ScoredChunk


@runtime_checkable
class Retriever(Protocol):
    """Finds knowledge entries relevant to a question."""

    name: str

    async def search(self, query: str, k: int) -> list[ScoredChunk]:
        """Return up to `k` entries, highest score first.

        Scores must be comparable against `ODM_RETRIEVER_MIN_SCORE`: anything
        below it is treated as "not covered by the knowledge base" and drives
        the refusal path. A retriever that always returns a high score turns
        the mentor into a bullshitter, so implementations should return
        honestly-low scores rather than clamping.
        """
        ...

    async def aclose(self) -> None: ...


@runtime_checkable
class LLMProvider(Protocol):
    """Streams an answer given a prompt."""

    name: str

    def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        """Yield answer text incrementally.

        Implementations must be cancellable: when the user hits Stop the
        pipeline cancels the surrounding task, and the provider is expected to
        close its connection promptly rather than keep burning tokens.
        """
        ...

    async def aclose(self) -> None: ...


@runtime_checkable
class TTSProvider(Protocol):
    """Turns one sentence into one audio segment."""

    name: str

    async def synthesize(self, text: str, voice: str) -> AudioSegment:
        """Synthesize `text`.

        Must not raise on provider failure — return `AudioSegment(ok=False)`
        instead. Audio is a nice-to-have; the text answer and subtitles must
        survive a dead TTS backend.
        """
        ...

    async def aclose(self) -> None: ...
