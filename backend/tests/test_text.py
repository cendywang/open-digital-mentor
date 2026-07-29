from app.text import (
    SentenceAccumulator,
    clean_markdown_for_tts,
    extract_expressions,
    is_speakable,
    to_speech_text,
    used_citation_indices,
)


def test_markdown_is_not_spoken():
    raw = "## 二、结论\n\n**阿联酋**设立需要 `freezone` 主体 [1]，详见 [文档](https://x.com)。"
    spoken = to_speech_text(raw)
    for junk in ("#", "**", "`", "[1]", "https://", "]("):
        assert junk not in spoken
    assert "阿联酋" in spoken
    assert "文档" in spoken
    assert clean_markdown_for_tts(raw) == spoken


def test_table_pipes_and_bullets_removed():
    spoken = to_speech_text("| A | B |\n- 第一项\n1. 第二项\n> 引用")
    assert "|" not in spoken
    assert "第一项" in spoken and "第二项" in spoken and "引用" in spoken


def test_decimal_is_not_split():
    acc = SentenceAccumulator()
    out = acc.push("增值税率是 5.5% 这一点需要注意。")
    assert len(out) == 1
    assert "5.5%" in out[0]


def test_expressions_extracted_not_spoken():
    text, exprs = extract_expressions("[happy]很高兴见到你")
    assert exprs == ["happy"]
    assert "[happy]" not in text
    assert text == "很高兴见到你"


def test_unspeakable_fragments_detected():
    assert not is_speakable("")
    assert not is_speakable("   ")
    assert not is_speakable("。。。")
    assert is_speakable("你好")


def test_short_fragment_merges_with_next_sentence():
    acc = SentenceAccumulator()
    out = acc.push("好的。这是一句足够长的完整回答内容。")
    # "好的。" alone is too short to justify its own TTS round trip.
    assert all(len(s) > 4 for s in out)
    assert "".join(out).startswith("好的。")


def test_accumulator_emits_then_flushes():
    acc = SentenceAccumulator()
    emitted: list[str] = []
    for token in ["阿联酋设立公司", "需要先选择自贸区。", "另外税务登记", "必须及时完成"]:
        emitted.extend(acc.push(token))
    assert len(emitted) == 1
    emitted.extend(acc.flush())
    assert len(emitted) == 2
    assert "税务登记" in emitted[1]


def test_long_run_on_is_cut_at_comma():
    acc = SentenceAccumulator(max_chars=40)
    out = acc.push("这是一段很长的没有句号的文字，" * 5)
    assert out, "run-on text should still start speaking"
    assert all(len(s) <= 60 for s in out)


def test_citation_indices_in_order_without_duplicates():
    assert used_citation_indices("先看 [2]，再看 [1]，然后再次 [2]。") == [2, 1]
