# 广告任务自动分析 Skill

## Implementation Plan v0.1

> 本文基于 `BLUEPRINT.md` 制定，用于指导 Skill 的分阶段实现、验收与后续演进。
>
> 核心原则：
>
> **先建立可信的数据与决策基础，再扩展生产自动化，最后形成数据闭环。**
>
> 不以“自动化程度”作为第一阶段目标，而以“决策是否可靠、可解释、可验证”作为第一阶段目标。

---

# 1. Overall Roadmap

整体分为五个阶段：

```text
Phase 0
基础设施与数据契约
        ↓
Phase 1
广告任务分析 MVP
        ↓
Phase 2
运营决策 Copilot
        ↓
Phase 3
内容生产 Copilot
        ↓
Phase 4
发布与数据复盘闭环
        ↓
Phase 5
自适应运营 Agent
```

对应能力演进：

```text
Data Contract
      ↓
Understand
      ↓
Evaluate
      ↓
Decide
      ↓
Produce
      ↓
Publish
      ↓
Learn
      ↓
Adapt
```

---

# 2. Phase 0 — Foundation

## 目标

建立整个 Skill 的基础数据契约和运行骨架。

这一阶段：

> **不追求自动抓取，不追求自动接单，不追求 AI 写稿。**

只解决一个问题：

> **未来所有 Agent 到底围绕什么数据工作？**

---

## 2.1 核心任务

### P0-01：建立 Repository

```text
newbang-ad-skill/
│
├── SKILL.md
├── blueprint.md
├── plan.md
│
├── schemas/
├── agents/
├── tools/
├── knowledge/
├── templates/
└── tests/
```

---

### P0-02：实现四个 Core Schema

必须落地：

```text
schemas/
├── ad-task.schema.json
├── account-profile.schema.json
├── evidence.schema.json
└── decision.schema.json
```

对应：

```text
AdTask
AccountProfile
Evidence
Decision
```

---

### P0-03：建立 ID 规则

统一：

```text
TASK-*
ACCOUNT-*
EVD-*
DEC-*
```

例如：

```text
TASK-NB-20260918-001
ACCOUNT-XHS-001
EVD-20260918-0001
DEC-20260918-0001
```

---

### P0-04：建立 Evidence 引用机制

所有分析结果必须能够回溯：

```text
Decision
    ↓
Reason
    ↓
Evidence
    ↓
Source
```

---

### P0-05：建立 Confidence 规范

统一：

```text
0.00 - 0.39  low
0.40 - 0.69  medium
0.70 - 0.89  high
0.90 - 1.00  very_high
```

并明确：

```text
Evidence Reliability
≠
Decision Confidence
```

---

## 2.2 P0 暂不做

```text
❌ 自动抓取新榜
❌ 自动接单
❌ 自动发布
❌ 自动写广告
❌ 机器学习
❌ 自动调整评分权重
```

---

## 2.3 Phase 0 验收标准

### Schema

四个 Schema 均能够：

```text
Create
Validate
Serialize
Deserialize
```

### Evidence

任意 Decision 都能回答：

```text
这个结论是什么？
为什么？
依据是什么？
依据来自哪里？
确定程度是多少？
```

### Contract

Agent 不允许直接输出：

```text
「建议接」
```

而必须输出符合 `Decision` Schema 的结构化对象。

---

# 3. Phase 1 — AdTask Analyzer MVP

## 目标

先让 Skill **真正看懂一个广告任务**。

输入：

```text
新榜广告任务原始内容
```

输出：

```text
AdTask
+
Evidence
+
初步 Analysis
```

---

# 3.1 Task Collector

第一版允许人工提供任务：

```text
复制新榜任务
        ↓
Task Collector
        ↓
Raw Task
```

这样可以绕过抓取问题，快速验证核心模型。

---

# 3.2 Task Parser

实现：

```text
Raw Task
    ↓
Task Parser
    ↓
AdTask
```

提取：

```text
品牌
产品
品类
广告目标
目标人群
内容形式
报价
交付要求
截止时间
审核要求
修改规则
风险要求
```

---

# 3.3 Requirement Normalizer

把自然语言要求转成：

```text
Mandatory
Optional
Forbidden
Unknown
```

例如：

```yaml
requirements:
  mandatory:
    - 产品露出
    - 指定卖点

  optional:
    - 真人出镜

  forbidden:
    - 竞品比较

  unknown:
    - 修改次数
```

---

