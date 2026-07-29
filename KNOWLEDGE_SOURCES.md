# KNOWLEDGE_SOURCES.md — 知识来源台账

`knowledge/` 下的每一条知识都必须在此登记来源与授权。
无法登记来源的知识不允许进入知识库——加载器会直接拒绝缺少 `source.title` 的条目。

---

## 当前状态：全部为合成示例数据

**⚠️ 本仓库分发的全部知识条目均为虚构内容，由本项目自撰，用于演示检索、引用与拒答链路。
它们不对应任何真实国家、政策、法律或税务规定，不构成任何形式的建议。**

| 文件 | 条目数 | 来源 | 授权 | 真实性 |
|---|---|---|---|---|
| `knowledge/sample-market-entry.yaml` | 28 | 本项目自撰 | Apache-2.0 | 合成示例数据（非真实政策） |

条目清单：

| id | 主题 | 类型 |
|---|---|---|
| `entity-freezone-vs-mainland` | 示例国别 / 主体设立 | decision_framework |
| `entity-tax-registration-window` | 示例国别 / 税务 | checklist |
| `banking-account-opening-blockers` | 示例国别 / 银行 | fact |
| `labor-localization-quota` | 示例国别 / 用工 | redline |
| `entity-branch-vs-subsidiary` | 示例国别 / 主体设立 | decision_framework |
| `entity-license-activity-match` | 示例国别 / 主体设立 | checklist |
| `entity-ownership-control` | 示例国别 / 主体设立 | decision_framework |
| `tax-vat-threshold-monitoring` | 示例国别 / 税务 | checklist |
| `tax-corporate-filing-calendar` | 示例国别 / 税务 | checklist |
| `tax-transfer-pricing-related-party` | 示例国别 / 税务 | redline |
| `banking-account-opening-pack` | 示例国别 / 银行 | checklist |
| `banking-source-of-funds` | 示例国别 / 银行 | decision_framework |
| `payments-fx-settlement` | 示例国别 / 银行 | decision_framework |
| `labor-visa-sequencing` | 示例国别 / 用工 | checklist |
| `labor-employment-contract` | 示例国别 / 用工 | checklist |
| `labor-termination-process` | 示例国别 / 用工 | redline |
| `data-residency-assessment` | 示例国别 / 数据合规 | decision_framework |
| `security-incident-response` | 示例国别 / 数据合规 | checklist |
| `product-registration-path` | 示例国别 / 产品准入 | decision_framework |
| `trade-customs-classification` | 示例国别 / 贸易与海关 | checklist |
| `trade-importer-of-record` | 示例国别 / 贸易与海关 | decision_framework |
| `channel-distributor-selection` | 示例国别 / 渠道 | decision_framework |
| `sales-government-tender` | 示例国别 / 渠道 | checklist |
| `operations-office-lease` | 示例国别 / 运营 | decision_framework |
| `operations-insurance-baseline` | 示例国别 / 运营 | checklist |
| `ip-trademark-registration` | 示例国别 / 知识产权 | checklist |
| `launch-first-ninety-days` | 示例国别 / 落地计划 | decision_framework |
| `exit-closure-checklist` | 示例国别 / 退出 | checklist |

---

## 为什么开源版用合成数据

1. **授权干净**：自撰内容，无任何第三方权利负担。
2. **规避责任**：真实的政策与税务规定会过期。一份过期的"真实"政策比明确标注的示例数据危险得多。
3. **演示效果等价**：检索、引用、溯源、拒答的链路演示，不依赖内容是否真实。
4. **保持领域中立**：Starter 只提供可再分发的数据结构和工作流，不暗示内置任何特定行业知识。

---

## 接入真实语料时的规则

如果你要用真实内容替换 `knowledge/`：

### 可以用

- 各国政府官网公开发布的文件与政策
- 世界银行、IMF、OECD 等机构的公开数据
- 自贸区、园区管理机构的官方公开材料
- 明确以 CC 协议授权的内容
- 你自己撰写或拥有完整权利的内容

### 不可以用

- 付费数据库、订阅制研报的内容
- 咨询公司报告的实质性摘录
- 客户提供的商业材料
- 未获授权的专家访谈记录
- 抓取自受版权保护网站的正文

### 每条必须登记

```yaml
source:
  title: 来源名称
  url: https://...
  retrieved_at: 2026-07-26      # 抓取日期，用于判断时效
  license: 该来源的授权说明
  is_sample_data: false          # 真实数据必须显式设为 false
```

并在本文件中新增一行登记。

### 关于时效

真实政策会变。建议：

- `retrieved_at` 超过 6 个月的条目在 UI 上标注"可能已过期"；
- 高风险类目（税率、时限、红线）设置更短的复核周期；
- 生产部署应建立与风险相匹配的专家复核和下架流程；本 Starter 不提供该运营流程。
