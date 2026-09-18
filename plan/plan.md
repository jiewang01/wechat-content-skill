# Account Content Strategist — Implementation Plan

> 目标：将 `blueprint.md` 中的设计落地为一个可执行、可评估、可迭代的 Content Strategy Skill。

---

# 1. Implementation Goal

第一阶段不追求“自动写出完美文章”。

优先实现：

```text
账号定位
  ↓
Research
  ↓
Candidate Pool
  ↓
TopN
  ↓
Positioning Filter
  ↓
Top1
  ↓
Article Brief
```

即：

> **先把“选题决策”做好，再把“文章生成”接进来。**

---

# 2. Implementation Phases

```text
Phase 0
基础工程

      ↓

Phase 1
Account Profile

      ↓

Phase 2
Research

      ↓

Phase 3
Candidate + Ranking

      ↓

Phase 4
Positioning Filter

      ↓

Phase 5
Editorial Brief

      ↓

Phase 6
Evaluation

      ↓

Phase 7
Optimization
```

---

# 3. Phase 0 — Skill Skeleton

## Goal

建立最小可运行 Skill。

---

## Tasks

创建：

```text
account-content-strategist/
├── SKILL.md
├── blueprint.md
├── plan.md
├── schemas/
├── prompts/
├── policies/
└── examples/
```

---

## SKILL.md Responsibilities

`SKILL.md` 只负责：

1. Skill 目标
2. Input / Output
3. Workflow
4. 调用顺序
5. 每阶段输入输出
6. 异常处理
7. 输出格式

不要把大量评分规则和 Prompt 全部写进 `SKILL.md`。

---

## Acceptance Criteria

给定：

```text
"分享 AI Coding 实践，帮助程序员提升研发效率"
```

Skill 能够：

```text
识别账号
→
进入 Research
→
最终输出 Article Brief
```

---

# 4. Phase 1 — Account Profile

## Goal

把非结构化账号简介转换为标准 AccountProfile。

---

## Input

支持：

```text
账号简介
账号定位
账号介绍
账号历史内容
```

最低支持：

```text
一段账号简介
```

---

## Output

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

  constraints:
```

---

## Implementation

建立：

```text
schemas/account-profile.yaml
prompts/profile-parser.md
```

---

## Acceptance Criteria

至少能稳定提取：

* Audience
* Domain
* Value Proposition
* Authority
* Boundary

如果无法判断：

```text
unknown
```

而不是自行编造。

---

# 5. Phase 2 — Research Engine

## Goal

建立内容研究能力。

---

## Research Lenses

必须覆盖：

```text
Trend
Demand
Content
Gap
```

---

## Research Query Generation

根据 AccountProfile 自动生成 Research Queries：

```text
Account Domain
+
Audience Problem
+
Current Trends
+
User Questions
```

例如：

```text
AI Coding
+
developer problems
+
latest
```

以及：

```text
AI Coding
+
agent context problems
```

---

## Research Output

统一：

```yaml
research_finding:
  topic:
  signals:
  evidence:
  user_questions:
  existing_content:
  content_gap:
  candidate_angles:
```

---

## Evidence Requirements

每一个重要结论尽可能保留：

```text
source
date
claim
confidence
```

Research 与 Evidence 必须分开：

```text
Evidence = 事实依据

Finding = 对事实的归纳
```

---

## Acceptance Criteria

对一个账号至少获得：

```text
5~15 Research Findings
```

并且每个 Finding 都能够解释：

```text
为什么值得关注？
依据是什么？
用户问题是什么？
内容机会在哪里？
```

---

# 6. Phase 3 — Candidate Generation

## Goal

把 Research Findings 转换成 Candidate Topics。

---

## Target

默认：

```text
20~50 candidates
```

---

## Candidate Schema

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

## Generation Rules

Candidate 必须：

1. 对应明确用户问题
2. 有 Research Evidence
3. 可以发展成文章
4. 尽量避免重复
5. 避免只生成“新闻复述”

---

## Candidate Quality Check

增加：

```text
duplicate detection
```

避免：

```text
AI Agent Memory
AI Agent 长期记忆
Agent Memory Management
```

实际上都是同一个选题。

---

# 7. Phase 4 — Market Ranking

## Goal

从 Candidate Pool 中筛选 TopN。

---

## Score

第一版：

```text
Demand       25%
Pain         20%
Trend        15%
Novelty      15%
ContentGap   15%
Evidence     10%
```

---

## Ranking Process

```text
Candidate Pool
      ↓
