# THIRD_PARTY_NOTICES

Open Digital Mentor 的原创代码以 Apache-2.0 发布。第三方 3D、图片与视频资产另见
`ASSETS.md`。

## 代码来源与致谢

### pixiv/ChatVRM — MIT

本项目的 VRM 渲染、音量包络口型、自动眨眼和视线行为参考了 ChatVRM 的公开设计思路，
并针对当前 `@pixiv/three-vrm` API 重新实现。为保留完整来源说明，附上其 MIT 许可声明：

```text
MIT License

Copyright (c) 2023 pixiv Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

上游：https://github.com/pixiv/ChatVRM

## 直接依赖

### 前端

| 包 | 许可 |
|---|---|
| `three` | MIT |
| `@pixiv/three-vrm` | MIT |
| `@pixiv/three-vrm-animation` | MIT |
| `next` | MIT |
| `react` / `react-dom` | MIT |
| `tailwindcss` | MIT |
| `typescript` | Apache-2.0 |
| `sharp` | Apache-2.0 |
| `tsx` | MIT |

`sharp` 在部分平台会安装基于 libvips 的可选二进制包；这些包在
`frontend/package-lock.json` 中标记为 LGPL-3.0-or-later。完整、精确到版本的前端依赖与
许可元数据以该 lockfile 为准。

### 后端

| 包 | 许可 |
|---|---|
| `fastapi` | MIT |
| `starlette` | BSD-3-Clause |
| `uvicorn` | BSD-3-Clause |
| `pydantic` / `pydantic-settings` | MIT |
| `httpx` | BSD-3-Clause |
| `websockets` | BSD-3-Clause |
| `PyYAML` | MIT |
| `python-dotenv` | BSD-3-Clause |

传递依赖的许可文本随相应软件包分发。制作二进制镜像或安装包时，发布者应重新生成依赖清单
并确认其中的许可义务。

## 外部服务

本项目不捆绑模型或语音服务。部署者自行选择的 OpenAI 兼容端点、MiniMax、Azure Speech
或其他服务受其各自服务条款和数据处理规则约束。

默认 Mock 模式不调用任何外部服务。
