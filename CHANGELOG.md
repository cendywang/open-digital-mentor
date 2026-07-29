# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 的结构。

## Unreleased

### Added

- Public contribution, security, release, and dependency-update workflows.

### Fixed

- Clean CI environments now install frontend dependencies reliably, with a lockfile verified on
  npm 10 and npm 11.

## 0.1.0 - 2026-07-28

### Added

- End-to-end Retriever → LLM → sentence TTS → VRM playback flow.
- Offline Mock mode with no credentials or outbound runtime requests.
- Local YAML/BM25 retrieval, citations, corpus-bound refusal, and sample-data labels.
- OpenAI-compatible LLM, MiniMax WebSocket TTS, and Azure Speech adapters.
- Ordered audio queue, Stop cancellation, subtitles, approximate lip sync, expressions, and
  procedural idle motion.
- Docker Compose, CI, secret scanning, asset verification, and bilingual README.