Score
      ↓
Deduplicate
      ↓
Diversity Check
      ↓
TopN
```

---

## Diversity Check

不能让 TopN 全部属于同一个角度。

例如：

```text
Top 5
├── 原理类
├── 实战类
├── 避坑类
├── 方法论
└── 趋势类
```

如果五个候选只是不同标题表达同一个问题，应降低重复候选。

---

## Acceptance Criteria

输出：

```text
Top 5
```

每个都有：

```text
Market Score
Score Breakdown
Evidence
Core Problem
Content Angle
```

---

# 8. Phase 5 — Positioning Filter

## Goal

这是最终选题决策的核心阶段。

输入：

```text
AccountProfile
+
TopN
```

输出：

```text
Top1
+
Rejected Topics
```

---

## Fit Dimensions

```text
Audience Fit
Problem Fit
Authority Fit
Value Fit
Differentiation Fit
Style Fit
```

---

## Score

```text
Audience Fit        20%
Problem Fit         20%
Authority Fit       20%
Value Fit           15%
Differentiation     15%
Style Fit           10%
```

---

## Boundary Check

先执行：

```text
Boundary Risk
```

如果：

```text
HIGH
```

直接：

```text
REJECT
```

再进行评分。

---

## Selection Logic

不要：

```text
TopN 中 Fit Score 最高
```

简单结束。

需要输出：

```yaml
selection:
  topic:
  market_reason:
  account_reason:
  audience_reason:
  differentiation_reason:
  risk:
```

---

## Acceptance Criteria

最终必须回答：

> 为什么这个题适合这个账号？

并且能够说明：

> 为什么其他 TopN 没有被选中？

---

# 9. Phase 6 — Editorial Development

## Goal

把 Top1 转换成 Article Brief。

---

## Process

```text
Top1
 ↓
Reader
 ↓
Pain
 ↓
Core Insight
 ↓
Angle
 ↓
Arguments
 ↓
Outline
 ↓
Titles
```

---

# 10. Pain Point Extraction

至少检查：

```text
Functional
Efficiency
Cognitive
Risk
Emotional
```

不要求每个主题都必须有五类 Pain。

只输出有证据或有明确逻辑支持的 Pain。

---

# 11. Core Insight

必须回答：

```text
用户以为问题是什么？

真正值得讨论的问题是什么？

为什么？

有什么证据？

这个认知变化对用户有什么价值？
```

形成：

```text
Misconception
      ↓
Evidence
      ↓
Core Insight
```

---

# 12. Outline Generation

默认结构：

```text
1. Hook

2. Problem

3. Misconception

4. Core Insight

5. Mechanism

6. Solution

7. Example

8. Action
```

但允许根据主题类型切换。

---

## Topic Type → Outline

### Trend

```text
发生了什么
→
为什么重要
→
影响谁
→
真正变化
→
用户应该关注什么
```

### Tutorial

```text
问题
→
原理
→
步骤
→
案例
→
常见错误
→
实践建议
```

### Case Study

```text
背景
→
问题
→
尝试
→
失败
→
原因
→
解决
→
经验
```

### Opinion / Insight

```text
现象
→
主流认知
→
反例
→
核心判断
→
证据
→
推导
→
结论
```

---

# 13. Final Article Brief

最终输出：

```yaml
article_brief:
  topic:
  angle:

  target_reader:

  pain_points: []

  core_insight:

  key_arguments: []

  title_candidates: []

  outline: []

  evidence: []

  risks: []
