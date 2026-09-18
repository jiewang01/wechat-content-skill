# Account Content Strategist — Design Blueprint

> 从「账号简介 / 定位」出发，通过 Research → TopN → 账号定位过滤 → Top1 → 主题策划，生成可直接进入文章创作流程的 Article Brief。

---

## 1. Overview

### 1.1 Skill Name

`account-content-strategist`

### 1.2 Purpose

该 Skill 用于解决：

> 给定一个账号简介或账号定位，如何结合当前外部内容环境，找到**值得写、适合这个账号写、并且能够形成具体文章**的主题。

核心原则：

```text
不是：
热门话题 → 写文章

而是：
账号定位
    ↓
研究外部内容环境
    ↓
发现内容机会
    ↓
筛选高潜选题 TopN
    ↓
通过账号定位进行二次过滤
    ↓
确定 Top1
    ↓
提炼痛点与核心洞察
    ↓
生成文章大纲
```

---

# 2. Core Design Principles

## 2.1 Market Potential ≠ Account Fit

这是整个 Skill 最重要的设计原则。

一个选题可能：

* 市场热度很高
* 用户需求很强
* 内容传播潜力很好

但不一定适合当前账号。

因此必须拆成两个阶段：

```text
Market Potential
    ↓
TopN

Account Fit
    ↓
Top1
```

不要把账号适配度直接混入第一阶段的排名。

---

## 2.2 Research First, Generate Later

所有选题首先应该来源于 Research，而不是直接由 LLM 凭空生成。

```text
Research Evidence
        ↓
Research Finding
        ↓
Candidate Topic
        ↓
Ranking
```

避免：

* 凭经验猜热点
* 编造用户需求
* 把模型知识当成实时趋势
* 没有依据地判断“最近很火”

---

## 2.3 Candidate ≠ Title

Candidate Topic 是一个内容机会对象，而不是一个标题。

例如：

```yaml
core_topic: "AI Coding 中的 Context Engineering"
user_problem: "Agent 运行时间越长，输出质量越差"
content_angle: "问题可能不是模型能力，而是上下文管理"
```

最终标题应该在 Top1 确定之后再生成。

---

## 2.4 Boundary Is a Hard Filter

账号定位除了描述“应该做什么”，还必须描述“不应该做什么”。

例如：

```yaml
authority:
  strengths:
    - AI Coding
    - Agent
    - 工程实践

boundaries:
  - 泛 AI 新闻评论
  - 与研发无关的社会热点
```

如果候选主题存在明显 Boundary Risk：

```text
Boundary Risk = HIGH
        ↓
REJECT
```

而不是简单通过降低分数处理。

---

# 3. End-to-End Workflow

```text
┌──────────────────────────┐
│ Account Profile          │
│ 账号简介 / 定位           │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│ ① Positioning Analysis   │
│ 解析账号定位              │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│ ② Research               │
│ Trend / Demand / Content │
│ Gap / Evidence           │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│ ③ Candidate Generation   │
│ 20~50 个候选选题           │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│ ④ Market Ranking         │
│ 市场潜力评分              │
└────────────┬─────────────┘
             ↓
           TopN
             ↓
┌──────────────────────────┐
│ ⑤ Positioning Filter     │
│ 账号适配度过滤             │
└────────────┬─────────────┘
             ↓
           Top1
             ↓
┌──────────────────────────┐
│ ⑥ Topic Development      │
│ Topic / Pain / Insight   │
│ Angle / Outline           │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│ Article Brief             │
└──────────────────────────┘
```

---

# 4. Stage 1 — Positioning Analysis

## 4.1 Input

可以接受：

```text
账号简介
账号主页介绍
账号历史文章
用户提供的账号定位
```

最小输入：

```text
"分享 AI Coding 实践，帮助程序员提升研发效率"
```

---

## 4.2 AccountProfile

统一转换成：

```yaml
account_profile:
  description:

  audience:
    primary:
    secondary: []

  domain: []

  value_proposition: []

  content_style:
    tone:
    format: []

  authority:
    strengths: []
    limitations: []

  boundaries: []

  platform:
  content_constraints:
```

---

## 4.3 Positioning Dimensions

账号定位至少解析五个维度：

### WHO

谁是目标用户？

### WHY

用户为什么关注？

### WHAT

账号解决什么问题？

### HOW

通过什么内容形式解决？

### BOUNDARY

什么内容不应该做？

---

# 5. Stage 2 — Research

Research 分为四个 Lens。

```text
Research
├── Trend Research
├── Demand Research
├── Content Research
└── Gap Research
```

---

## 5.1 Trend Research

回答：

> 最近发生了什么？

关注：

* 新产品
* 新技术
* 新事件
* 新趋势
* 新观点
* 行业变化

---

## 5.2 Demand Research

回答：

