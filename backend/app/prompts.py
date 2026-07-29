"""Prompt construction.

Two things this prompt has to get right, and they are the two things that
separate a knowledge mentor from a chatbot with a 3D skin:

  1. Every substantive claim carries a `[n]` marker tied to a real entry.
  2. When the retrieved context does not cover the question, the mentor says
     so instead of improvising. Enterprise buyers trust a system that declines
     far more than one that always has an answer.

The refusal decision is made in code (score threshold) *before* the model is
called, so it does not depend on the model choosing to behave. This prompt is
the second line of defence, not the first.
"""

from __future__ import annotations

from app.models import Message, Role, ScoredChunk

SYSTEM_PREAMBLE = """你是一位出海业务的资深顾问，正在以数字导师的形式回答提问。

回答规则：
1. 只依据下方【知识库材料】作答。材料之外的内容，一律不要编造。
2. 每一处实质性结论后面必须标注来源编号，格式为 [1]、[2]。可以在一句话后标多个。
3. 如果材料中包含「判断维度」，优先按维度组织回答，先讲怎么判断，再讲结论。
4. 如果材料中包含「红线」，必须明确指出。
5. 如果材料不足以回答，直接说明「当前知识库没有覆盖这个问题」，并说明缺什么。不要用常识补齐。
6. 回答控制在 300 字以内，口语化，适合朗读。不要使用 Markdown 表格和代码块。
7. 可在回答开头用一个表情标记表达语气，取值为
   [neutral] [happy] [relaxed] [sad] [surprised] [angry] 之一。

【知识库材料】
{context}
"""

REFUSAL_TEMPLATE = (
    "[neutral]这个问题超出了我当前知识库的覆盖范围，我不能给你一个可靠的答案。\n\n"
    "我的知识库目前覆盖的是{topics}。"
    "如果你的问题属于这些范围，可以换个说法再问一次；"
    "如果不属于，需要先把相应的知识补充进来，我才能基于材料回答。"
)


def build_context(results: list[ScoredChunk]) -> str:
    """Render retrieved entries as numbered, citable blocks."""
    if not results:
        return "（无）"
    return "\n\n".join(r.chunk.as_prompt_block(i + 1) for i, r in enumerate(results))


def build_messages(question: str, results: list[ScoredChunk]) -> list[Message]:
    return [
        Message(role=Role.SYSTEM, content=SYSTEM_PREAMBLE.format(context=build_context(results))),
        Message(role=Role.USER, content=question),
    ]


def build_refusal(known_topics: list[str]) -> str:
    if known_topics:
        unique = list(dict.fromkeys(t for t in known_topics if t))[:5]
        topics = "、".join(unique) if unique else "有限的几个主题"
    else:
        topics = "有限的几个主题"
    return REFUSAL_TEMPLATE.format(topics=topics)
