"""WebSocket protocol v0.

Every server event carries `turn_id`, and ordered events also carry `seq`.
The client drops anything whose `turn_id` is not the active turn — the only
reliable defence against packets that were already in flight when the user hit
Stop. Audio additionally needs `seq` because segments are synthesised
concurrently and may arrive out of order.

v0 is deliberately shaped so M1 can add `segment_id` for partial-sentence
streaming without breaking clients.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.models import Citation, Viseme

PROTOCOL_VERSION = 0


# ---------------------------------------------------------------------------
# client -> server
# ---------------------------------------------------------------------------


class AskMessage(BaseModel):
    type: Literal["ask"]
    turn_id: str
    question: str


class StopMessage(BaseModel):
    type: Literal["stop"]
    turn_id: str = ""


# ---------------------------------------------------------------------------
# server -> client
# ---------------------------------------------------------------------------


class ErrorCode(StrEnum):
    BAD_REQUEST = "bad_request"
    MESSAGE_TOO_LONG = "message_too_long"
    RATE_LIMITED = "rate_limited"
    UPSTREAM_FAILED = "upstream_failed"
    INTERNAL = "internal"


class ServerEvent(BaseModel):
    type: str
    turn_id: str = ""


class HelloEvent(ServerEvent):
    type: Literal["hello"] = "hello"
    protocol_version: int = PROTOCOL_VERSION
    mode: str
    providers: dict[str, str]
    knowledge_entries: int
    # Surfaced so the UI can label sample corpora honestly.
    sample_data_only: bool = True


class TurnStartEvent(ServerEvent):
    type: Literal["turn.start"] = "turn.start"


class RetrievalEvent(ServerEvent):
    type: Literal["retrieval"] = "retrieval"
    citations: list[Citation] = Field(default_factory=list)
    refused: bool = False
    top_score: float = 0.0


class TextDeltaEvent(ServerEvent):
    type: Literal["text.delta"] = "text.delta"
    seq: int
    text: str


class ExpressionEvent(ServerEvent):
    type: Literal["expression"] = "expression"
    expression: str


class AudioEvent(ServerEvent):
    type: Literal["audio"] = "audio"
    seq: int
    # base64; empty string means "this segment has no audio, show text only"
    audio: str = ""
    mime_type: str = "audio/wav"
    text: str = ""
    visemes: list[Viseme] = Field(default_factory=list)
    ok: bool = True


class TurnEndEvent(ServerEvent):
    type: Literal["turn.end"] = "turn.end"
    text: str = ""
    total_segments: int = 0


class InterruptedEvent(ServerEvent):
    type: Literal["interrupted"] = "interrupted"


class ErrorEvent(ServerEvent):
    type: Literal["error"] = "error"
    code: ErrorCode = ErrorCode.INTERNAL
    message: str = ""
