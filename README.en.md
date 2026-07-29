# Open Digital Mentor

[Chinese / 中文](README.md)

> Knowledge-driven VRM digital mentor starter

An open-source vertical slice that runs end to end, demonstrates grounded answers with
citations, and lets you replace the knowledge base, model providers, and avatar.

**The complete default flow works without any API key.**

**Status: M0 complete (2026-07-28).**

## What it is

```text
question -> read-only retrieval -> cited answer -> TTS -> VRM avatar playback
                          |
                          +-> no supporting knowledge -> explicit refusal
```

There are four replaceable boundaries:

| Boundary | Bundled implementation | Replacement point |
|---|---|---|
| `Retriever` | `mock` / local BM25 | `search()` |
| `LLMProvider` | `mock` / OpenAI-compatible | `stream()` |
| `TTSProvider` | `mock` / MiniMax / Azure Speech | `synthesize()` |
| `AvatarRuntime` | `VrmRenderer` | runtime interface |

It is not a digital-human SaaS, a photorealistic avatar stack, or an enterprise knowledge
management platform. The avatar is a replaceable terminal; the core product behavior is
grounded knowledge, traceable citations, and refusal outside the corpus.

## Quick start

Requirements: Node.js 20.9 or newer, and Python 3.11 or newer.

```bash
# After cloning or downloading this repository:
cd open-digital-mentor
make dev
```

Open <http://localhost:3000>.

The first run installs missing dependencies. You do not need `.env` or an API key. The
default `ODM_MODE=mock` uses local LLM/TTS implementations and reads the 28 synthetic
entries under `knowledge/`. Runtime code makes no outbound request; the assertion lives in
`backend/tests/test_mock_offline.py`.

For an offline acceptance run, execute `make setup` while online, disconnect the machine,
then execute `make dev`.

Docker is also a single command:

```bash
docker compose up --build
```

Compose publishes only `127.0.0.1:3000` and `127.0.0.1:8000` on the host.

### Try these flows

1. Ask the first sample question and inspect the `[1]` citation marker.
2. Open the citation card and compare the quoted source text.
3. Ask for Python quicksort and observe the explicit out-of-scope refusal.
4. Press Stop during playback; audio stops, buffered segments are dropped, and the avatar returns idle.

### 42-second demo

[Open the MP4 demo](docs/demo.mp4): idle, cited answer, expanded source, Stop, and an
explicit out-of-scope refusal, followed by the avatar asset attribution.

## Configure real providers

Create the optional local configuration file:

```bash
make init-env
```

OpenAI-compatible LLM example:

```bash
ODM_MODE=live
ODM_LLM_PROVIDER=openai_compatible
ODM_LLM_BASE_URL=https://api.example.com/v1
ODM_LLM_API_KEY=your-server-side-key
ODM_LLM_MODEL=your-model
ODM_RETRIEVER=local
```

MiniMax WebSocket TTS example:

```bash
ODM_TTS_PROVIDER=minimax
ODM_TTS_API_KEY=your-server-side-key
ODM_TTS_VOICE=your-cloned-voice-id
ODM_TTS_MODEL=speech-2.8-turbo
# ODM_TTS_ENDPOINT=full-request-url             # optional; blank uses the official URL
```