# 3.4 Evidence Extraction

原始任务中的事实全部转换成：

```text
Evidence
```

例如：

```text
EVD-001
type: task_fact
content: 广告预算 800 元
reliability: 0.98
```

---

# 3.5 Phase 1 输出

最终形成：

```text
Raw Task
     ↓
AdTask
     ↓
Evidence[]
```

---

# 3.6 Phase 1 验收

准备至少：

```text
20 个真实广告任务
```

测试：

* 字段提取完整率
* 金额提取准确率
* 截止时间识别准确率
* 必选/禁用要求识别准确率
* Unknown 识别能力

重点测试：

> **不能把“没写”当成“没有”。**

---

# 4. Phase 2 — Decision Copilot

这是整个项目第一个真正产生运营价值的阶段。

## 目标

回答：

> **这个广告到底值不值得接？**

输入：

```text
AdTask
+
AccountProfile
+
Evidence
```

输出：

```text
Decision
```

---

# 4.1 AccountProfile MVP

第一版不追求自动构建账号画像。

允许人工配置：

```yaml
account:
  category:
  followers:

audience:
  tags:

content:
  niches:
  preferred_topics:
  forbidden_topics:

performance:
  avg_views:
  median_views:
  engagement_rate:

commercial:
  historical_revenue:
  historical_cpm:

production:
  avg_production_hours:
  ai_generation_capability:
```

---

# 4.2 Account Fit Analyzer

计算：

```text
Audience Fit
Content Fit
Brand Fit
Historical Fit
Production Fit
```

最终形成：

```text
Account Fit
```

但必须附带：

```text
Evidence
+
Confidence
```

---

# 4.3 Economics Analyzer

建立最基础的经济模型：

```text
Expected Income
-
Production Cost
-
Opportunity Cost
=
Expected Net Value
```

生产成本：

```text
Content Planning
+
Writing
+
Material
+
Shooting
+
Editing
+
Review
+
Revision
```

第一版可以全部使用人工输入或历史均值。

---

# 4.4 Risk Analyzer

至少识别：

```text
Platform Risk
Brand Risk
Claim Risk
Copyright Risk
Account Reputation Risk
```

---

# 4.5 Hard Constraint Engine

先于评分执行：

```text
Hard Constraints
        ↓
    ┌───┴───┐
   Fail    Pass
    ↓       ↓
 Reject   Scoring
```

例如：

```text
账号明确拒绝该品类
        ↓
      REJECT
```

不能因为“广告费很高”又把它算回来。

---

# 4.6 Decision Engine

形成：

```text
Revenue
Account Fit
Production Cost
Opportunity Cost
Risk
        ↓
Decision Engine
        ↓
ACCEPT
OBSERVE
REJECT
NEED_INFORMATION
```

---

# 4.7 Decision Explanation

每次决策必须输出：

```text
Decision
Score
Confidence
Reasons
Blockers
Next Actions
Evidence
```

示例：

```text
建议：ACCEPT

决策指标：82
置信度：0.84

主要依据：
1. 目标人群与账号高度匹配
2. 历史同类广告表现稳定
3. 预计生产成本较低

主要不确定性：
1. 品牌修改次数未知

下一步：
确认品牌审核规则
```

---

# 4.8 Phase 2 验收

建立：

```text
50 个历史广告任务
```

让系统进行：

```text
Blind Decision Test
```

即：

```text
历史任务
   ↓
Skill 独立判断
   ↓
与实际运营结果比较
```

重点不是追求：

```text
Score Accuracy = 100%
```

而是验证：

```text
Evidence 是否充分
Decision 是否可解释
Confidence 是否合理
错误是否能够定位
```

---

# 5. Phase 3 — Content Copilot

## 目标

解决：

> **既然值得接，那么接下来应该怎么做？**

流程：

```text
Decision = ACCEPT
        ↓
Campaign Brief
        ↓
Content Strategy
        ↓
Draft
        ↓
Self Review
        ↓
Human Review
```

---

# 5.1 Brief Generator

输入：

```text
AdTask
AccountProfile
Decision
```

输出：

```text
CampaignBrief
```

包含：

```text
Campaign Objective
Target Audience
Product USP
Mandatory Claims
Forbidden Claims
Content Angle
Hook
Storyline
CTA
Platform Style
Account Style
Risk Checklist
```

---

# 5.2 Content Strategy

不要让 AI 直接写广告。

先生成：

