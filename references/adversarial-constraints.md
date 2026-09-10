# 对抗式质量约束：Defender / Attacker / Judge

> **本文档是 `wechat-content-skill` 全程实现的硬约束（Hard Constraints）。**
> 所有 Skill（research / content / visual / native / layout / publishing）、所有 core 模块（workflow / state / artifacts）、所有 validators，在任何阶段、任何分支、任何降级路径下都必须遵守本文档。
> 违反任意一条 Hx 约束的实现，视为 bug，不接受"功能优先"豁免。

---

## 1. 为什么用对抗而不是单次校验

蓝图第九章把 Quality Gate 称为"整个项目的护城河"，第十章要求 Repair Loop 做定向修复。但单次校验只有"生产 → 检查"两个角色，生产者天然倾向给自己放行。对抗式架构引入三方制衡：

```text
Defender（防御者）  产出 Artifact，抵御攻击，定向修复
Attacker（攻击者）  只找缺陷，产出结构化攻击报告，不改内容
Judge（裁判）       确定性代码终审，裁决 PASS / REPAIR / REJECT，永不改内容
```

对应蓝图的既有概念：

| 蓝图概念 | 对抗角色 |
|----------|----------|
| 各阶段 Skill 的生产职责（三、五、六章） | Defender |
| Quality Gate 4 层验证（九章） | Attacker（检出）+ Judge（裁决） |
| Repair Loop 定向修复（十章） | Defender 收到 AttackReport 后的行为约束 |
| "Prefer deterministic tools over LLM judgment"（十六章 Rules） | Judge 必须是确定性代码 |

---

## 2. 三角色定义

### 2.1 Defender（防御者）

**职责**
- 生产每个阶段的 Artifact：`ResearchResult → ContentBrief → ArticleDraft → VisualPlan → ContentPackage → WechatDocument`
- 接收 `AttackReport`，对被命中的位置执行**定向修复**（Targeted Repair）
- 每次修复必须产出 `DefenseReport`，逐条回应攻击项

**实现载体**
- Agent 侧：`skills/*/SKILL.md` 定义的生产流程
- 代码侧：`renderer/`（AST → HTML）、`core/workflow/`

**禁止**
- ❌ 自评通过（Defender 不得宣布自己的产出合格，合格与否只能由 Judge 裁决）
- ❌ 跳过攻击直接请求放行
- ❌ 修复时重写整篇 / 重排未命中的节点（见 H3）
- ❌ 删除或篡改历史 AttackReport

### 2.2 Attacker（攻击者）

**职责**
- 对当前 Gate 的输入 Artifact 生成攻击：AI 味、事实与引用缺陷、结构缺陷、组件违规、微信兼容性、可读性
- 每条攻击必须携带**可定位证据**（node_id / source_id / 行级位置 + 原文片段）

**实现载体（双引擎）**
- **规则攻击器（确定性，优先）**：`skills/content/humanize/`（AI 味黑名单 + 句长/段落/重复指标）、`validators/component/` 规则、`validators/wechat/` 规则
- **LLM 攻击器（补充）**：以"找茬"角色对内容做假设性审查，产出候选攻击，**必须先过 Judge 预审才计入回合**

**禁止**
- ❌ 直接修改 Artifact（攻击者只产出 `AttackReport`）
- ❌ 无证据指控（缺 location/evidence 的攻击一律无效）
- ❌ 攻击"风格偏好"这类无法客观判定的问题

### 2.3 Judge（裁判）

**职责**
- 预审 AttackReport：过滤无证据攻击
- 复核修复后的 Artifact，做终审裁决：`PASS / REPAIR / REJECT`
- 维护回合上限（每 Gate ≤3 轮）与裁决记录

**实现载体（只能是确定性代码）**
- `validators/content/`、`validators/component/`、`validators/wechat/`、`validators/html/`
- `core/workflow/adversarial.py`（回合调度与上限执行）

**禁止**
- ❌ 由 LLM 担任 Judge（蓝图十六章 Rules："Prefer deterministic tools over LLM judgment"）
- ❌ 修改任何内容
- ❌ 运行时放宽规则或阈值（规则外置于配置，改规则必须过测试，见 H7）
- ❌ 超限放行（3 轮后仍失败必须 REJECT）

---

## 3. 对抗协议（Adversarial Protocol）

```text
Defender 产出阶段 Artifact
        ↓
Attacker.generate_attacks(artifact) ──→ AttackReport（结构化，含证据）
        ↓
Judge.pre_screen(attack_report)      ──→ 驳回无证据攻击
        ↓
（无有效攻击）──→ Judge 裁决 PASS
        ↓（存在有效攻击）
Defender.repair(attack_report)       ──→ 更新 Artifact + DefenseReport
        ↓
Judge.verify(artifact, defense)      ──→ Verdict
        ↓                                    │
   PASS ──→ 进入下一状态                        │
        ↓                                    │
   REPAIR（round+1，round < 3）──→ 回到 Attacker │
        ↓                                    │
   REJECT（round == 3 仍失败）──→ 降级出口        │
                                               │
降级出口：export HTML + 本地 artifact + 人工审核清单
（发布不是 Workflow 的唯一出口 —— 蓝图十二章）
```

**回合产物（全部是结构化 Artifact，进 checkpoint）**

```json
{
  "gate": "render",
  "round": 2,
  "attacks": [
    {
      "id": "atk_007",
      "category": "unsupported_css",
      "severity": "error",
      "location": "component_17",
      "evidence": "style contains display:grid",
      "suggestion": "replace with inline-block layout"
    }
  ]
}
```

