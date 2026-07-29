"""BM25 retrieval over the local YAML corpus. No external services.

Why BM25 and not embeddings for M0: it is ~120 lines of stdlib, it runs
offline, it needs no model download, and on a corpus of a few dozen curated
entries it is genuinely competitive. Swapping in a vector store later means
implementing `Retriever` and nothing else.

Chinese is tokenised with character bigrams rather than a word segmenter — no
jieba dependency, and bigrams are a solid proxy for term matching in a corpus
this size.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from pathlib import Path

from app.knowledge import load_corpus
from app.models import Chunk, ScoredChunk

log = logging.getLogger(__name__)

_CJK = r"一-鿿㐀-䶿"
_LATIN_TOKEN_RE = re.compile(rf"[^\s{_CJK}]+")
_CJK_RUN_RE = re.compile(rf"[{_CJK}]+")

_K1 = 1.5
_B = 0.75


def tokenize(text: str) -> list[str]:
    """Latin words lowercased; CJK runs as overlapping character bigrams."""
    lowered = text.lower()
    tokens: list[str] = []

    for run in _CJK_RUN_RE.findall(lowered):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))

    for word in _LATIN_TOKEN_RE.findall(lowered):
        cleaned = re.sub(r"[^\w%.-]", "", word)
        if len(cleaned) >= 2:
            tokens.append(cleaned)

    return tokens


def _chunk_text(chunk: Chunk) -> str:
    """The searchable surface of an entry.

    Title and keywords are repeated to weight them above body prose — a
    poor-man's field boost that avoids a full multi-field BM25F.
    """
    parts = [
        chunk.title,
        chunk.title,
        chunk.topic,
        " ".join(chunk.keywords),
        " ".join(chunk.keywords),
        chunk.content,
        " ".join(chunk.dimensions),
        " ".join(chunk.redlines),
    ]
    return " ".join(p for p in parts if p)


class LocalRetriever:
    """In-memory BM25 index built once at startup."""

    name = "local"

    def __init__(self, directory: Path) -> None:
        self._chunks: list[Chunk] = load_corpus(directory)
        self._docs: list[Counter[str]] = []
        self._lengths: list[int] = []
        self._df: Counter[str] = Counter()

        for chunk in self._chunks:
            tf = Counter(tokenize(_chunk_text(chunk)))
            self._docs.append(tf)
            self._lengths.append(sum(tf.values()))
            self._df.update(tf.keys())

        self._n = len(self._chunks)
        self._avg_len = (sum(self._lengths) / self._n) if self._n else 0.0
        log.info("LocalRetriever indexed %d entries", self._n)

    @property
    def size(self) -> int:
        return self._n

    @property
    def sample_data_only(self) -> bool:
        return all(chunk.source.is_sample_data for chunk in self._chunks)

    @property
    def topics(self) -> list[str]:
        """Distinct topics in the corpus, for an informative refusal.

        "I cover A, B and C" is actionable; "that's outside my scope" is not.
        """
        return list(dict.fromkeys(c.topic for c in self._chunks if c.topic))

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        if df == 0:
            return 0.0
        return math.log(1.0 + (self._n - df + 0.5) / (df + 0.5))

    async def search(self, query: str, k: int) -> list[ScoredChunk]:
        if self._n == 0:
            return []

        q_terms = tokenize(query)
        if not q_terms:
            return []

        raw: list[tuple[int, float]] = []
        for i, tf in enumerate(self._docs):
            length = self._lengths[i] or 1
            score = 0.0
            for term in set(q_terms):
                freq = tf.get(term, 0)
                if not freq:
                    continue
                denom = freq + _K1 * (1 - _B + _B * length / (self._avg_len or 1))
                score += self._idf(term) * (freq * (_K1 + 1)) / denom
            if score > 0:
                raw.append((i, score))

        if not raw:
            return []

        raw.sort(key=lambda p: p[1], reverse=True)

        # Normalise against the theoretical best this query could achieve, so
        # the score is comparable to ODM_RETRIEVER_MIN_SCORE across corpora of
        # different sizes. A question whose terms barely appear scores low and
        # trips the refusal path — which is the behaviour we want.
        unique_terms = set(q_terms)
        matched_terms = {term for term in unique_terms if self._df.get(term, 0) > 0}
        # A single accidental rare-token hit must not make an unrelated query
        # look perfect. Include query coverage in the score so e.g. one shared
        # bigram in a Python question cannot bypass the refusal threshold.
        coverage = len(matched_terms) / len(unique_terms)
        ceiling = sum(self._idf(t) * (_K1 + 1) / _K1 for t in matched_terms) or 1.0
        return [
            ScoredChunk(
                chunk=self._chunks[i],
                # Squaring coverage makes isolated collisions conservative.
                # "快速排序" and the corpus phrase "任务排序" share a
                # bigram, but one collision out of a whole question is not
                # enough evidence to answer.
                score=round(min(1.0, s / ceiling) * coverage**2, 4),
            )
            for i, s in raw[:k]
        ]

    async def aclose(self) -> None:
        return None