```text
3 个候选内容方向
```

例如：

```text
Angle A
Angle B
Angle C
```

然后根据：

```text
Account Fit
Historical Performance
Production Cost
Brand Requirements
```

选择生产方向。

---

# 5.3 Draft Generator

生成：

```text
标题
正文
图片建议
视频脚本
口播
CTA
```

具体能力根据平台逐步增加。

---

# 5.4 Self Review

AI 初稿必须进行二次检查：

```text
Requirement Check
Claim Check
Platform Check
Brand Check
Account Style Check
```

输出：

```text
PASS
WARN
FAIL
```

---

# 5.5 Human Review

这一阶段：

> **必须保留人工审核。**

人工是：

```text
最终发布 Gate
```

而不是可选步骤。

---

# 5.6 Phase 3 验收

至少选择：

```text
10 个真实广告任务
```

测试：

* Brief 可执行性
* AI 初稿修改量
* 平均人工修改时间
* 品牌要求遗漏率
* 风险检测召回率

核心指标：

```text
Human Editing Time
```

而不是“AI 写得像不像”。

---

# 6. Phase 4 — Publish & Feedback Loop

## 目标

从：

```text
Decision → Content
```

进一步形成：

```text
Decision
→ Content
→ Publish
→ Performance
→ Postmortem
```

---

# 6.1 Publish Record

每一次广告发布必须记录：

```text
Task ID
Account ID
Content ID
Publish Time
Actual Production Hours
Revision Count
Actual Revenue
```

---

# 6.2 Performance Record

至少采集：

```text
Views
Likes
Comments
Saves
Shares
Clicks
Conversion
Revenue
```

根据平台实际可获取数据逐步扩展。

---

# 6.3 Prediction vs Actual

系统必须记录：

```text
Prediction
        VS
Actual
```

例如：

```text
Metric             Prediction    Actual
Views                 12k         18k
Production Hours       3h          4.5h
Revision Count          1           3
Engagement Rate       5.2%         7.1%
```

---

# 6.4 Postmortem Agent

自动生成：

```text
What Worked
What Failed
Prediction Error
Production Error
Content Error
Commercial Error
Next Recommendation
```

注意：

这里的“Recommendation”是：

> 对下一次任务参数的调整建议，

而不是简单给当前任务打分。

---

# 6.5 Model Update

允许更新：

```text
AccountProfile
Cost Model
Historical Performance
Decision Evidence
```

例如：

```text
Historical Estimate:
3h

Actual:
4.5h

Updated Estimate:
4.1h
```

---

# 6.6 Phase 4 验收

累计：

```text
30+ 个已完成广告任务
```

能够回答：

```text
过去预测准不准？

哪些品类最适合账号？

哪些广告生产成本经常被低估？

哪些品牌修改次数最多？

哪些内容方向表现最好？

哪些决策容易出错？
```

---

# 7. Phase 5 — Adaptive Advertising Agent

这是最终形态。

## 目标

从：

```text
固定规则
```

演进为：

```text
基于历史结果持续优化
```

---

# 7.1 Adaptive AccountProfile

AccountProfile 不再完全人工维护：

```text
AccountProfile
       ↑
       │
Performance
       │
Postmortem
       │
Historical Campaigns
```

形成动态账号画像。

---

# 7.2 Adaptive Cost Model

系统自动学习：

```text
Task Type
+
Content Format
+
Brand
+
Revision Pattern
+
Production Method
```

对生产成本进行预测。

---

# 7.3 Adaptive Decision Model

根据历史结果持续验证：

```text
Predicted Value
        VS
Actual Value
```

分析：

```text
False Positive
False Negative
```

例如：

```text
预测 ACCEPT
实际表现差
        ↓
Decision Error
        ↓
寻找原因
        ↓
更新模型
```

---

# 7.4 Decision Debugging

这是 Phase 5 非常重要的能力。

任何一次失败决策，都能够回放：

```text
Task
 ↓
Evidence
 ↓
Analysis
 ↓
Score
 ↓
Decision
 ↓
Actual Result
```

最终回答：

> **当时为什么做出这个判断？如果重新判断，哪些证据会改变结果？**

---

# 8. Phase Gates

每个 Phase 必须满足 Exit Criteria 才进入下一阶段。

