import pytest

from app.config import REPO_ROOT
from app.knowledge import KnowledgeError, load_corpus
from app.providers.retriever_local import LocalRetriever, tokenize

SAMPLE_DIR = REPO_ROOT / "knowledge"


def test_sample_corpus_loads():
    chunks = load_corpus(SAMPLE_DIR)
    assert 20 <= len(chunks) <= 30
    assert len({c.id for c in chunks}) == len(chunks)


def test_every_sample_entry_is_marked_as_sample_data():
    for chunk in load_corpus(SAMPLE_DIR):
        assert chunk.source.title, f"{chunk.id} has no citable source"
        assert chunk.source.is_sample_data, f"{chunk.id} claims to be real data"
        assert "非真实政策" in chunk.source.title


def test_decision_frameworks_carry_real_dimensions():
    frameworks = [c for c in load_corpus(SAMPLE_DIR) if c.type.value == "decision_framework"]
    assert len(frameworks) >= 8
    assert all(len(chunk.dimensions) >= 3 for chunk in frameworks)
    assert all(chunk.redlines for chunk in frameworks)


def test_entry_without_source_is_rejected(tmp_path):
    (tmp_path / "bad.yaml").write_text(
        "id: x\ntitle: t\ncontent: c\n", encoding="utf-8"
    )
    with pytest.raises(KnowledgeError, match="source.title"):
        load_corpus(tmp_path)


def test_duplicate_ids_are_rejected(tmp_path):
    body = "- id: dup\n  title: t\n  content: c\n  source:\n    title: s\n"
    (tmp_path / "a.yaml").write_text(body, encoding="utf-8")
    (tmp_path / "b.yaml").write_text(body, encoding="utf-8")
    with pytest.raises(KnowledgeError, match="duplicate"):
        load_corpus(tmp_path)


def test_tokenizer_handles_mixed_scripts():
    tokens = tokenize("自贸区 freezone 设立")
    assert "自贸" in tokens
    assert "freezone" in tokens


async def test_relevant_query_scores_above_threshold():
    retriever = LocalRetriever(SAMPLE_DIR)
    results = await retriever.search("自贸区和关境内主体怎么选", k=4)
    assert results
    assert results[0].score > 0.15
    assert results[0].chunk.id == "entity-freezone-vs-mainland"


@pytest.mark.parametrize(
    ("question", "expected_id"),
    [
        ("企业开户材料要准备什么", "banking-account-opening-pack"),
        ("数据跨境前要评估哪些因素", "data-residency-assessment"),
        ("进口责任主体由谁担任", "trade-importer-of-record"),
        ("本地经销商应该怎么筛选", "channel-distributor-selection"),
        ("员工工作签证应该按什么顺序办理", "labor-visa-sequencing"),
    ],
)
async def test_retrieval_points_at_the_supporting_entry(question, expected_id):
    results = await LocalRetriever(SAMPLE_DIR).search(question, k=4)
    assert results
    assert results[0].score >= 0.15
    assert results[0].chunk.id == expected_id


@pytest.mark.parametrize(
    "question",
    [
        "帮我写一段 Python 快速排序",
        "写一个快速排序",
        "今天天气怎么样",
        "给我推荐一部电影",
    ],
)
async def test_off_corpus_query_scores_low_enough_to_refuse(question):
    """The refusal path depends on honest scoring, so assert it directly."""
    retriever = LocalRetriever(SAMPLE_DIR)
    results = await retriever.search(question, k=4)
    top = results[0].score if results else 0.0
    assert top < 0.15, f"off-corpus query scored {top}, refusal would not fire"


async def test_replacing_the_knowledge_directory_needs_no_code_change(tmp_path):
    (tmp_path / "replacement.yaml").write_text(
        """
id: lunar-oxygen-loop
topic: 月球基地 / 生命支持
type: fact
title: 月球基地氧气循环（测试）
content: 密闭舱通过测试用再生模块循环氧气。
keywords: [月球基地, 氧气循环, 再生模块]
source:
  title: 测试数据
  is_sample_data: true
""".strip(),
        encoding="utf-8",
    )

    retriever = LocalRetriever(tmp_path)
    results = await retriever.search("月球基地怎样循环氧气", k=4)

    assert retriever.size == 1
    assert results[0].chunk.id == "lunar-oxygen-loop"
