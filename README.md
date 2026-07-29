# Open Digital Mentor

[English](README.en.md)

> Knowledge-driven VRM digital mentor starter
> 知识驱动的数字导师 —— 数字人形象只是可替换的交互终端

一个可以跑、可以演示、可以整体替换知识库与模型的开源数字导师 Vertical Slice。

**不填任何 API Key 就能完整运行。**

**项目状态：M0 已完成（2026-07-28）。**

---

## 它是什么

```
提问 → 检索只读知识库 → 生成带引用的回答 → TTS → VRM 数字人播报
                                    ↓
                          知识库没覆盖 → 明确拒答
```

四个可替换点，各自只有一个接口：

| 接口 | 内置实现 | 换成你自己的 |
|---|---|---|
| `Retriever` | `mock` / `local`(BM25) | 实现 `search()` |
| `LLMProvider` | `mock` / `openai_compatible` | 实现 `stream()` |
| `TTSProvider` | `mock` / `minimax` / `azure` | 实现 `synthesize()` |
| `AvatarRuntime` | `VrmRenderer` | 实现 5 个方法 |

## 它不是什么

不是数字人 SaaS，不是高写实数字人方案，不是企业知识管理平台。
数字人形象是**可替换的交互终端**，产品价值在知识与引用。

---

## 快速开始

需要 Node ≥ 20.9 和 Python ≥ 3.11。

```bash
# Clone 或下载本仓库后：
cd open-digital-mentor
make dev        # 首次自动安装缺失依赖，然后同时启动前后端
```

打开 http://localhost:3000

不需要创建 `.env`，也不需要任何 API Key。默认 `ODM_MODE=mock`：LLM 与 TTS 使用内置 Mock，
Retriever 读取本地 `knowledge/` 的 28 条合成示例，整条链路**不会发起任何出站网络请求**
（`backend/tests/test_mock_offline.py` 对此有断言）。

首次安装依赖需要访问包仓库；应用运行时不需要外网。要做断网验收，可先执行
`make setup`，断网后再执行 `make dev`。

也可以只用 Docker：

```bash
docker compose up --build
```

Compose 只把 `127.0.0.1:3000` 和 `127.0.0.1:8000` 暴露给宿主机；Mock 模式同样
不需要 `.env` 或 API Key。

### 试这四件事

1. 点「自贸区主体和关境内主体应该怎么选？」——看回答里的 `[1]` `[2]` 角标
2. 点角标下方的引用卡片 → 展开被引用的**原文片段**
3. 点「帮我写一段 Python 快速排序」——**导师会明确拒答**，这是有意设计的
4. 播报中点「停止」——音频立即静音，队列清空，形象回到待机

### 42 秒演示

[查看 MP4 演示](docs/demo.mp4)：待机 → 带引用回答 → 展开原文 → Stop → 域外问题拒答
→ 角色资产署名。

---

## 接入真实模型

先执行 `make init-env`，再编辑根目录 `.env`：

```bash
ODM_MODE=live

ODM_LLM_PROVIDER=openai_compatible
ODM_LLM_BASE_URL=https://api.deepseek.com/v1      # 任何 OpenAI 兼容端点
ODM_LLM_API_KEY=sk-...
ODM_LLM_MODEL=deepseek-chat

ODM_RETRIEVER=local                                # 用 knowledge/ 下的 YAML
```

TTS 保持 `mock` 也能跑（本地生成音节包络波形）。要真实语音：

```bash
ODM_TTS_PROVIDER=minimax
ODM_TTS_API_KEY=...
ODM_TTS_VOICE=你的复刻Voice-ID
ODM_TTS_MODEL=speech-2.8-turbo
# ODM_TTS_ENDPOINT=完整请求URL                  # 可选；留空使用官方地址
```

