# knowledge/ — 知识库

这个目录就是数字导师的全部知识。替换它，就换掉了整个导师的领域。不需要改代码。

## ⚠️ 本目录内容为合成示例数据

**这里的每一条都是为演示链路而虚构的，不对应任何真实国家、政策、法律或税务规定，不构成任何建议。**

真实语料请自行按下述格式补充，并在 `source` 中如实登记来源与授权。

## 格式

每个 `.yaml` 文件包含一条或多条知识条目（顶层为映射或映射列表）。

```yaml
- id: unique-slug                    # 必填，全库唯一
  topic: 国别 / 主题                  # 可选，用于拒答时说明覆盖范围
  type: decision_framework           # fact | decision_framework | checklist | redline
  title: 条目标题                     # 必填，会出现在引用列表里
  content: |                         # 必填，正文
    ...
  dimensions:                        # 可选，专家的判断维度
    - 维度一
  redlines:                          # 可选，不可逾越的红线
    - 红线一
  keywords: [关键词, keyword]         # 可选，提升召回
  source:                            # 必填，且 source.title 必填
    title: 来源名称
    url: https://...
    retrieved_at: 2026-07-26
    license: 授权说明
    is_sample_data: true             # 真实语料请改为 false
```

## 为什么要有 `dimensions` 和 `redlines`

这是本项目和「又一个 RAG demo」的分界线。

扁平的文本切片只能让模型复述段落。而把专家的**判断维度**和**红线**结构化出来，
回答才能变成「你要沿这三个维度判断，其中这一条是不能碰的」——这才是专家经验，
而不是检索到的散文。

## 加载规则

- 递归读取本目录下所有 `.yaml` / `.yml`
- `id` 重复会导致启动报错
- **缺少 `source.title` 会导致该条目加载失败**：无法署名的知识不能被引用，
  与其渲染一个指向空气的角标，不如拒绝加载
- 加载失败时服务不会崩溃，会退回 MockRetriever 并在日志中报错

## 默认启用与替换

仓库默认使用本目录的 28 条合成知识；LLM 与 TTS 仍是完全离线的 Mock。
如需切回 3 条内置烟雾测试数据，可设 `ODM_RETRIEVER=mock`。

```bash
# .env
ODM_RETRIEVER=local
ODM_KNOWLEDGE_DIR=knowledge
```
