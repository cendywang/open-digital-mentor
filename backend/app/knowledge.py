"""Loading the knowledge corpus from disk.

The corpus is plain YAML under `knowledge/` (configurable via
`ODM_KNOWLEDGE_DIR`). Replacing that directory replaces the mentor's entire
domain — no code change, no rebuild, no database.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from app.models import Chunk, KnowledgeType, Source

log = logging.getLogger(__name__)


class KnowledgeError(Exception):
    pass


def load_corpus(directory: Path) -> list[Chunk]:
    """Read every `*.yaml` / `*.yml` under `directory` into Chunks."""
    if not directory.exists():
        raise KnowledgeError(f"knowledge directory not found: {directory}")

    files = sorted(p for p in directory.rglob("*") if p.suffix in (".yaml", ".yml"))
    if not files:
        raise KnowledgeError(f"no .yaml files found under {directory}")

    chunks: list[Chunk] = []
    seen: set[str] = set()

    for path in files:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise KnowledgeError(f"{path.name}: invalid YAML — {exc}") from exc
        if raw is None:
            continue

        entries = raw if isinstance(raw, list) else [raw]
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise KnowledgeError(f"{path.name}[{i}]: expected a mapping, got {type(entry)}")
            chunk = _to_chunk(entry, path, i)
            if chunk.id in seen:
                raise KnowledgeError(f"duplicate knowledge id: {chunk.id} (in {path.name})")
            seen.add(chunk.id)
            chunks.append(chunk)

    log.info("loaded %d knowledge entries from %s", len(chunks), directory)
    return chunks


def _to_chunk(entry: dict[str, Any], path: Path, index: int) -> Chunk:
    where = f"{path.name}[{index}]"

    for required in ("id", "title", "content"):
        if not entry.get(required):
            raise KnowledgeError(f"{where}: missing required field '{required}'")

    raw_source = entry.get("source") or {}
    if not isinstance(raw_source, dict):
        raise KnowledgeError(f"{where}: 'source' must be a mapping")
    if not raw_source.get("title"):
        # Every claim must be attributable. An entry without a source cannot be
        # cited honestly, so refuse to load it rather than silently render a
        # citation pointing at nothing.
        raise KnowledgeError(f"{where}: 'source.title' is required — every entry must be citable")

    try:
        ktype = KnowledgeType(entry.get("type", "fact"))
    except ValueError as exc:
        valid = ", ".join(t.value for t in KnowledgeType)
        raise KnowledgeError(
            f"{where}: unknown type '{entry.get('type')}' (expected: {valid})"
        ) from exc

    return Chunk(
        id=str(entry["id"]),
        topic=str(entry.get("topic", "")),
        type=ktype,
        title=str(entry["title"]),
        content=str(entry["content"]).strip(),
        dimensions=[str(d) for d in entry.get("dimensions", []) or []],
        redlines=[str(r) for r in entry.get("redlines", []) or []],
        keywords=[str(k) for k in entry.get("keywords", []) or []],
        source=Source(
            title=str(raw_source["title"]),
            url=str(raw_source.get("url", "")),
            retrieved_at=str(raw_source.get("retrieved_at", "")),
            license=str(raw_source.get("license", "")),
            is_sample_data=bool(raw_source.get("is_sample_data", True)),
        ),
    )
