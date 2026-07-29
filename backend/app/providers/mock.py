"""Mock providers — the default, and the reason this project runs with no keys.

Nothing in this module may touch the network. `tests/test_mock_offline.py`
enforces that invariant by banning socket creation during a full pipeline run.
"""

from __future__ import annotations

import asyncio
import io
import math
import random
import re
import struct
import wave
from dataclasses import dataclass

from app.models import AudioSegment, Chunk, KnowledgeType, Message, ScoredChunk, Source, Viseme
from app.text import to_speech_text

# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------

_MOCK_CHUNKS: list[Chunk] = [
    Chunk(
        id="mock-freezone-vs-mainland",
        topic="示例国别 / 主体设立",
        type=KnowledgeType.DECISION_FRAMEWORK,
        title="自贸区主体与内地主体的选择维度（示例）",
        content=(
            "选择自贸区还是内地主体，取决于业务是否需要直接面向本地终端市场。"
            "自贸区主体在外资持股、利润汇出和设立速度上更宽松；内地主体则在承接"
            "本地政府与国企合同、开展本地零售业务上不可替代。"
        ),
        dimensions=[
            "业务是否需要直接面向本地终端市场",
            "是否需要承接本地政府或国企合同",
            "对外资持股比例的要求",
            "利润汇出与外汇管制的容忍度",
        ],
        redlines=["自贸区主体通常不得直接在关境内开展经营活动，需通过分销商或设立内地实体"],
        keywords=["自贸区", "内地", "设立", "主体", "持股", "freezone", "mainland"],
        source=Source(title="示例数据（非真实政策）", is_sample_data=True),
    ),
    Chunk(
        id="mock-tax-registration-window",
        topic="示例国别 / 税务",
        type=KnowledgeType.CHECKLIST,
        title="设立后的税务登记时限（示例）",
        content=(
            "主体设立完成后需在规定窗口期内完成税务登记。逾期通常触发定额罚款，"
            "且会影响后续的银行开户与资质申请。"
        ),
        dimensions=[],
        redlines=["逾期登记的罚款通常不可通过事后补登豁免"],
        keywords=["税务", "登记", "时限", "罚款", "tax", "registration"],
        source=Source(title="示例数据（非真实政策）", is_sample_data=True),
    ),
    Chunk(
        id="mock-banking-account-opening",
        topic="示例国别 / 银行",
        type=KnowledgeType.FACT,
        title="企业银行开户的常见卡点（示例）",
        content=(
            "开户审核关注实际控制人背景、资金来源说明与本地经营实质。"
            "缺少本地办公场地租约或本地雇员，通常会被要求补充材料或直接拒绝。"
        ),
        keywords=["银行", "开户", "账户", "实质", "bank", "account"],
        source=Source(title="示例数据（非真实政策）", is_sample_data=True),
    ),
]


class MockRetriever:
    """Keyword overlap over a tiny built-in corpus.

    Scores are intentionally honest: a question with no keyword overlap gets
    ~0, which trips the refusal threshold instead of inventing an answer.
    """

    name = "mock"

    @property
    def size(self) -> int:
        return len(_MOCK_CHUNKS)

    @property
    def sample_data_only(self) -> bool:
        return all(chunk.source.is_sample_data for chunk in _MOCK_CHUNKS)

    @property
    def topics(self) -> list[str]:
        return list(dict.fromkeys(c.topic for c in _MOCK_CHUNKS if c.topic))

    async def search(self, query: str, k: int) -> list[ScoredChunk]:
        q = query.lower()
        tokens = set(re.findall(r"[\w一-鿿]+", q))
        scored: list[ScoredChunk] = []
        for chunk in _MOCK_CHUNKS:
            hits = sum(1 for kw in chunk.keywords if kw.lower() in q)
            title_hits = sum(1 for t in tokens if len(t) >= 2 and t in chunk.title.lower())
            denom = max(len(chunk.keywords), 1)
            score = min(1.0, (hits / denom) * 1.6 + title_hits * 0.12)
            if score > 0:
                scored.append(ScoredChunk(chunk=chunk, score=round(score, 4)))
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:k]

    async def aclose(self) -> None:
        return None


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

