# Evidence Policy

> 适用范围：全链路（Stage 2 产出，Stage 4/5/6 消费）。Evidence 是全 Skill 的「一等公民」。

## 1. 定义：事实层 vs 观点层

```text
事实层（可以写成 evidence）：发生了什么 / 谁说了什么 / 数据是多少 / 产品何时发布
观点层（禁止写成 evidence）："我认为……" / "xx 很热门" / "用户肯定需要"
```

判断标准：一条陈述能否被独立核实？能 → evidence；不能 → 观点，需要降级为 finding 的 `signals` 并标注低置信，或者丢弃。

## 2. 统一结构

所有阶段复用同一结构（见 `schemas/research-finding.yaml` 的 `evidence` 定义）：

```yaml
source:       来源名称 / URL
source_type:  news | product | community | discussion | search_trend | official_doc | analytics | social | other
date:         YYYY-MM-DD；未知填 unknown
claim:        可验证的事实陈述
confidence:   高 | 中 | 低
```

## 3. 使用要求

- 每个**重要**结论（支撑选题、评分、insight 的判断）至少 1 条 evidence。
- 无证据支撑的信号：必须在对应字段标注性或字段级别注明 `confidence: low`，且不得作为评分的高分依据。
- evidence 在 Candidate → Ranking → Top1 → Brief 全链路随选题流动（`source_signals` 保证可追溯），不允许中途丢失来源。

## 4. 置信度分级

| 级别 | 判定 |
|---|---|
| high | 官方文档 / 一手数据 / 权威媒体报道，且时间新鲜、来源具体 |
| medium | 高信誉社区讨论 / 二次转述，或来源次权威，或时间略旧 |
| low | 单一来源 / 无法核对日期 / 含推测成分；只能作为弱信号 |

## 5. 冲突处理

- Evidence 冲突：**同时保留双方**（Evidence A / Evidence B），分别保留各自 source 与 confidence，不武断选取一方当作事实；冲突本身可作为 content_gap 或选题风险记录。
- 时效冲突（旧数据 vs 新数据）：优先新近且 confidence 更高的一方，但保留旧的备查。

## 6. 禁止行为

- 为补足数量而编造来源 / 日期；
- 把观点写成事实；
- 用模型记忆冒充检索结果（同 research-policy §2）。