```text
Phase 0
  │
  │ Schema Stable
  ▼
Phase 1
  │
  │ Task Parsing Reliable
  ▼
Phase 2
  │
  │ Decision Explainable
  ▼
Phase 3
  │
  │ Human Editing Cost Reduced
  ▼
Phase 4
  │
  │ Feedback Loop Closed
  ▼
Phase 5
  │
  │ Adaptive Model
  ▼
Continuous Evolution
```

---

# 9. Priority Matrix

| 能力                        | Phase | 优先级 |
| ------------------------- | ----- | --- |
| AdTask Schema             | P0    | P0  |
| AccountProfile Schema     | P0    | P0  |
| Evidence Schema           | P0    | P0  |
| Decision Schema           | P0    | P0  |
| Task Parser               | P1    | P0  |
| Evidence Extraction       | P1    | P0  |
| Account Fit               | P2    | P0  |
| Economics                 | P2    | P0  |
| Hard Constraint           | P2    | P0  |
| Decision Engine           | P2    | P0  |
| Brief Generator           | P3    | P1  |
| AI Draft                  | P3    | P1  |
| AI Self Review            | P3    | P1  |
| Human Review              | P3    | P0  |
| Publish Record            | P4    | P1  |
| Performance Analysis      | P4    | P0  |
| Postmortem                | P4    | P0  |
| Model Update              | P4    | P1  |
| Adaptive Decision         | P5    | P2  |
| Automatic Task Collection | P5    | P1  |
| Automatic Publishing      | P5    | P2  |

---

# 10. What NOT to Build First

项目初期明确禁止被以下方向带偏：

```text
❌ 先做复杂 Web UI
❌ 先做自动发布
❌ 先做自动接单
❌ 先做复杂机器学习
❌ 先做复杂评分公式
❌ 先做几十个平台适配
❌ 先做多 Agent 编排
```

正确顺序：

```text
Data Contract
        ↓
Decision Quality
        ↓
Production Efficiency
        ↓
Feedback
        ↓
Automation
```

---

# 11. MVP Definition

真正意义上的 MVP 不是：

> “能够自动从新榜抓任务并自动发布广告。”

而是：

> **输入一个广告任务 + 一个账号画像，Skill 能够基于可追溯 Evidence 给出结构化、可解释、带 Confidence 的运营决策。**

因此 MVP：

```text
Input
├── AdTask
└── AccountProfile

Processing
├── Evidence Extraction
├── Account Fit
├── Economics
├── Risk
└── Decision Engine

Output
└── Decision
    ├── Action
    ├── Score
    ├── Confidence
    ├── Reasons
    ├── Blockers
    └── Evidence
```

---

# 12. MVP Demo

理想的第一版 Demo：

```text
用户：

帮我分析这个新榜广告任务。

        ↓

Skill

[Task]
品牌：XXX
产品：XXX
报价：¥800
截止：9月20日
要求：……

        ↓

[Account]
账号：XXX
粉丝：XXX
核心人群：……
历史平均阅读：……

        ↓

[Evidence]
EVD-001
EVD-002
EVD-003
……

        ↓

[Analysis]

收益：¥800
预计生产成本：¥180
账号匹配：高
机会成本：中
风险：低

        ↓

[Decision]

ACCEPT

决策指标：82
置信度：0.84

主要原因：
……

主要不确定性：
……

下一步：
……
```

这个 Demo 跑通以后，再进入内容生产。

---

# 13. Testing Strategy

测试不只测试代码。

需要建立四层测试。

## 13.1 Schema Test

验证：

```text
Valid
Invalid
Missing
Null
Boundary
```

---

## 13.2 Extraction Test

验证：

```text
Raw Task
→
AdTask
```

---

## 13.3 Decision Test

验证：

```text
AdTask
+
AccountProfile
+
Evidence
→
Decision
```

重点：

```text
Reason 必须有 Evidence
Decision 必须有 Confidence
Unknown 不能被误判为 Fact
Hard Constraint 必须优先
```

---

## 13.4 Regression Test

以后任何 Prompt、Agent、Model 修改，都必须跑历史 Case：

```text
Historical Cases
       ↓
New Version
       ↓
Compare
       ↓
Regression Detection
```

避免：

> “为了修一个任务，把过去 20 个任务的判断全部改坏。”

---

# 14. Evaluation Dataset

从 Phase 1 开始建立：

```text
tests/
└── cases/
    ├── task-001.json
    ├── task-002.json
    ├── task-003.json
    └── ...
```

每个 Case 包含：

```text
Raw Task
Expected AdTask
Expected Evidence
AccountProfile
Expected Decision
Actual Outcome
```

