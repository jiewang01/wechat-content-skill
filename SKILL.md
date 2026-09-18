---
name: account-content-strategist
description: >
  从账号简介/定位出发，通过 Positioning Analysis → Research → Candidate Pool →
  Market Ranking(TopN) → Positioning Filter(Top1) → Editorial Development，
  输出可直接进入文章写作流程的 Article Brief。输入一段「账号定位」即可启动。
---

# Account Content Strategist

## 1. Skill 目标

给定一个账号简介或账号定位，结合外部内容环境，找到 **值得写、适合这个账号写、并且能发展成具体文章** 的主题，最终产出 **Article Brief**（供下游 Writing Skill 使用）。

本 Skill 不直接写文章，它解决四个问题：

```text
Research           → 外部世界发生了什么？
Market Ranking     → 哪些机会值得关注？
Positioning Filter → 哪些机会属于这个账号？
Editorial          → 这个账号应该如何把它讲出来？
```

核心链路：

```text
Account Positioning
      ↓
Research
      ↓
Candidate Pool (20~50)
      ↓
Market Ranking
      ↓
TopN (默认 5)
      ↓
Positioning Filter
      ↓
Top1
      ↓
Editorial Development
      ↓
Article Brief
```

## 2. 核心设计原则

1. **Market Potential ≠ Account Fit**：市场热度与账号适配必须分阶段评估。Stage 2~4 只评估市场潜力，Stage 5 才开始看账号匹配，避免「因为适合账号所以人为提高市场排名」。
2. **Research First, Generate Later**：所有选题来自外部研究且有 Evidence 支撑，禁止用模型记忆冒充实时趋势、编造用户需求。
3. **Candidate ≠ Title**：选题阶段产出的是「内容机会对象」（core_topic + user_problem + content_angle），标题在 Top1 确定后才生成。
4. **Boundary Is a Hard Filter**：账号「不该做」的内容，Boundary Risk = HIGH 时直接 REJECT，不做降分处理。
5. **Evidence 一等公民**：关键判断尽可能可追溯（source / date / claim / confidence）。
6. **输出 Article Brief，不直接写文章**：与下游 Writing Skill 解耦。

## 3. Input / Output

### 3.1 Input

| 输入 | 说明 |
|---|---|
| 账号简介 / 账号定位（最小输入） | 一段介绍，如 "分享 AI Coding 实践，帮助程序员提升研发效率" |
| 可选 | 账号主页介绍、历史文章、用户补充的定位细节 |

### 3.2 Output

- 最终输出：`article_brief`（遵循 `schemas/article-brief.yaml`）
- 中间产物：`account_profile` → `research_finding[]` → `candidate[]` → `ranking_result`(TopN) → `top1_selection`

所有输出均为 YAML，遵循对应 schema。

## 4. Workflow（6 Stage）

| Stage | 名称 | 输入 → 输出 | Schema | Prompt |
|---|---|---|---|---|
| 1 | Positioning Analysis | 账号简介 → AccountProfile | schemas/account-profile.yaml | prompts/profile-parser.md |
| 2 | Research | AccountProfile → 5~15 ResearchFinding（Trend / Demand / Content / Gap 四 lens） | schemas/research-finding.yaml | prompts/research.md |
| 3 | Candidate Generation | AccountProfile + ResearchFinding[] → 20~50 Candidates | schemas/candidate-topic.yaml | prompts/topic-generator.md |
| 4 | Market Ranking | Candidate Pool → TopN（默认 5） | schemas/ranking-result.yaml | prompts/ranking.md |
| 5 | Positioning Filter | AccountProfile + TopN → Top1 + 被拒主题及原因 | — | prompts/positioning-filter.md |
| 6 | Editorial Development | Top1 + AccountProfile + Evidence → Article Brief | schemas/article-brief.yaml | prompts/editorial.md |

### 4.1 Stage 1 — Positioning Analysis

把非结构化账号信息转换为结构化 `account_profile`（WHO / WHY / WHAT / HOW / BOUNDARY 五个维度，见 blueprint §4.3）。无法判断的字段填 `unknown`，推断内容标注 `[inferred]`，禁止编造。

### 4.2 Stage 2 — Research

围绕 AccountProfile 生成 Research Queries（domain × audience 问题 × trend × 用户问题），执行四个 Lens：