```json
{
  "gate": "render",
  "round": 2,
  "decision": "REPAIR",
  "reason": "1 unresolved attack: atk_007",
  "unresolved": ["atk_007"]
}
```

---

## 4. 三个 Gate 的对抗映射

| Gate | 触发状态（蓝图十一章） | 攻击面 | Attacker 组件 | Judge 组件 |
|------|------------------------|--------|---------------|------------|
| **Content Gate** | DRAFTED → | AI 味 / 事实 / 引用 / 结构 / 字数 | `skills/content/humanize/` + content 规则 | `validators/content/` |
| **Render Gate** | RENDERING → | 组件未知 / 缺必填 prop / 非法嵌套 / 属性 / 主题缺失 | `validators/component/` 规则 | `validators/component/` |
| **Publish Gate** | VALIDATED → READY_TO_PUBLISH | 微信兼容性 / inline CSS / 图片 / 体积 / 空节点 | `validators/wechat/` + `validators/html/` 规则 | `validators/wechat/` |

三个 Gate 共用同一套对抗协议与同一份回合上限计数器，仅攻击面与规则集不同。

---

## 5. 硬约束清单（全程生效）

| # | 约束 | 验收方式 |
|---|------|----------|
| **H1** | **角色分离**：同一执行单元不得同时担任 Defender 与 Judge；LLM 可任 Defender/Attacker，**永远不得担任 Judge** | 代码审查 + Judge 模块无 LLM 调用 |
| **H2** | **无证据不攻击**：AttackReport 每条必须含 `location` + `evidence`，否则 Judge 预审驳回 | 单测：空证据攻击被过滤 |
| **H3** | **定向修复**：Defender 只允许修改被命中的节点/字段，禁止重写整篇 | Repair Loop 单测：未命中节点内容不变 |
| **H4** | **回合上限**：每个 Gate 最多 3 轮对抗；超限 REJECT 走降级出口，绝不放行 | 单测：第 3 轮失败后状态为 REJECT |
| **H5** | **带病不发布**：Judge 未判 PASS 的 Artifact 不得进入 UPLOADING | 状态机守卫：VALIDATED → READY_TO_PUBLISH 需 PASS 记录 |
| **H6** | **全程留痕**：每轮 Attack/Defense/Verdict 均为结构化 Artifact 并写入 checkpoint | resume 后可完整回放对抗历史 |
| **H7** | **规则外置**：Judge 的确定性规则（白名单/阈值/黑名单）全部外置配置，修改需过测试 | 规则文件在 `validators/*/rules/`，无硬编码 |
| **H8** | **确定性优先**：门禁判定以确定性 Validator 为准；LLM 攻击仅作补充信号，不能推翻确定性规则 | Judge.verify 只消费规则结果 |

---

## 6. 对抗产物 Schema（M1 落地清单）

在蓝图八章 Artifact 之外，对抗循环新增 3 个一等 Artifact：

| Artifact | 生产者 | 消费者 |
|----------|--------|--------|
| `AttackReport` | Attacker | Defender（修复依据）、Judge（预审） |
| `DefenseReport` | Defender | Judge（复核依据） |
| `Verdict` | Judge | Orchestrator（状态推进 / 回合控制） |

三者均入 `core/artifacts/`，均参与 checkpoint 序列化，均有 JSON Schema。

---

## 7. 与参考仓库的实现对应

不抄代码，只借已验证的模式：

- `843645440/wechat-skill` 的 **双质量门（component_lint + validate_gzh_html）** → Judge 的确定性裁决基座（H1、H8 的落地参照）
- `jiji262/wechat-publisher` 的 **ai_score 阈值门禁** → Judge 阈值化裁决（分数门限 + 规则黑名单双轨）
- `yunshengya/wechat-article` 的 **skip 降级标志** → REJECT 后的降级出口设计（export HTML / 本地 artifact / 人工发布）

---

## 8. 各模块落点（实现索引）

| 模块 | 承担角色 | 必须遵守 |
|------|----------|----------|
| `skills/research/SKILL.md` | Defender | H3：只按 AttackReport 修 facts/sources |
| `skills/content/SKILL.md` | Defender | H3：humanize 重写只改命中句段 |
| `skills/content/humanize/` | Attacker（规则） | H2：命中必须给位置与原文证据 |
| `skills/visual/SKILL.md` | Defender | H3 |
| `skills/native/SKILL.md` | Defender | H3 |
| `skills/layout/SKILL.md` | Defender | H3 |
| `skills/publishing/SKILL.md` | Defender + 降级执行 | H5：UPLOADING 前必须有 PASS Verdict |
| `renderer/` | Defender（代码） | H3：Repair Loop 只重渲染受影响子树 |
| `validators/content/` | Judge | H1、H7、H8 |
| `validators/component/` | Judge + Attacker（规则） | H1、H7 |
| `validators/wechat/` + `validators/html/` | Judge + Attacker（规则） | H1、H7 |
| `core/workflow/adversarial.py` | 回合调度（非角色） | H4、H6：上限执行与留痕 |
| `core/state/` | 状态守卫 | H5：VALIDATED→READY_TO_PUBLISH 检查 PASS |
| `core/artifacts/` | Artifact 定义 | H6：Attack/Defense/Verdict 三模型 |

---

## 9. 一句话记忆

> **Defender 生产、Attacker 找茬、Judge 用代码裁决；证据不足不攻击，命中之外不动手，三轮不过走降级，没有 PASS 不发布。**
