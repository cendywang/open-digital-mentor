# ASSETS.md — 资产授权台账

本项目分发的非代码资产必须在此登记作者、许可、来源和修改情况。没有明确来源与授权的资产
不应进入公开仓库。

## 3D 模型

### `frontend/public/avatars/default.vrm`

| 项 | 内容 |
|---|---|
| 角色 | 伏石 玲 / ブレザー（Fuseishi Rei / Blazer） |
| 版权所有者 | © 京姫鉄道合同会社 |
| 模型制作 | 佐久間蒼乃 |
| 角色设计 | 高嶋るみあ |
| 原始素材 | https://github.com/kyoki-railway/fuseishi-character-3d |
| 发行方条款 | https://www.kyoki-railway.co.jp/legal/materials/fuseishi/ |
| 许可 | **Creative Commons Attribution-ShareAlike 4.0 International（CC BY-SA 4.0）** |
| 许可正文 | https://creativecommons.org/licenses/by-sa/4.0/ |
| 本项目改动 | 纹理最长边缩至 512px；57 组 morph target 仅保留 VRM 表情绑定的 14 组；移除 morph normal 后重新打包 GLB |
| 优化脚本 | `frontend/scripts/optimize-vrm.mjs` |
| 文件大小 | 3,133,220 bytes（2.99 MiB） |
| SHA-256 | `06f8d0eb11477a453d984a95ddbe423a895d428a789bfefca245e054a5fae098` |

仓库中的文件是原模型的修改版本，并继续以 **CC BY-SA 4.0** 分发。代码的 Apache-2.0
许可不改变该模型自身的署名与 ShareAlike 条件。

建议署名：

> “伏石 玲 / ブレザー” © 京姫鉄道合同会社。模型制作：佐久間蒼乃；角色设计：高嶋るみあ。
> Open Digital Mentor contributors 对文件进行了纹理与 morph target 优化。
> CC BY-SA 4.0。

替换为自有 VRM：

```bash
cp your-avatar.vrm frontend/public/avatars/default.vrm
make verify-vrm
```

替换资产后，请同步更新本文件中的权利人、来源、许可、修改记录、大小和 SHA-256。

## 动作

**无外部动作资产。** 待机姿态、呼吸、重心摆动、眨眼和视线均由
`frontend/src/avatar/AvatarMotionDriver.ts` 程序化生成，不分发 `.vrma`、BVH 或动捕文件。

## 图片

### `frontend/src/app/icon.svg`

| 项 | 内容 |
|---|---|
| 作者 | Open Digital Mentor contributors |
| 来源 | 本项目自制 |
| 许可 | Apache-2.0 |
| 本项目改动 | 原始版本，无外部素材 |

舞台背景由 `frontend/src/app/globals.css` 中的 CSS 渐变生成，不含图片素材。

### `docs/demo-attribution.svg`

| 项 | 内容 |
|---|---|
| 作者 | Open Digital Mentor contributors |
| 来源 | 本项目自制的演示视频署名卡 |
| 许可 | Apache-2.0 |
| 用途 | 作为 `docs/demo.mp4` 末尾的可见资产署名 |

## 演示视频

### `docs/demo.mp4`

| 项 | 内容 |
|---|---|
| 作者 | Open Digital Mentor contributors |
| 来源 | 本项目在 Mock 模式下的实际录屏 |
| 内容 | 42 秒；待机、带引用回答、展开原文、Stop、域外拒答、角色资产署名卡 |
| 格式 | H.264 MP4，960×600，5 FPS，无音轨 |
| 许可 | **CC BY-SA 4.0**（画面包含上文登记的角色模型） |
| 文件大小 | 1,828,715 bytes |
| SHA-256 | `1963e84a52a452c25e7531effc3604568b94c1e3e58b131636a6ead618bc91dc` |

视频末尾包含 6 秒可见署名卡；视频单独转载时请保留该卡片。完整修改与文件校验记录仍以本
台账为准。

## 音频

仓库不包含预录音频。

- Mock 模式由 `backend/app/providers/mock.py` 在本地生成音节包络波形。
- Live 模式由部署者自行配置的 TTS 服务生成，输出不写入仓库。

## 知识语料

见 `knowledge/README.md` 与 `KNOWLEDGE_SOURCES.md`。

当前 `knowledge/` 下的内容均为本项目自撰的合成示例数据，以 Apache-2.0 分发，不对应真实
国家、政策或法律规定。