```text
Trend   最近发生了什么？      → 新产品 / 技术 / 事件 / 趋势 / 观点 / 行业变化
Demand  用户正在关心什么？    → 用户问题 / 搜索需求 / 社区讨论 / FAQ / 使用障碍
Content 别人正在写什么？      → 热门内容 / 高互动 / 高频主题 / 饱和度 / 主流观点
Gap     什么问题已经有需求但没被讲透？ → 高需求 + 有讨论 + 内容缺口
```

每个 Finding 需回答：为什么值得关注 / 依据是什么 / 用户问题是什么 / 内容机会在哪里。

### 4.3 Stage 3 — Candidate Generation

由 ResearchFinding 的 evidence、content_gap、candidate_angles 展开候选池，做语义去重与质量过滤（有用户问题、有证据、可发展成文章、避免新闻复述）。

### 4.4 Stage 4 — Market Ranking

只评估「这个选题值不值得做」，不评估「账号该不该做」。按 scoring-policy 六维加权出 Market Score，去重 + 多样性检查后输出 TopN。默认 `top_n: 5`。

### 4.5 Stage 5 — Positioning Filter

先执行 Boundary Hard Filter（HIGH → REJECT），再对剩余候选计算 Account Fit 六维加权，综合市场分与适配度选出 Top1，并解释为什么其他 TopN 未被选中。

### 4.6 Stage 6 — Editorial Development

Top1 → target_reader → pain_points → core_insight（misconception → evidence → insight）→ angle → key_arguments → outline → title_candidates，最终输出 `article_brief`。大纲默认 8 段式（Hook / Problem / Misconception / Core Insight / Mechanism / Solution / Example / Action），可按主题类型切换（详见 prompts/editorial.md）。

## 5. 文件结构与职责

```text
account-content-strategist/
├── SKILL.md              # 本文件：目标 / 输入输出 / Workflow / 调用顺序 / 异常处理 / 输出格式
├── BLUEPRINT.md          # 设计蓝图（设计原则、评分模型、数据结构）
├── plan/
│   └── plan.md           # 实施计划（阶段拆解、验收标准、DoD）
├── schemas/              # 各阶段输入输出的数据契约（YAML）
│   ├── account-profile.yaml
│   ├── research-finding.yaml
│   ├── candidate-topic.yaml
│   ├── ranking-result.yaml
│   └── article-brief.yaml
├── prompts/              # 各阶段执行 Prompt
│   ├── profile-parser.md
│   ├── research.md
│   ├── topic-generator.md
│   ├── ranking.md
│   ├── positioning-filter.md
│   └── editorial.md
├── policies/             # 跨阶段基础规则
│   ├── research-policy.md
│   ├── evidence-policy.md
│   └── scoring-policy.md
├── examples/             # 端到端示例
│   └── ai-coding.yaml
└── evaluation/           # 评估数据集与指南（plan.md §14-16）
    ├── evaluation-dataset.yaml
    └── evaluation-guide.md
```

## 6. 调用顺序（Agent 运行约定）

1. 只有拿到 `account_profile` 之后才能开始 Research。
2. 只有拿到 `research_finding[]` 之后才能生成 Candidates。
3. 只有 Market Ranking 完成（TopN）之后才进入 Positioning Filter。
4. 只有确定 Top1 之后才进入 Editorial。
5. 任一阶段输入不足，按 §7 终止或降级；禁止跳过步骤、禁止编造中间产物。
6. Stage 2 必须调用真实检索工具获取外部信息，未取得实时数据时如实标注。

## 7. 异常处理

| 场景 | 处理方式 |
|---|---|
| Research 充足性不足 | 有效 Finding < 3 → 输出 `Research Insufficient`，降低 Evidence / Confidence，不编造 |
| 账号定位不清晰 | 无法判断的字段填 `unknown`，可推断的标 `[inferred]`；必要时要求用户补充（目标用户 / 领域 / 内容方向） |
| TopN 全部不适合账号 | 输出 `NO_VALID_TOP1` + 建议重新 Research，禁止强行选择 Top1 |
| Evidence 冲突 | 同时保留 Evidence A / Evidence B，不武断选取其一当作事实 |
| 无法判断的字段 | 一律填 `unknown`，禁止编造 |

## 8. 输出格式

- 所有中间产物与最终产出必须是 YAML 且遵循对应 schema（见 §4 表格）。
- 评分类字段范围：0~100（见 policies/scoring-policy.md）。
- 证据统一用 `{ source, source_type, date, claim, confidence }` 结构（见 schemas/research-finding.yaml 的 `evidence` 定义）。
- 最终交付：`article_brief` YAML，可直接作为下游 Writing Skill 的输入。