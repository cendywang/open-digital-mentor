"""The mentor turn: retrieve -> answer -> speak.

One question in, a stream of protocol events out. No tools, no agent loop, no
branching on model output. The whole surface is this file plus three provider
interfaces, keeping the execution path small enough to review.

Concurrency shape: text deltas are emitted the moment they arrive so subtitles
lead the audio, while each completed sentence is handed to TTS in a background
task. Those tasks finish out of order, so audio events carry `seq` and the
client reorders. Cancelling the turn cancels every in-flight TTS task, which
is what stops the meter running after the user hits Stop.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import AsyncIterator

from app.config import Settings
from app.models import Citation, ScoredChunk
from app.processing_marker import TURN_DONE
from app.prompts import build_messages, build_refusal
from app.protocol import (
    AudioEvent,
    ErrorCode,
    ErrorEvent,
    ExpressionEvent,
    RetrievalEvent,
    ServerEvent,
    TextDeltaEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from app.providers import LLMProvider, Retriever, TTSProvider
from app.text import SentenceAccumulator, clean_markdown_for_tts, extract_expressions

log = logging.getLogger(__name__)

_SNIPPET_CHARS = 400


class MentorPipeline:
    def __init__(
        self,
        *,
        retriever: Retriever,
        llm: LLMProvider,
        tts: TTSProvider,
        settings: Settings,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._tts = tts
        self._settings = settings

    # -- public -------------------------------------------------------------

    async def run(self, turn_id: str, question: str) -> AsyncIterator[ServerEvent]:
        queue: asyncio.Queue[ServerEvent | object] = asyncio.Queue()
        producer = asyncio.create_task(self._produce(turn_id, question, queue))

        try:
            while True:
                event = await queue.get()
                if event is TURN_DONE:
                    break
                yield event  # type: ignore[misc]
        finally:
            if not producer.done():
                producer.cancel()
            # Wait for cancellation to land so no orphaned TTS task survives
            # the turn and keeps spending on the provider.
            await asyncio.gather(producer, return_exceptions=True)

    # -- internals ----------------------------------------------------------

    async def _produce(
        self, turn_id: str, question: str, queue: asyncio.Queue[ServerEvent | object]
    ) -> None:
        tts_tasks: list[asyncio.Task[None]] = []
        try:
            await queue.put(TurnStartEvent(turn_id=turn_id))

            results = await self._retriever.search(question, self._settings.retriever_top_k)
            top_score = results[0].score if results else 0.0
            accepted = [
                result
                for result in results
                if result.score >= self._settings.retriever_min_score
            ]
            refused = not accepted
            citations = _to_citations(accepted)

            await queue.put(
                RetrievalEvent(
                    turn_id=turn_id,
                    citations=citations,
                    refused=refused,
                    top_score=top_score,
                )
            )

            if refused:
                text, segments = await self._emit_refusal(turn_id, results, queue, tts_tasks)
            else:
                text, segments = await self._emit_answer(
                    turn_id, question, accepted, queue, tts_tasks
                )

            # `turn.end` must genuinely mean "nothing more is coming for this
            # turn", so it waits for every synthesis task. Emitting it when the
            # text stream ended let late audio leak into the *next* turn and
            # be played under the wrong question.
            if tts_tasks:
                await asyncio.gather(*tts_tasks)

            await queue.put(
                TurnEndEvent(turn_id=turn_id, text=text, total_segments=segments)
            )

        except asyncio.CancelledError:
            for task in tts_tasks:
                task.cancel()
            raise
        except Exception:  # noqa: BLE001 - converted to a stable client error
            log.exception("turn %s failed", turn_id)
            for task in tts_tasks:
                task.cancel()
            await queue.put(
                ErrorEvent(
                    turn_id=turn_id,
                    code=ErrorCode.UPSTREAM_FAILED,
                    message="upstream provider failed; check server logs",
                )
            )
        finally:
            await queue.put(TURN_DONE)

    async def _emit_refusal(
        self,
        turn_id: str,
        results: list[ScoredChunk],
        queue: asyncio.Queue[ServerEvent | object],
        tts_tasks: list[asyncio.Task[None]],
    ) -> tuple[str, int]:
        """The refusal path is a first-class feature, not an error branch."""
        # Prefer the corpus-wide topic list: an off-corpus question usually
        # retrieves nothing at all, so `results` is empty exactly when the
        # user most needs to be told what this mentor does know.
        known_topics = getattr(self._retriever, "topics", None) or [
            r.chunk.topic for r in results
        ]
        text = build_refusal(known_topics)
        display, expressions = extract_expressions(text)

        if expressions:
            await queue.put(ExpressionEvent(turn_id=turn_id, expression=expressions[0]))
        await queue.put(TextDeltaEvent(turn_id=turn_id, seq=0, text=display))

        tts_tasks.append(
            asyncio.create_task(self._synthesize(turn_id, 0, display.strip(), queue))
        )
        return display, 1

    async def _emit_answer(
        self,
        turn_id: str,
        question: str,
        results: list[ScoredChunk],
        queue: asyncio.Queue[ServerEvent | object],
        tts_tasks: list[asyncio.Task[None]],
    ) -> tuple[str, int]:
        messages = build_messages(question, results)
        accumulator = SentenceAccumulator()
        semaphore = asyncio.Semaphore(self._settings.max_concurrent_tts_per_session)

        full_text: list[str] = []
        seen_expressions: set[str] = set()
        text_seq = 0
        segment_seq = 0

        async for delta in self._llm.stream(messages):
            chunk = accumulator.feed(delta)

            for expression in chunk.expressions:
                if expression not in seen_expressions:
                    seen_expressions.add(expression)
                    await queue.put(ExpressionEvent(turn_id=turn_id, expression=expression))

            if chunk.display:
                full_text.append(chunk.display)
                await queue.put(
                    TextDeltaEvent(turn_id=turn_id, seq=text_seq, text=chunk.display)
                )
                text_seq += 1

            for sentence in chunk.sentences:
                tts_tasks.append(
                    asyncio.create_task(
                        self._synthesize(turn_id, segment_seq, sentence, queue, semaphore)
                    )
                )
                segment_seq += 1

        for sentence in accumulator.flush():
            tts_tasks.append(
                asyncio.create_task(
                    self._synthesize(turn_id, segment_seq, sentence, queue, semaphore)
                )
            )
            segment_seq += 1

        return "".join(full_text).strip(), segment_seq

    async def _synthesize(
        self,
        turn_id: str,
        seq: int,
        text: str,
        queue: asyncio.Queue[ServerEvent | object],
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        """Synthesize one segment. Never raises — audio is best-effort."""
        spoken = clean_markdown_for_tts(text)
        try:
            if semaphore is not None:
                async with semaphore:
                    segment = await self._tts.synthesize(spoken, self._settings.tts_voice)
            else:
                segment = await self._tts.synthesize(spoken, self._settings.tts_voice)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("TTS failed for turn %s seq %s: %s", turn_id, seq, exc)
            await queue.put(
                AudioEvent(turn_id=turn_id, seq=seq, audio="", text=spoken, ok=False)
            )
            return

        await queue.put(
            AudioEvent(
                turn_id=turn_id,
                seq=seq,
                audio=base64.b64encode(segment.audio).decode("ascii") if segment.audio else "",
                mime_type=segment.mime_type,
                text=spoken,
                visemes=segment.visemes,
                ok=segment.ok,
            )
        )


def _to_citations(results: list[ScoredChunk]) -> list[Citation]:
    return [
        Citation(
            index=i + 1,
            id=r.chunk.id,
            title=r.chunk.title,
            snippet=r.chunk.content[:_SNIPPET_CHARS],
            source=r.chunk.source,
            type=r.chunk.type,
        )
        for i, r in enumerate(results)
    ]