_CONTEXT_BLOCK_RE = re.compile(
    r"^\[(?P<index>\d{1,2})\]\s*(?P<body>.*?)(?=^\[\d{1,2}\]\s|\Z)",
    re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class _ContextEntry:
    index: str
    title: str
    summary: str
    dimensions: tuple[str, ...]
    redlines: tuple[str, ...]


def _parse_context(context: str) -> list[_ContextEntry]:
    entries: list[_ContextEntry] = []
    for match in _CONTEXT_BLOCK_RE.finditer(context):
        lines = [line.rstrip() for line in match.group("body").strip().splitlines()]
        if not lines:
            continue

        title = lines[0].strip()
        body: list[str] = []
        sections: dict[str, list[str]] = {"dimensions": [], "redlines": []}
        section: str | None = None

        for line in lines[1:]:
            stripped = line.strip()
            if stripped == "判断维度：":
                section = "dimensions"
                continue
            if stripped == "红线：":
                section = "redlines"
                continue
            if stripped.startswith("（类型："):
                continue
            if section and stripped.startswith("- "):
                sections[section].append(stripped[2:].strip())
            elif section is None and stripped:
                body.append(stripped)

        summary = "".join(body)
        first_sentence = re.split(r"(?<=[。！？!?])", summary, maxsplit=1)[0].strip()
        entries.append(
            _ContextEntry(
                index=match.group("index"),
                title=title,
                summary=first_sentence,
                dimensions=tuple(sections["dimensions"]),
                redlines=tuple(sections["redlines"]),
            )
        )
    return entries


class MockLLM:
    """Composes a cited answer from whatever context the pipeline injected.

    It reads the same numbered `[n] Title` blocks a real model would see, so
    the citation plumbing is genuinely exercised rather than stubbed with a
    fixed string.
    """

    name = "mock"

    def __init__(self, *, delay_s: float = 0.035) -> None:
        self._delay = delay_s

    async def stream(self, messages: list[Message]):
        context = next((m.content for m in messages if m.role == "system"), "")
        question = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        ).strip()
        entries = _parse_context(context)

        text = self._compose(question, entries)
        for token in _tokenize_for_stream(text):
            await asyncio.sleep(self._delay)
            yield token

    @staticmethod
    def _compose(question: str, entries: list[_ContextEntry]) -> str:
        if not entries:
            return (
                "[neutral]（Mock 模式）我在当前知识库中没有找到支撑材料，"
                "因此不对这个问题作答。"
            )

        first = entries[0]
        lines = [f"[neutral]（Mock 模式）关于「{question}」，我只依据检索到的示例材料回答。"]

        if first.dimensions:
            labels = ("第一", "第二", "第三", "第四")
            dimensions = "；".join(
                f"{labels[i]}，{item}" for i, item in enumerate(first.dimensions[:4])
            )
            lines.append(f"判断时先看这些维度：{dimensions}。[{first.index}]")
        elif first.summary:
            lines.append(f"核心信息是：{first.summary}[{first.index}]")
        else:
            lines.append(f"最相关的材料是《{first.title}》[{first.index}]。")

        if first.redlines:
            lines.append(f"需要特别注意：{'；'.join(first.redlines[:2])}。[{first.index}]")

        if len(entries) > 1:
            others = "、".join(f"《{entry.title}》[{entry.index}]" for entry in entries[1:3])
            lines.append(f"还可以结合 {others} 交叉核对。")
        lines.append(
            "这些内容全部是合成示例数据，不代表真实政策，也不构成法律、税务或投资建议。"
        )
        return "".join(lines)

    async def aclose(self) -> None:
        return None


def _tokenize_for_stream(text: str) -> list[str]:
    """Chop text into small pieces so the frontend sees a real token stream."""
    out: list[str] = []
    step = 4
    for i in range(0, len(text), step):
        out.append(text[i : i + step])
    return out


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

_SAMPLE_RATE = 16_000
_SECONDS_PER_CHAR = 0.20


class MockTTS:
    """Generates a WAV locally so lip sync has a real waveform to analyse.

    It is not speech — it is a syllable-shaped amplitude envelope. That is
    enough to drive the RMS-based mouth and to prove the audio queue,
    ordering, viseme gating and Stop paths all work without any credentials.
    """

    name = "mock"

    async def synthesize(self, text: str, voice: str) -> AudioSegment:
        spoken = to_speech_text(text)
        if not spoken:
            return AudioSegment(audio=b"", mime_type="audio/wav", visemes=[], ok=True)

        duration = max(0.35, len(spoken) * _SECONDS_PER_CHAR)
        pcm, visemes = _render_syllables(spoken, duration)
        return AudioSegment(
            audio=_wrap_wav(pcm),
            mime_type="audio/wav",
            visemes=visemes,
            ok=True,
        )

    async def aclose(self) -> None:
        return None


def _render_syllables(text: str, duration_s: float) -> tuple[bytes, list[Viseme]]:
    """Build a PCM buffer whose envelope opens once per character."""
    # Deterministic per-text jitter so the same sentence always renders the
    # same waveform. Not security-sensitive; it only shapes a placeholder tone.
    rng = random.Random(hash(text) & 0xFFFF_FFFF)  # noqa: S311
    total = int(_SAMPLE_RATE * duration_s)
    per_char = max(1, total // max(1, len(text)))

    samples = bytearray()
    visemes: list[Viseme] = []
    phase = 0.0

    for idx, ch in enumerate(text):
        start = idx * per_char / _SAMPLE_RATE
        if ch.isspace():
            samples.extend(b"\x00\x00" * per_char)
            continue

        # Silence at punctuation gives the mouth a reason to close.
        if not ch.isalnum() and not ("一" <= ch <= "鿿"):
            samples.extend(b"\x00\x00" * per_char)
            continue

        freq = rng.uniform(110.0, 260.0)
        peak = rng.uniform(0.45, 0.95)
        for n in range(per_char):
            t = n / per_char
            # Raised-cosine envelope: closed -> open -> closed per syllable.
            env = 0.5 * (1.0 - math.cos(2.0 * math.pi * min(t, 1.0)))
            phase += 2.0 * math.pi * freq / _SAMPLE_RATE
            value = math.sin(phase) * env * peak * 0.6
            value += math.sin(phase * 2.03) * env * peak * 0.18
            samples.extend(struct.pack("<h", int(max(-1.0, min(1.0, value)) * 32000)))

        visemes.append(
            Viseme(offset_s=round(start, 4), duration_s=round(per_char / _SAMPLE_RATE, 4), text=ch)
        )

    return bytes(samples), visemes


def _wrap_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()
