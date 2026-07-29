import asyncio

import pytest

from app.config import REPO_ROOT, Settings
from app.knowledge import load_corpus
from app.models import Message
from app.pipeline import MentorPipeline
from app.providers.mock import MockLLM, MockRetriever, MockTTS
from app.providers.retriever_local import LocalRetriever


def make_settings(**overrides) -> Settings:
    base = {
        "ODM_MODE": "mock",
        "ODM_RETRIEVER_TOP_K": "4",
        "ODM_RETRIEVER_MIN_SCORE": "0.15",
        "ODM_MAX_CONCURRENT_TTS_PER_SESSION": "3",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def build(**overrides) -> MentorPipeline:
    return MentorPipeline(
        retriever=MockRetriever(),
        llm=MockLLM(delay_s=0.0),
        tts=MockTTS(),
        settings=make_settings(**overrides),
    )


async def collect(pipeline: MentorPipeline, question: str) -> list:
    return [e async for e in pipeline.run("t1", question)]


async def test_answer_emits_citations_and_audio():
    events = await collect(build(), "自贸区和内地主体怎么选")
    kinds = [e.type for e in events]

    assert kinds[0] == "turn.start"
    assert "retrieval" in kinds
    assert "turn.end" in kinds

    retrieval = next(e for e in events if e.type == "retrieval")
    assert not retrieval.refused
    assert retrieval.citations
    assert retrieval.citations[0].index == 1
    assert retrieval.citations[0].source.title

    audio = [e for e in events if e.type == "audio"]
    assert audio, "expected at least one audio segment"
    assert all(a.audio for a in audio), "mock TTS must produce real bytes"


async def test_audio_seq_covers_every_segment_exactly_once():
    """Segments are synthesised concurrently and do arrive out of order."""
    events = await collect(build(), "自贸区和内地主体怎么选")
    end = next(e for e in events if e.type == "turn.end")
    seqs = sorted(e.seq for e in events if e.type == "audio")
    assert seqs == list(range(end.total_segments))


async def test_turn_end_is_the_last_event():
    """turn.end must mean "nothing more is coming".

    Emitting it when the text stream finished let audio from turn N arrive
    during turn N+1 and play under the wrong question.
    """
    events = await collect(build(), "自贸区和内地主体怎么选")
    assert events[-1].type == "turn.end"
    assert all(e.type != "audio" for e in events[events.index(events[-1]) :][1:])


async def test_refusal_turn_also_delivers_audio_before_turn_end():
    events = await collect(build(), "帮我写一段 Python 快速排序")
    assert events[-1].type == "turn.end"
    audio = [e for e in events if e.type == "audio"]
    assert len(audio) == 1
    assert audio[0].seq == 0


async def test_off_corpus_question_is_refused():
    events = await collect(build(), "帮我写一段 Python 快速排序")
    retrieval = next(e for e in events if e.type == "retrieval")
    assert retrieval.refused is True
    assert retrieval.citations == []

    text = "".join(e.text for e in events if e.type == "text.delta")
    assert "知识库" in text
    # A refusal is still spoken — the avatar should say it, not go silent.
    assert any(e.type == "audio" for e in events)


async def test_spoken_text_never_contains_expression_markers():
    events = await collect(build(), "自贸区和内地主体怎么选")
    for event in events:
        if event.type in ("audio", "text.delta"):
            assert "[neutral]" not in event.text
            assert "[happy]" not in event.text


async def test_expression_is_emitted_as_an_event():
    events = await collect(build(), "自贸区和内地主体怎么选")
    assert any(e.type == "expression" for e in events)


async def test_audio_and_synchronized_subtitle_text_are_clean_for_tts():
    class MarkdownLLM:
        name = "markdown"

        async def stream(self, messages):
            yield "[happy]## **重点**：按材料办理 [1]。"

        async def aclose(self):
            return None

    pipeline = MentorPipeline(
        retriever=MockRetriever(),
        llm=MarkdownLLM(),
        tts=MockTTS(),
        settings=make_settings(),
    )
    events = await collect(pipeline, "自贸区怎么选")

    display = "".join(e.text for e in events if e.type == "text.delta")
    audio = [e for e in events if e.type == "audio"]
    assert "**重点**" in display and "[1]" in display
    assert audio
    assert all("**" not in event.text for event in audio)
    assert all("[1]" not in event.text for event in audio)
    assert all("[happy]" not in event.text for event in audio)
    assert any(e.type == "expression" and e.expression == "happy" for e in events)


async def test_tts_failure_degrades_to_text_only():
    class BrokenTTS:
        name = "broken"

        async def synthesize(self, text, voice):
            raise RuntimeError("tts is down")

        async def aclose(self):
            return None

    pipeline = MentorPipeline(
        retriever=MockRetriever(),
        llm=MockLLM(delay_s=0.0),
        tts=BrokenTTS(),
        settings=make_settings(),
    )
    events = await collect(pipeline, "自贸区和内地主体怎么选")

    assert any(e.type == "text.delta" for e in events), "text must survive dead TTS"
    audio = [e for e in events if e.type == "audio"]
    assert audio and all(a.ok is False and a.audio == "" for a in audio)
    assert not any(e.type == "error" for e in events)


async def test_cancelling_a_turn_stops_further_tts_work():
    """Stop must not leave background synthesis running up the bill."""
    started = 0
    finished = 0

    class SlowTTS:
        name = "slow"

        async def synthesize(self, text, voice):
            nonlocal started, finished
            started += 1
            await asyncio.sleep(5)
            finished += 1
            return MockTTS().synthesize(text, voice)

        async def aclose(self):
            return None

    pipeline = MentorPipeline(
        retriever=MockRetriever(),
        llm=MockLLM(delay_s=0.01),
        tts=SlowTTS(),
        settings=make_settings(),
    )

    async def drain():
        async for _ in pipeline.run("t1", "自贸区和内地主体怎么选"):
            pass

    task = asyncio.create_task(drain())
    await asyncio.sleep(0.4)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await asyncio.sleep(0.2)
    assert finished == 0, "cancelled turn kept synthesising audio"


async def test_mock_llm_only_cites_supplied_context():
    llm = MockLLM(delay_s=0.0)
    messages = [
        Message(role="system", content="[1] 甲\n\n[2] 乙"),
        Message(role="user", content="q"),
    ]
    text = "".join([t async for t in llm.stream(messages)])
    assert "[1]" in text
    assert "[3]" not in text


async def test_mock_answer_exposes_decision_dimensions_and_redline():
    retriever = LocalRetriever(REPO_ROOT / "knowledge")
    pipeline = MentorPipeline(
        retriever=retriever,
        llm=MockLLM(delay_s=0.0),
        tts=MockTTS(),
        settings=make_settings(ODM_RETRIEVER="local"),
    )

    events = await collect(pipeline, "自贸区和关境内主体怎么选")
    text = "".join(e.text for e in events if e.type == "text.delta")

    assert "判断时先看这些维度" in text
    assert "业务是否需要直接面向本地终端客户收款" in text
    assert "需要特别注意" in text
    assert "[1]" in text


@pytest.mark.parametrize(
    "question",
    [
        "自贸区和关境内主体怎么选",
        "企业开户材料要准备什么",
        "数据跨境前要评估哪些因素",
        "进口责任主体由谁担任",
        "本地经销商应该怎么筛选",
    ],
)
async def test_five_citations_are_verbatim_and_exist_in_corpus(question):
    corpus = {chunk.id: chunk for chunk in load_corpus(REPO_ROOT / "knowledge")}
    pipeline = MentorPipeline(
        retriever=LocalRetriever(REPO_ROOT / "knowledge"),
        llm=MockLLM(delay_s=0.0),
        tts=MockTTS(),
        settings=make_settings(ODM_RETRIEVER="local"),
    )

    events = await collect(pipeline, question)
    retrieval = next(event for event in events if event.type == "retrieval")

    assert not retrieval.refused
    assert retrieval.citations
    for citation in retrieval.citations:
        source = corpus[citation.id]
        assert citation.title == source.title
        assert citation.snippet in source.content
        assert citation.source == source.source