```

---

# 14. Phase 7 — Evaluation

Skill 落地之后不能只通过“看起来不错”验收。

需要建立 Evaluation Dataset。

---

## Dataset

至少准备：

```text
10~20 个账号
```

覆盖不同领域：

```text
技术
职场
育儿
生活方式
教育
商业
个人品牌
```

---

# 15. Evaluation Dimensions

## 15.1 Profile Accuracy

账号定位解析是否正确？

---

## 15.2 Research Relevance

Research 是否真正围绕账号，而不是泛搜索？

---

## 15.3 Candidate Quality

候选选题是否具有：

* 用户需求
* 明确问题
* 可写性
* 差异化

---

## 15.4 Ranking Quality

TopN 是否真的来自高潜候选？

---

## 15.5 Positioning Fit

Top1 是否符合：

```text
Audience
Authority
Value
Boundary
```

---

## 15.6 Editorial Quality

最终 Article Brief 是否可以直接交给写作 Agent？

---

# 16. Recommended Evaluation Table

```text
| Dimension | Target |
|-----------|--------|
| Profile Accuracy | ≥ 90% |
| Research Relevance | ≥ 85% |
| Candidate Validity | ≥ 85% |
| TopN Quality | ≥ 80% |
| Positioning Fit | ≥ 90% |
| Brief Usability | ≥ 85% |
```

这些指标作为工程目标，而不是统计学意义上的绝对保证。

---

# 17. Phase 8 — Optimization

第一版运行后重点观察：

```text
问题 1：
Research 太泛

问题 2：
TopN 看起来热门，但不适合账号

问题 3：
Top1 与 TopN 差异不明显

问题 4：
Pain Point 太模板化

问题 5：
Outline 太像 AI 生成

问题 6：
Evidence 不足

问题 7：
标题党
```

然后分别优化对应 Module。

---

# 18. Failure Handling

## Research 不足

不要继续编造。

输出：

```text
Research Insufficient
```

并降低：

```text
Evidence Score
Confidence
```

---

## Account Positioning 不清晰

要求补充：

```text
目标用户
账号领域
内容方向
```

或者使用：

```text
inferred
```

标记推断内容。

---

## TopN 全部不适合

不要强行产生 Top1。

允许：

```text
NO_VALID_TOP1
```

并输出：

```text
需要重新 Research
```

---

## Evidence 冲突

保留：

```text
Evidence A
Evidence B
```

不要强行选择一个作为事实。

---

# 19. Phase 9 — Future Extensions

第一版稳定后，可以继续增加。

---

## 19.1 Historical Content Analysis

加入账号历史文章：

```text
历史内容
 ↓
Topic Coverage
 ↓
Content Saturation
 ↓
重复检测
 ↓
内容空白
```

最终判断：

> 这个账号过去已经写过什么？

---

## 19.2 Content Portfolio

不要只找单篇 Top1。

可以进一步：

```text
账号定位
 ↓
Topic Map
 ↓
Content Pillars
 ↓
每个 Pillar 找机会
```

形成账号长期内容规划。

---

## 19.3 Feedback Loop

文章发布之后获得：

```text
阅读
点赞
收藏
评论
转发
完读
关注转化
```

反馈：

```text
Performance
 ↓
Topic Features
 ↓
Ranking Model
```

最终形成：

> 账号自己的 Topic Intelligence。

---

## 19.4 Multi-Agent

后续可以进一步拆成：

```text
Research Agent
        ↓
Trend Agent
        ↓
Demand Agent
        ↓
Gap Agent
        ↓
Topic Agent
        ↓
Ranking Agent
        ↓
Positioning Agent
        ↓