最终形成：

> **Advertising Decision Benchmark**

这是后续 Skill 能否持续演进的关键资产。

---

# 15. Observability

每次运行必须记录：

```text
Run ID
Task ID
Account ID

Input Version
Prompt Version
Agent Version
Schema Version

Evidence Count
Decision
Confidence

Execution Time
Tool Calls
Human Changes

Final Result
```

这样才能进行：

```text
Decision Debugging
Prompt Regression
Agent Regression
Cost Analysis
```

---

# 16. Version Strategy

所有核心模块独立版本：

```text
Blueprint v0.1

Schema
  AdTask v1
  AccountProfile v1
  Evidence v1
  Decision v1

Agent
  TaskAnalyzer v0.1
  DecisionEngine v0.1

Prompt
  TaskParser v0.1
  DecisionPrompt v0.1
```

禁止：

```text
修改 Prompt
→
没有版本记录
```

---

# 17. Suggested Milestones

## M0 — Contract Freeze

完成：

```text
blueprint.md
4 Core Schemas
ID Strategy
Evidence / Confidence Rules
```

---

## M1 — Task Understanding

完成：

```text
Raw Task
→
AdTask
→
Evidence
```

---

## M2 — Decision MVP

完成：

```text
AdTask
+
AccountProfile
+
Evidence
→
Decision
```

---

## M3 — Content Copilot

完成：

```text
Decision
→
Brief
→
Draft
→
Human Review
```

---

## M4 — Closed Loop

完成：

```text
Publish
→
Performance
→
Postmortem
→
Model Update
```

---

## M5 — Adaptive Agent

完成：

```text
Historical Data
→
Adaptive Model
→
Decision Optimization
```

---

# 18. Final Architecture Evolution

最终系统从：

```text
                    v0
                 数据模型
                    │
                    ▼
                    v1
               决策 Copilot
                    │
                    ▼
                    v2
               内容 Copilot
                    │
                    ▼
                    v3
                数据闭环
                    │
                    ▼
                    v4
              Adaptive Agent
```

逐步演进。

而不是一开始就构建：

```text
全自动广告 Agent
```

---

# 19. Implementation Log

## 2026-09-18 — Phase 0 + Phase 1 基础落地

已完成：

```text
- BLUEPRINT.md（原 BULEPRINT.md，已重命名）
- schemas/
  ├── ad-task.schema.json          (AdTask@v1)
  ├── account-profile.schema.json  (AccountProfile@v1)
  ├── evidence.schema.json         (Evidence@v1)
  └── decision.schema.json         (Decision@v1，reasons[].evidence_refs 与 confidence.evidence_refs 设为必填)
- knowledge/
  ├── id-rules.md                  (TASK-*/ACCOUNT-*/EVD-*/DEC-*)
  ├── evidence-rules.md            (追溯链、type、reliability 给分、Rule 05)
  ├── confidence-rules.md          (Reliability ≠ Confidence、四档分级)
  ├── task-parser-rules.md         (Phase 1：抽取字段清单、金额/时间、缺失处理)
  └── requirement-normalizer-rules.md (Phase 1：mandatory/optional/forbidden/unknown)
- tests/cases/task-001.example.json (演示/校验用虚构示例)
```

待办：

- [ ] M1 验收：20 个真实广告任务测试集
- [ ] M2：Decision Engine 规则细化（Account Fit / Economics / Risk / Hard Constraint / 权重）

---

# 20. Definition of Done

整个 Skill 的最终完成标准不是“功能全部自动化”。

而是满足：

```text
✓ 每个任务都有标准化 AdTask
✓ 每个账号都有 AccountProfile
✓ 每个关键判断都有 Evidence
✓ 每个预测都有 Confidence
✓ 每个运营动作都有 Decision
✓ 每个 Decision 都可解释
✓ 每个发布都有 Result
✓ 每个 Result 都可以进入 Learning
✓ 每次模型更新都有版本
✓ 历史 Decision 可以回放
✓ 错误 Decision 可以定位原因
```

最终形成：

```text
              FACT
                ↓
             EVIDENCE
                ↓
             ANALYSIS
                ↓
             DECISION
                ↓
              ACTION
                ↓
              RESULT
                ↓
             LEARNING
                ↓
              UPDATE
                │
                └──────────→ NEXT DECISION
```

这就是「新榜广告任务自动分析 Skill」的长期演进主线。