> 用户正在关心什么？

关注：

* 用户问题
* 搜索需求
* 社区讨论
* 评论区问题
* FAQ
* 实际使用障碍

---

## 5.3 Content Research

回答：

> 别人正在写什么？

分析：

* 热门内容
* 高互动内容
* 高频主题
* 标题模式
* 内容饱和度
* 主流观点

---

## 5.4 Gap Research

回答：

> 哪些问题已经有需求，但还没有被很好地解释？

重点寻找：

```text
高需求
+
存在讨论
+
内容存在明显缺口
```

例如：

```text
已有大量内容：
Context Window 是什么

潜在 Gap：
为什么 Agent 运行时间越长效果越差？
工程上应该如何治理上下文？
```

---

# 6. Research Evidence

所有重要 Research Finding 应尽可能保留 Evidence。

```yaml
evidence:
  source:
  source_type:
  date:
  claim:
  confidence:
```

例如：

```yaml
evidence:
  source: "GitHub"
  source_type: "discussion"
  date: "2026-09-15"
  claim: "Users report quality degradation as agent context grows"
  confidence: high
```

Evidence 是：

```text
事实层
```

而不是：

```text
观点层
```

---

# 7. ResearchFinding

Research 的标准中间产物：

```yaml
research_finding:
  topic:

  signals:
    trend:
    demand:
    discussion:

  evidence: []

  user_questions: []

  existing_content:
    saturation:

  content_gap:

  candidate_angles: []
```

---

# 8. Stage 3 — Candidate Generation

Research 完成之后生成较大的 Candidate Pool。

推荐：

```text
20~50 candidates
```

Candidate 至少包含：

```yaml
candidate:
  core_topic:
  user_problem:
  target_audience:
  content_angle:
  evidence:
  source_signals:
```

---

# 9. Stage 4 — Market Ranking

这一阶段只判断：

> **这个选题本身值不值得做？**

不判断：

> **这个账号是否应该做？**

---

## 9.1 Market Score

初版评分模型：

```text
Market Score
=
Demand       × 25%
+
Pain         × 20%
+
Trend        × 15%
+
Novelty      × 15%
+
ContentGap   × 15%
+
Evidence     × 10%
```

所有维度：

```text
0 ~ 100
```

---

## 9.2 Dimension Definition

### Demand

用户是否明确存在需求？

### Pain

问题是否足够真实、具体、有损失？

### Trend

当前关注度是否上升？

### Novelty

是否存在新的切入角度？

### ContentGap

现有内容是否存在明显缺口？

### Evidence

是否有足够可靠的 Research Evidence？

---

# 10. TopN Output

默认：

```text
Top 5
```

可配置：

```yaml
top_n: 5
```

输出：

```yaml
rank:
topic:
market_score:
score_breakdown:
  demand:
  pain:
  trend:
  novelty:
  content_gap:
  evidence:
evidence: []
```

---

# 11. Stage 5 — Positioning Filter

TopN 进入账号定位过滤。

---

## 11.1 Fit Dimensions

```text
Positioning Fit
├── Audience Fit
├── Problem Fit
├── Authority Fit
├── Value Fit
├── Differentiation Fit
└── Style Fit
```

---

## 11.2 Account Fit Score

初版：

```text
Account Fit
=
Audience Fit        × 20%
+
Problem Fit         × 20%
+
Authority Fit       × 20%
+
Value Fit           × 15%
+
Differentiation     × 15%
+
Style Fit           × 10%
```

---

## 11.3 Boundary Risk

单独处理：

```text
Boundary Risk
├── LOW
├── MEDIUM
└── HIGH
```

规则：

```text
HIGH
 ↓
REJECT
```

---

# 12. Top1 Selection

Top1 不仅输出主题，还要解释选择依据。

```yaml
selected_topic:
  topic:

  why_selected:
    market_reason:
    audience_reason:
    account_reason:
    differentiation_reason:

  risks: []

  confidence:
```

这里的 `why_selected` 非常重要。

它回答：

> 为什么这个主题最终从 TopN 中脱颖而出？

---

# 13. Stage 6 — Topic Development

Top1 进入文章策划。

```text
Top1
 ↓
Topic Definition
 ↓
Pain Point
 ↓
Core Insight
 ↓
Content Angle
 ↓
Outline
 ↓
Title Candidates
```

---

# 14. Pain Point Model

Pain 不应该只是：

> 用户不知道某个知识点。

建议拆成：

```text
Pain
├── Functional Pain
├── Efficiency Pain
├── Cognitive Pain
├── Risk Pain
└── Emotional Pain
```

---

## 14.1 Functional Pain

做不到。

例如：

> Agent 无法稳定完成复杂任务。

---

## 14.2 Efficiency Pain

太慢、太复杂、重复劳动。

---