The MiniMax adapter uses the [official WebSocket T2A API](https://platform.minimaxi.com/docs/guides/speech-t2a-websocket)
and collects its streamed MP3 frames into the sentence-sized segment used by the application
protocol. Cancelling a turn closes the upstream task. The Azure Speech adapter remains
available with `ODM_TTS_PROVIDER=azure`, key, voice, and either region or a full endpoint.
`ODM_TTS_ENDPOINT` has the same full-request-URL meaning for every TTS provider and can
target a proxy or private gateway.

Keys are read only by the Python backend. They are never sent to the browser or embedded in
the frontend bundle. `edge-tts` is not bundled. Before adding any TTS client or service,
review its current software license, service terms, and data-processing requirements.

Bundled implementations switch through configuration only:

| Replace | Configuration |
|---|---|
| LLM | `ODM_MODE=live`, `ODM_LLM_PROVIDER=openai_compatible`, URL/model/key |
| MiniMax TTS | `ODM_MODE=live`, `ODM_TTS_PROVIDER=minimax`, key/voice/model, optional endpoint |
| Azure TTS | `ODM_MODE=live`, `ODM_TTS_PROVIDER=azure`, key/voice plus region or full endpoint |
| Retriever | `ODM_RETRIEVER=local` or `mock` |
| VRM file | `NEXT_PUBLIC_ODM_AVATAR_URL=/avatars/your-model.vrm` |

## Replace the knowledge base

`knowledge/` is the mentor's complete knowledge surface. Replace its YAML files and restart;
no application code changes are required.

```yaml
- id: unique-slug
  topic: market / subject
  type: decision_framework        # fact | decision_framework | checklist | redline
  title: Entry title
  content: |
    Supporting text.
  dimensions:
    - A decision dimension
  redlines:
    - A boundary that must not be crossed
  keywords: [keyword]
  source:
    title: Source name
    url: https://example.com/source
    retrieved_at: 2026-07-26
    license: Permission statement
    is_sample_data: false
```

Every entry needs a source title. Duplicate IDs or unattributed entries fail validation. See
`knowledge/README.md` for the full loading contract.

## Replace the avatar

```bash
cp your-avatar.vrm frontend/public/avatars/default.vrm
make verify-vrm
```

The verifier checks file size, humanoid bones, expressions, SpringBone, LookAt, and the exact
three-vrm APIs used by the renderer. You can instead set `NEXT_PUBLIC_ODM_AVATAR_URL`.

## Architecture

```text
+---------------- frontend (Next.js 16 + React 19) ----------------+
| useMentorSession ---- WebSocket protocol v0                       |
|                   +-- AudioQueue: seq reorder + stale-turn drop  |
|                   +-- AvatarRuntime                              |
|                         +-- VrmRenderer (three + three-vrm 3.x)  |
|                              +-- LipSyncDriver                   |
|                              +-- AvatarMotionDriver (pose/idle) |
+------------------------------------------------------------------+
                              | WebSocket
+---------------- backend (FastAPI) -------------------------------+
| /ws -> MentorPipeline                                            |
|          +-- Retriever: low score becomes refusal                |
|          +-- LLMProvider: text stream -> sentence split          |
|          +-- TTSProvider: concurrent sentence synthesis          |
| No agent, code execution, browser tool, or file-writing tool.    |
+------------------------------------------------------------------+
```

Protocol events are `hello`, `turn.start`, `retrieval`, `text.delta`, `expression`, `audio`,
`turn.end`, `interrupted`, and `error`. Every turn event carries `turn_id`; audio carries
`seq` so the client can reorder concurrent synthesis and discard late packets after Stop.

## Extension interfaces

The authoritative backend signatures are in `backend/app/providers/base.py`:

```python
class Retriever(Protocol):
    name: str
    async def search(self, query: str, k: int) -> list[ScoredChunk]: ...
    async def aclose(self) -> None: ...

class LLMProvider(Protocol):
    name: str
    def stream(self, messages: list[Message]) -> AsyncIterator[str]: ...
    async def aclose(self) -> None: ...

class TTSProvider(Protocol):
    name: str
    async def synthesize(self, text: str, voice: str) -> AudioSegment: ...
    async def aclose(self) -> None: ...
```

A custom implementation follows the same small shape:

```python
class MyRetriever:
    name = "my_retriever"

    async def search(self, query: str, k: int) -> list[ScoredChunk]:
        rows = await my_index.search(query, limit=k)
        return [ScoredChunk(chunk=row.chunk, score=row.score) for row in rows]

    async def aclose(self) -> None:
        await my_index.aclose()
```

Add its enum value in `backend/app/config.py` and register one branch in the single factory,
`backend/app/providers/__init__.py`. No retrieval, prompt, protocol, or UI code needs changing.
LLM implementations must honor task cancellation. TTS implementations must return
`AudioSegment(ok=False)` on provider failure so text and subtitles survive.

The frontend boundary is in `frontend/src/avatar/types.ts`:

```typescript
interface AvatarRuntime {
  readonly state: AvatarState;
  mount(canvas: HTMLCanvasElement): void;
  load(url: string): Promise<void>;
  setState(state: AvatarState): void;
  setExpression(expression: AvatarExpression): void;
  speak(request: SpeakRequest): Promise<void>;
  stop(): void;
  dispose(): void;
  onStateChange(listener: (state: AvatarState) => void): () => void;
  getAttribution(): AvatarAttribution | null;
}
```

Implement that interface and instantiate it in `AvatarStage.tsx` to use a non-VRM renderer.
For another VRM model, only the file or environment variable changes.

## Known limitations

These are current behavior, not roadmap claims:

| Limitation | Current behavior |
|---|---|
| Synthetic corpus | Demonstration content only; it is not legal, tax, or investment advice |
| Approximate lip sync | RMS volume-envelope animation, not phoneme-level visemes |
| Sentence-sized audio | Each complete sentence is synthesized and delivered as one segment |
| Sentence boundary gating | Boundaries gate whole sentences, not individual words |
| Live citation integrity | Citation cards only contain loaded corpus entries and unknown markers are not clickable. A live LLM's `[n]` markers are currently prompt-constrained; semantic entailment and mandatory citation coverage are not enforced |
| Measured latency | On 2026-07-26, five local Chrome runs measured 345-364 ms from submit to first Mock audio and 379-387 ms to first answer text. A real MiniMax run delivered the first audio segment of a complete answer in about 1.30 s; a short synthesis returned a 3.31 s MP3 in about 2.38 s. Cloud results depend on model, voice, and network |
| Single-turn dialog | M0 has no managed multi-turn memory |
| No speech input | ASR and microphone input are M1 scope |
| Deployment boundary | No authentication, tenancy, or audit trail; do not expose directly to the public internet |

## Development and security

```bash
make test          # backend and frontend tests
make lint          # ruff and TypeScript
make verify-vrm    # VRM size and runtime compatibility
make security      # dangerous capabilities, dependencies, ignore rules, asset ledger
make check         # all of the above plus a production frontend build
```

Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a patch. Maintainers should use
the [public release checklist](docs/RELEASE_CHECKLIST.md) before publishing.

Mock mode binds the backend to loopback, validates browser WebSocket origins, limits message
size and per-IP connections, and does not log question bodies by default. See `SECURITY.md`
for the deployment boundary and private vulnerability-reporting channel.

## Roadmap

- **M0 (complete):** text question, grounded citations, refusal, TTS playback, lip sync, Stop
- **M1:** speech input, streaming subtitles/audio, user interruption, latency traces, lip-sync amplitude tuning
- **M2:** ingestion scripts, a generic remote Retriever for RAG/KG services, more provider examples, Avatar Manifest, English UI/i18n

Authentication, multi-tenancy, knowledge lifecycle, expert review, long reports, and GraphRAG
are not included in the current starter.

## License

Code is [Apache-2.0](LICENSE). Changes are recorded in [CHANGELOG.md](CHANGELOG.md).
Asset terms are in [ASSETS.md](ASSETS.md), third-party software
notices in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and knowledge provenance in
[KNOWLEDGE_SOURCES.md](KNOWLEDGE_SOURCES.md).

The bundled avatar is a modified CC BY-SA model. Attribution and ShareAlike obligations are
documented in `ASSETS.md` and remain in effect for the optimized derivative.