MiniMax Adapter 使用[官方 WebSocket T2A 接口](https://platform.minimaxi.com/docs/guides/speech-t2a-websocket)。上游返回的 MP3 分片会在服务端合并成
现有协议所需的整句音频；Stop 取消任务时会同步关闭上游连接。Azure Speech Adapter
仍可用：配置 `ODM_TTS_PROVIDER=azure`、Key、Voice 以及 Region 即可切换；若填写
`ODM_TTS_ENDPOINT` 指向完整请求 URL，则 Azure 不再需要 Region。Endpoint 对所有 TTS
Provider 含义一致，适合接代理或私有网关。

本项目不捆绑 `edge-tts`。自行增加任何 TTS 客户端或服务前，请分别复核其当前软件许可、
服务条款与数据处理要求。

**API Key 只存在于服务端**，不会出现在前端代码、打包产物或浏览器里。

内置实现均可只改配置切换：

| 替换项 | 配置 |
|---|---|
| OpenAI 兼容 LLM | `ODM_MODE=live`、`ODM_LLM_PROVIDER=openai_compatible` 及对应 URL/模型/Key |
| MiniMax TTS | `ODM_MODE=live`、`ODM_TTS_PROVIDER=minimax`、Key/Voice ID/Model，可选 Endpoint |
| Azure TTS | `ODM_MODE=live`、`ODM_TTS_PROVIDER=azure`、Key/Voice，以及 Region 或完整 Endpoint |
| 本地或 Mock 检索 | `ODM_RETRIEVER=local` 或 `mock` |
| 其他 VRM | `NEXT_PUBLIC_ODM_AVATAR_URL=/avatars/your-model.vrm`，或直接替换 `default.vrm` |

---

## 换掉知识库

`knowledge/` 就是导师的全部知识。替换该目录即可，不需要改代码。

```yaml
- id: unique-slug
  topic: 国别 / 主题
  type: decision_framework        # fact | decision_framework | checklist | redline
  title: 条目标题
  content: |
    ...
  dimensions:                     # ← 专家的判断维度
    - 沿哪个维度判断
  redlines:                       # ← 不可逾越的红线
    - 不能碰的线
  keywords: [关键词]
  source:
    title: 来源名称               # 必填。无法署名的知识不允许被引用
    url: https://...
    is_sample_data: false
```

`dimensions` 和 `redlines` 是本项目和普通 RAG demo 的分界线：
扁平切片只能让模型复述段落，把**判断维度**结构化出来，回答才是专家经验。

详见 `knowledge/README.md`。

## 换掉形象

```bash
cp your-avatar.vrm frontend/public/avatars/default.vrm
make verify-vrm    # 校验骨骼 / 表情 / 弹簧骨与渲染器兼容
```

---

## 架构

```
┌──────────────── frontend (Next.js 16 + React 19) ──────────────┐
│  useMentorSession ──┬── WebSocket (protocol v0)                 │
│                     ├── AudioQueue      按 seq 重排 + 丢弃迟到包  │
│                     └── AvatarRuntime                           │
│                           └── VrmRenderer (three 0.185 + VRM 3.x)│
│                                ├── LipSyncDriver                │
│                                └── AvatarMotionDriver  姿态/idle  │
└─────────────────────────────────────────────────────────────────┘
                          ↕ WebSocket
┌──────────────── backend (FastAPI) ─────────────────────────────┐
│  /ws → MentorPipeline                                           │
│          ├── Retriever    检索 → 低于阈值即拒答                   │
│          ├── LLMProvider  流式生成 → 分句 → 并发 TTS              │
│          └── TTSProvider                                        │
│  没有 Agent · 没有代码执行 · 没有浏览器 · 没有文件工具              │
└─────────────────────────────────────────────────────────────────┘
```

WebSocket 事件：`hello` / `turn.start` / `retrieval` / `text.delta` /
`expression` / `audio` / `turn.end` / `interrupted` / `error`。
音频按 `seq` 重排，所有事件带 `turn_id` 用于丢弃迟到包。

---

## 四个替换接口

下面是代码实际使用的签名，不是概念示意。后端三个接口定义在
`backend/app/providers/base.py`，Avatar 接口定义在 `frontend/src/avatar/types.ts`。

### Retriever

```python
class Retriever(Protocol):
    name: str
    async def search(self, query: str, k: int) -> list[ScoredChunk]: ...
    async def aclose(self) -> None: ...
```

自定义实现必须按相关度从高到低返回，并允许低分结果触发拒答：

```python
class MyRetriever:
    name = "my_retriever"

    async def search(self, query: str, k: int) -> list[ScoredChunk]:
        rows = await my_index.search(query, limit=k)
        return [ScoredChunk(chunk=row.chunk, score=row.score) for row in rows]

    async def aclose(self) -> None:
        await my_index.aclose()
```

### LLMProvider

```python
class LLMProvider(Protocol):
    name: str
    def stream(self, messages: list[Message]) -> AsyncIterator[str]: ...
    async def aclose(self) -> None: ...
```

实现必须支持任务取消；Stop 会取消包围它的 asyncio task：

```python
class MyLLM:
    name = "my_llm"

    async def stream(self, messages: list[Message]):
        async for token in my_client.stream(messages):
            yield token

    async def aclose(self) -> None:
        await my_client.aclose()
```

### TTSProvider

```python
class TTSProvider(Protocol):
    name: str
    async def synthesize(self, text: str, voice: str) -> AudioSegment: ...
    async def aclose(self) -> None: ...
```

失败时返回 `ok=False`，不能让文字回答一起失败：

```python
class MyTTS:
    name = "my_tts"

    async def synthesize(self, text: str, voice: str) -> AudioSegment:
        try:
            audio = await my_client.synthesize(text, voice)
            return AudioSegment(audio=audio, mime_type="audio/mpeg", ok=True)
        except MyProviderError:
            return AudioSegment(audio=b"", mime_type="audio/mpeg", ok=False)

    async def aclose(self) -> None:
        await my_client.aclose()
```

新增后端实现时，只需在 `backend/app/config.py` 增加配置枚举值，并在
`backend/app/providers/__init__.py` 的单一工厂中注册；检索、Prompt、协议和 UI 不改。

### AvatarRuntime

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

一个静态形象实现可以忽略音频驱动，但仍须正确完成生命周期：

```typescript
class StaticAvatar implements AvatarRuntime {
  private canvas: HTMLCanvasElement | null = null;
  private current: AvatarState = "idle";
  private listeners = new Set<(state: AvatarState) => void>();

  get state() { return this.current; }
  mount(canvas: HTMLCanvasElement) { this.canvas = canvas; }
  async load(url: string) {
    const image = new Image();
    image.src = url;
    await image.decode();
    const context = this.canvas?.getContext("2d");
    if (context && this.canvas) context.drawImage(image, 0, 0, this.canvas.width, this.canvas.height);
  }
  setState(state: AvatarState) {
    this.current = state;
    this.listeners.forEach((listener) => listener(state));
  }
  setExpression(_expression: AvatarExpression) {}
  async speak(_request: SpeakRequest) {}
  stop() {}
  dispose() { this.canvas = null; this.listeners.clear(); }
  onStateChange(listener: (state: AvatarState) => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
  getAttribution() { return null; }
}
```

在 `AvatarStage.tsx` 中把 `new VrmRenderer(...)` 换成该实现即可。若只是换另一份 VRM，
无需写代码，替换文件或设置 `NEXT_PUBLIC_ODM_AVATAR_URL` 即可。

---

## 已知限制

这一节是认真的，不是免责套话。

| 限制 | 说明 |
|---|---|
| **示例知识为合成数据** | 虚构内容，不构成任何法律、税务或投资建议 |
| **口型是近似效果** | 基于音量包络（RMS）驱动，**非音素级 viseme 同步** |
| **音频粒度是整句** | 不是流式音频切片。一句合成完才下发 |
| **边界门控是整句起止** | 不是逐词。多数 TTS 对中文只返回句级 boundary |
| **Live 引用仍受模型约束** | 检索卡片只来自已加载语料，未知编号不会变成可点击引用；但 Live LLM 输出的 `[n]` 标记目前由 Prompt 约束，尚未做语义蕴含或强制引用覆盖校验 |
| **端到端延迟** | 2026-07-26 本机 Chrome 连续 5 次实测：提交到首个 Mock 音频 345–364ms，提交到首段正文 379–387ms。真实 MiniMax 完整问答约 1.30 秒收到首段音频；短句合成约 2.38 秒返回 3.31 秒 MP3。云端结果取决于模型、声音与网络 |
| **单轮问答** | M0 无多轮记忆管理 |
| **无语音输入** | ASR 是 M1 范围 |
| **不适合直接公网部署** | 无认证、无多租户、无审计。见 `SECURITY.md` |

---

## 开发

```bash
make test          # 后端测试
make lint          # ruff + tsc
make verify-vrm    # VRM 与渲染器兼容性
make security      # 危险能力、依赖、忽略规则与资产台账
make check         # 全部
```

提交补丁前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)；维护者发布前使用
[公开发布检查表](docs/RELEASE_CHECKLIST.md)。

## 路线图

- **M0**（已完成）文字问答 · 检索引用 · 拒答 · TTS 播报 · 口型 · Stop
- **M1** 按住说话 · ASR · 流式字幕 · 分段 TTS · 用户打断 · 延迟 Trace · 口型幅度调优
- **M2** 知识摄取脚本 · 通用远端 Retriever（对接 RAG/KG）· 更多 Provider 示例 · Avatar Manifest · 英文界面/i18n

权限、多租户、知识生命周期、专家审核、报告工作流和 GraphRAG 尚未包含在当前 Starter。

## 许可

代码以 [Apache-2.0](LICENSE) 发布。版本变化见 [CHANGELOG.md](CHANGELOG.md)。

资产授权见 [ASSETS.md](ASSETS.md)，第三方代码见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)，
知识来源见 [KNOWLEDGE_SOURCES.md](KNOWLEDGE_SOURCES.md)。

内置示例形象为 CC BY-SA 授权的第三方模型，**署名与 ShareAlike 义务见 `ASSETS.md`**。