## 14.3 Cognitive Pain

不知道为什么失败。

---

## 14.4 Risk Pain

担心：

* 出错
* 返工
* 数据损失
* 不可控

---

## 14.5 Emotional Pain

例如：

* 焦虑
* 挫败
* 不确定
* “是不是我不会用？”

---

# 15. Article Outline Framework

默认采用问题驱动型结构：

```text
1. Hook
   用户正在经历什么？

2. Problem
   为什么这个问题值得关注？

3. Misconception
   大多数人认为原因是什么？

4. Core Insight
   真正的问题是什么？

5. Mechanism
   为什么会发生？

6. Solution
   怎么解决？

7. Example
   具体案例

8. Action
   用户接下来可以做什么？
```

最终形成：

```text
用户痛点
 ↓
反常识认知
 ↓
核心观点
 ↓
原理解释
 ↓
解决方案
 ↓
案例
 ↓
行动建议
```

---

# 16. Final Output — Article Brief

最终不直接写文章，而是生成：

```yaml
article_brief:

  account:
    positioning:
    audience:
    value_proposition:

  selected_topic:
    topic:
    angle:

  reader:
    target_reader:

  pain_points:
    functional:
    efficiency:
    cognitive:
    risk:
    emotional:

  core_insight:

  key_arguments: []

  title_candidates: []

  outline:
    - section:
      purpose:
      key_points: []

  evidence: []

  risks: []
```

Article Brief 可以作为下游 Writing Skill 的输入。

---

# 17. Skill Architecture

不建议实现为一个巨型 Prompt。

建议：

```text
                    Skill
                      │
          ┌───────────┴───────────┐
          │       Orchestrator     │
          └───────────┬───────────┘
                      │
       ┌──────────────┼──────────────┐
       ↓              ↓              ↓
 Profile Parser   Research Agent   Topic Generator
                                      │
                                      ↓
                               Ranking Agent
                                      │
                                      ↓
                                Fit Filter
                                      │
                                      ↓
                              Editorial Agent
```

---

# 18. Module Responsibilities

## Profile Parser

输入：

```text
账号简介 / 定位
```

输出：

```text
AccountProfile
```

---

## Research Agent

负责：

```text
Trend
Demand
Content
Gap
Evidence
```

输出：

```text
ResearchFinding[]
```

---

## Topic Generator

负责：

```text
ResearchFinding
 ↓
Candidate[]
```

---

## Ranking Agent

负责：

```text
Candidate[]
 ↓
Market Score
 ↓
TopN
```

---

## Fit Filter

负责：

```text
TopN
+
AccountProfile
 ↓
Account Fit
 ↓
Top1
```

---

## Editorial Agent

负责：

```text
Top1
 ↓
Pain
 ↓
Insight
 ↓
Angle
 ↓
Outline
 ↓
Article Brief
```

---

# 19. Recommended Repository Structure

```text
account-content-strategist/
│
├── SKILL.md
│
├── blueprint.md
├── plan.md
│
├── schemas/
│   ├── account-profile.yaml
│   ├── research-finding.yaml
│   ├── candidate-topic.yaml
│   ├── ranking-result.yaml
│   └── article-brief.yaml
│
├── prompts/
│   ├── profile-parser.md
│   ├── research.md
│   ├── topic-generator.md
│   ├── ranking.md
│   ├── positioning-filter.md
│   └── editorial.md
│
├── policies/
│   ├── research-policy.md
│   ├── evidence-policy.md
│   └── scoring-policy.md
│
└── examples/
    ├── ai-coding.yaml
    ├── parenting.yaml
    └── lifestyle.yaml
```

---

# 20. Key Design Decisions

### Decision 1

**Research 与 Ranking 分离。**

Research 提供事实和信号，Ranking 进行决策。

### Decision 2

**Market Score 与 Account Fit 分离。**

避免“因为适合账号，所以人为提高市场排名”。

### Decision 3

**Boundary Risk 是 Hard Filter。**

账号不应该做的内容，不因为热度高而进入最终候选。

### Decision 4

**Topic 与 Title 分离。**

先确定内容机会，再生成标题。

### Decision 5

**Evidence 一等公民。**

Research 产生的关键判断应该尽可能可以追溯。

### Decision 6

**最终输出 Article Brief，而不是直接写文章。**

让本 Skill 与后续 Writing Skill 解耦。

---

# 21. Core Formula

整个 Skill 可以抽象为：

```text
Account Positioning
        +
External Research
        ↓
Content Opportunities
        ↓
Market Potential
        ↓
TopN
        ↓
Account Positioning Filter
        ↓
Top1
        ↓
Editorial Development
        ↓
Article Brief
```

核心理念：

> **先证明“这个题值得写”，再证明“这个账号应该写”，最后解决“应该怎么写”。**

