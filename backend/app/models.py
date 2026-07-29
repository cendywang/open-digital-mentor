"""Core domain types shared by providers, pipeline and WS protocol."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    role: Role
    content: str


class KnowledgeType(StrEnum):
    """What kind of thing a knowledge entry is.

    This is the part that separates a knowledge *mentor* from a generic RAG
    demo: the corpus does not just hold prose, it holds the shape of an
    expert's judgement. `DECISION_FRAMEWORK` and `REDLINE` entries are what
    let an answer say "here are the three dimensions you weigh, and here is
    the line you must not cross" instead of paraphrasing a paragraph.
    """

    FACT = "fact"
    DECISION_FRAMEWORK = "decision_framework"
    CHECKLIST = "checklist"
    REDLINE = "redline"


class Source(BaseModel):
    title: str
    url: str = ""
    retrieved_at: str = ""
    license: str = ""
    # Sample corpora must say so, loudly and in the UI.
    is_sample_data: bool = True


class Chunk(BaseModel):
    """One retrievable knowledge entry."""

    id: str
    topic: str = ""
    type: KnowledgeType = KnowledgeType.FACT
    title: str
    content: str
    dimensions: list[str] = Field(default_factory=list)
    redlines: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    source: Source

    def as_prompt_block(self, index: int) -> str:
        """Render for injection into the LLM prompt, numbered for citation."""
        parts = [f"[{index}] {self.title}"]
        if self.type is not KnowledgeType.FACT:
            parts.append(f"（类型：{self.type.value}）")
        parts.append(self.content.strip())
        if self.dimensions:
            parts.append("判断维度：\n" + "\n".join(f"  - {d}" for d in self.dimensions))
        if self.redlines:
            parts.append("红线：\n" + "\n".join(f"  - {r}" for r in self.redlines))
        return "\n".join(parts)


class ScoredChunk(BaseModel):
    chunk: Chunk
    score: float


class Citation(BaseModel):
    """What the frontend renders as a clickable footnote."""

    index: int
    id: str
    title: str
    snippet: str
    source: Source
    type: KnowledgeType


class Viseme(BaseModel):
    """A mouth-shape hint aligned to the audio timeline.

    Providers that only return sentence-level boundaries emit one of these per
    sentence. The frontend must treat a sparse viseme list as a *declared
    degradation* (amplitude-driven mouth within the window), never present it
    as phoneme-accurate sync.
    """

    offset_s: float
    duration_s: float
    text: str = ""


class AudioSegment(BaseModel):
    """One synthesized sentence."""

    audio: bytes
    mime_type: str = "audio/mpeg"
    visemes: list[Viseme] = Field(default_factory=list)
    # False when the TTS provider failed and we degraded to text-only.
    ok: bool = True


class Answer(BaseModel):
    text: str
    citations: list[Citation] = Field(default_factory=list)
    # True when the retriever found nothing above threshold and the mentor
    # declined to answer. Tracked explicitly so the UI can style it and so
    # tests can assert the refusal path actually fires.
    refused: bool = False