Editorial Agent
```

但第一版不建议一开始就做成大量 Agent。

优先：

> **单 Skill + 清晰 Stage + 强 Schema + 可验证 Evidence。**

---

# 20. MVP Definition

第一版 MVP 只需要实现：

```text
① Account Profile
        ↓
② Research
        ↓
③ Candidate 20+
        ↓
④ Market Top5
        ↓
⑤ Positioning Filter
        ↓
⑥ Top1
        ↓
⑦ Pain + Insight + Outline
```

最终输出：

```text
Article Brief
```

---

# 21. MVP Acceptance Example

输入：

```text
账号简介：

“分享 AI Coding 实践，
帮助程序员提升研发效率。”
```

预期输出：

```text
Account Profile
        ↓
Research Findings
        ↓
20+ Candidate Topics
        ↓
Top 5
        ↓
Positioning Filter
        ↓
Top 1
        ↓
为什么选择
        ↓
目标用户
        ↓
核心痛点
        ↓
核心洞察
        ↓
文章角度
        ↓
标题候选
        ↓
8 段式文章大纲
```

整个链路必须可以完整跑通。

---

# 22. Implementation Priority

按照以下优先级：

```text
P0
Workflow
Schema
Account Profile
Research
TopN
Positioning Filter
Article Brief

P1
Evidence Layer
Duplicate Detection
Diversity Check
Evaluation Dataset

P2
历史内容分析
Topic Map
Content Portfolio
Performance Feedback

P3
Multi-Agent
自动学习 Ranking
长期账号策略
```

---

# 23. Final Delivery

最终 Skill 应形成：

```text
account-content-strategist/
│
├── SKILL.md
│
├── blueprint.md
├── plan.md
│
├── schemas/
│
├── prompts/
│
├── policies/
│
└── examples/
```

核心运行链路：

```text
                    ACCOUNT
                       │
                       ▼
               Profile Parser
                       │
                       ▼
                    PROFILE
                       │
                       ▼
                  Research
                       │
                       ▼
              Research Findings
                       │
                       ▼
            Candidate Generator
                       │
                       ▼
               20~50 Candidates
                       │
                       ▼
             Market Ranker
                       │
                       ▼
                    TopN
                       │
                       ▼
           Positioning Filter
                       │
                       ▼
                    Top1
                       │
                       ▼
           Editorial Development
                       │
                       ▼
                Article Brief
```

---

# 24. Definition of Done

当以下条件全部满足时，Skill 第一版完成：

* [ ] 能从自然语言账号简介生成 AccountProfile
* [ ] 能基于账号定位生成 Research Queries
* [ ] 能完成 Trend / Demand / Content / Gap Research
* [ ] Research Finding 带 Evidence
* [ ] 能生成 20+ Candidate Topics
* [ ] 能进行 Market Score
* [ ] 能输出 TopN
* [ ] 能执行 Boundary Hard Filter
* [ ] 能计算 Account Fit
* [ ] 能选择 Top1
* [ ] 能解释 Top1 的选择原因
* [ ] 能提炼 Pain Points
* [ ] 能提炼 Core Insight
* [ ] 能生成 Content Angle
* [ ] 能生成 Article Outline
* [ ] 能输出 Article Brief
* [ ] 能处理 Research Insufficient
* [ ] 能处理 NO_VALID_TOP1
* [ ] 有至少 10 个 Evaluation Cases
* [ ] 整个 Workflow 可以端到端运行

---

# 25. Final Implementation Principle

不要把这个 Skill 做成：

> **“一个会搜索和写标题的 Agent。”**

而应该做成：

> **“一个以账号定位为约束、以外部证据为基础、以内容机会发现为目标的选题决策系统。”**

最终能力边界应该非常清晰：

```text
Research
回答：
“外部世界发生了什么？”

Ranking
回答：
“哪些机会值得关注？”

Positioning Filter
回答：
“哪些机会属于这个账号？”

Editorial
回答：
“这个账号应该如何把它讲出来？”
```

这四个问题解决之后，文章写作反而只是下游能力。
