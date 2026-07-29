"""Text processing between the LLM and the TTS engine.

Three jobs, in this order:
  1. pull expression events out of the stream so they never get read aloud
  2. split into sentences early enough that TTS can start before the LLM ends
  3. strip markup so the avatar doesn't pronounce "asterisk asterisk"

Step 3 sounds trivial until you hear a digital human read out "井号井号 二、
星号星号阿联酋星号星号".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Expression markers the model may emit inline, e.g. "[happy] 很高兴见到你".
# Extracted as events and never spoken.
_EXPRESSION_RE = re.compile(r"\[(neutral|happy|angry|sad|relaxed|surprised)\]", re.IGNORECASE)

# Citation markers, e.g. "[1]" / "[1][3]". Kept in the display text, removed
# from the spoken text — nobody wants to hear "方括号一".
_CITATION_RE = re.compile(r"\[(\d{1,2})\]")

# Sentence terminators. The `\.(?=\s|$)` branch is load-bearing: it stops
# "3.5%" and "U.A.E." from being chopped mid-token, while still ending real
# English sentences.
_SENTENCE_END_RE = re.compile(r"[。！？；!?;\n]|\.(?=\s|$)")

_NON_SPEECH_RE = re.compile(r"^[\s\W_]+$", re.UNICODE)

_MD_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"```.*?```", re.DOTALL), " "),          # fenced code
    (re.compile(r"`([^`]*)`"), r"\1"),                    # inline code
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), " "),           # images
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),        # links -> label
    (re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE), ""), # headings
    (re.compile(r"^\s*>\s?", re.MULTILINE), ""),          # blockquotes
    (re.compile(r"^\s*[-*+]\s+", re.MULTILINE), ""),      # bullets
    (re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE), ""),    # ordered list markers
    (re.compile(r"^\s*[-*_]{3,}\s*$", re.MULTILINE), ""), # horizontal rules
    (re.compile(r"<[^>]+>"), " "),                        # html tags
    (re.compile(r"\*\*|__|~~"), ""),                      # bold / strike
    (re.compile(r"(?<!\w)[*_](?!\w)"), ""),               # stray emphasis
    (re.compile(r"\|"), " "),                             # table pipes
)

_UNSPOKEN_CHARS = str.maketrans({c: " " for c in "•▪◦✅❌⚠️→←↑↓※§¶"})


def strip_markdown_for_speech(text: str) -> str:
    """Remove markup that would otherwise be pronounced."""
    out = text
    for pattern, repl in _MD_PATTERNS:
        out = pattern.sub(repl, out)
    out = out.translate(_UNSPOKEN_CHARS)
    out = re.sub(r"[ \t]+", " ", out)
    return out.strip()


def strip_citations_for_speech(text: str) -> str:
    return _CITATION_RE.sub("", text)


def clean_markdown_for_tts(text: str) -> str:
    """Convert display text into the exact sentence sent to TTS."""
    return strip_markdown_for_speech(strip_citations_for_speech(text)).strip()


def to_speech_text(text: str) -> str:
    """Backward-compatible name used by provider implementations."""
    return clean_markdown_for_tts(text)


def is_speakable(text: str) -> bool:
    """False when there is nothing left worth sending to a TTS engine.

    Guards the network call: an empty or punctuation-only fragment should
    produce a silent segment locally, not a round trip.
    """
    return bool(text) and not _NON_SPEECH_RE.match(text)


# A marker may be split across streamed tokens ("[hap" + "py] 你好"), so a
# trailing fragment that could still become one is held back rather than
# forwarded. Digits are excluded so citation markers like "[1]" are never
# withheld.
_PARTIAL_EXPRESSION_RE = re.compile(r"^\[[a-zA-Z]*$")
_MAX_HELD_CHARS = 12


@dataclass
class ExpressionStreamFilter:
    """Removes `[expr]` markers from a token stream that arrives in fragments."""

    _held: str = ""

    def push(self, delta: str) -> tuple[str, list[str]]:
        text, expressions = extract_expressions(self._held + delta)

        start = text.rfind("[")
        if (
            start != -1
            and _PARTIAL_EXPRESSION_RE.match(text[start:])
            and len(text) - start <= _MAX_HELD_CHARS
        ):
            self._held = text[start:]
            text = text[:start]
        else:
            self._held = ""

        return text, expressions

    def flush(self) -> str:
        rest, self._held = self._held, ""
        return rest


@dataclass
class StreamChunk:
    """What one streamed token produced, after filtering."""

    display: str
    sentences: list[str]
    expressions: list[str]


@dataclass
class SentenceAccumulator:
    """Buffers streamed LLM tokens and emits complete sentences.

    Emitting early is what lets TTS overlap generation. Emitting *too* early
    produces choppy prosody, so a fragment must reach `min_chars` before a
    terminator counts — except for the very first sentence, which uses
    `first_min_chars` to get audio started sooner.

    It is also the single place expression markers are stripped, so the
    display text and the spoken text can never disagree about them.
    """

    min_chars: int = 12
    first_min_chars: int = 6
    max_chars: int = 120

    _buf: str = ""
    _emitted: int = 0
    _filter: ExpressionStreamFilter = field(default_factory=ExpressionStreamFilter)

    def _threshold(self) -> int:
        return self.first_min_chars if self._emitted == 0 else self.min_chars

    def feed(self, delta: str) -> StreamChunk:
        """Feed a streamed token."""
        cleaned, expressions = self._filter.push(delta)
        return StreamChunk(
            display=cleaned,
            sentences=self._consume(cleaned),
            expressions=expressions,
        )

    def push(self, delta: str) -> list[str]:
        """Feed a token; return whatever complete sentences that produced."""
        return self.feed(delta).sentences

    def _consume(self, cleaned: str) -> list[str]:
        self._buf += cleaned
        out: list[str] = []
        while True:
            match = _SENTENCE_END_RE.search(self._buf)
            if match:
                end = match.end()
                candidate = self._buf[:end]
                if len(candidate.strip()) >= self._threshold():
                    out.append(candidate.strip())
                    self._buf = self._buf[end:]
                    self._emitted += 1
                    continue
                # Too short to stand alone — keep accumulating past this
                # terminator so "好的。" doesn't become its own audio segment.
                nxt = _SENTENCE_END_RE.search(self._buf, end)
                if nxt is None:
                    break
                candidate = self._buf[: nxt.end()]
                out.append(candidate.strip())
                self._buf = self._buf[nxt.end() :]
                self._emitted += 1
                continue

            # No terminator in sight and the buffer is getting long: cut at the
            # last comma *within* the limit so a run-on paragraph still starts
            # speaking, without letting the segment exceed max_chars.
            if len(self._buf) >= self.max_chars:
                window = self._buf[: self.max_chars]
                cut = max(window.rfind("，"), window.rfind(","), window.rfind(" "))
                if cut <= 0:
                    cut = self.max_chars - 1
                out.append(self._buf[: cut + 1].strip())
                self._buf = self._buf[cut + 1 :]
                self._emitted += 1
                continue
            break

        return [s for s in out if s]

    def flush(self) -> list[str]:
        """Emit whatever is left at end of stream, including any held marker."""
        self._buf += self._filter.flush()
        rest = self._buf.strip()
        self._buf = ""
        if rest:
            self._emitted += 1
            return [rest]
        return []


def extract_expressions(text: str) -> tuple[str, list[str]]:
    """Split `[happy]`-style markers out of the text.

    Returns (text_without_markers, markers_found_lowercased).
    """
    found = [m.group(1).lower() for m in _EXPRESSION_RE.finditer(text)]
    return (_EXPRESSION_RE.sub("", text), found) if found else (text, [])


def used_citation_indices(text: str) -> list[int]:
    """Which `[n]` markers the answer actually used, in order of appearance."""
    seen: list[int] = []
    for m in _CITATION_RE.finditer(text):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return seen
