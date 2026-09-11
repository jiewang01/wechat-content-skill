---
name: quality
description: wechat-content-skill 的质量门权威说明（Judge 侧）：content / component / html / wechat 四道门各管什么、问题类型与 severity 语义、管线门禁流转与修复轮次上限。回答「何时信任哪个门」。
---

# Quality Skill（质量门技能）

## 目标

回答一个核心问题：**何时信任哪个门**。

`validators/` 的四个模块就是四道门，本 skill 与之一一对应（`rules/` 四份规则文档），是门的**唯一权威说明**：通过条件、问题类型、severity 语义只在这里定义；其他 skill 引用本文，不重复定义。

## 输入 / 输出

- 输入：任一中间产物 —— `ArticleDraft`（内容门）、语义 Markdown（组件门）、渲染 HTML（HTML 门 / 公众号门）
- 输出：`list[ValidationIssue]`（字段：`type` / `node` / `property` / `message` / `severity`）

全部 validator 遵守同一容错契约：**永不抛异常；一次扫描收集全部问题；空列表 = 通过**。
（对比：parser 是 fail-fast 的，首错即抛 —— 两者互补，lint 的全量问题列表是 H3 定向修复的前提。）

## 四道门总览

| 门 | 对应模块 · 规则 | 入口函数 | 检查层 | 何时信任 |
|----|----------------|----------|--------|----------|
| 内容门 | `validators/content/qa.py` · [rules/content.md](rules/content.md) | `lint_content(draft, research, brief)` | 文本层 | 初稿完成、进入视觉规划前。通过 = 文本层达标，**不代表可发布** |
| 组件门 | `validators/component/lint.py` · [rules/component.md](rules/component.md) | `lint_components(semantic_markdown, theme)` | 标记层 | 语义标记生成后、渲染前。错误全部拦截在渲染之前 |
| HTML 门 | `validators/html/checks.py` · [rules/html.md](rules/html.md) | `lint_html(html)` | 产物层 | 渲染后（渲染修复循环逐轮执行）。白名单与渲染器输出同步，默认链路零误报 |
| 公众号门 | `validators/wechat/gzh.py` · [rules/wechat.md](rules/wechat.md) | `lint_gzh(html)` | 产物层 | 发布前最后一道。`validate_wechat_html()` = HTML 门 + 公众号门（蓝图 9.3 九项） |

**信任原则：下层通过不能反推上层没问题** —— HTML 干净不代表文本 / 标记层达标，每层各有各的门。

## severity 语义（全门通用）

`ValidationIssue.severity` 仅两种取值（`core/artifacts/models.py`）：

- `error`（默认）：硬失败。管线中触发 REJECT / REPAIR，未清零不得推进状态机
- `warning`：软提示。不拦截流转，但计入报告（如 `word_count_below_target`、AI 味的四个 warning 类）

## 工作流（管线门禁流转）

`core/workflow/pipeline.py` 把四道门接进状态机，gate 名只有三个（content / render / publish）：

| 步骤 | 门 | 动作 |
|------|----|------|
| WRITING → DESIGNING | 内容门 | `lint_content` 有 error → `gate="content"` 拒绝，抛 `ContentGateError` |
| DESIGNING（预检） | 组件门 | LLM 产出的语义标记先过 `lint_components`，有错则弃用该设计、回退 `draft.markdown` |
| RENDERING → VALIDATING | 组件门 + 渲染门 | `lint_components` 错误记 `gate="content"`（组件错误本质是内容层标记问题）；`repair_rendered` 渲染 + 修复循环逐轮跑 `lint_html`（≤ 3 轮，`MAX_REPAIR_ROUNDS`），残留 error → `gate="render"` 拒绝；parser 解析失败同样以 `RenderError` 拦截 |
| VALIDATING → VALIDATED / REJECT | 公众号门 | `lint_gzh` 有 error → 修复循环（≤ 3 轮，`_MAX_PUBLISH_ROUNDS`，H4），清零 → VALIDATED，超限 → REJECT |
| VALIDATED → READY_TO_PUBLISH | — | 全部通过；发布能力与降级出口见 [../publishing/SKILL.md](../publishing/SKILL.md) |

单命令跑三层门禁：`python scripts/validate.py pkg.json`（组件门 → 渲染修复循环 → 公众号门；stdout 输出 `ValidationReport` JSON，退出码 0/1/2）。

### 修复策略（H3）

修复永不整篇重写：validator 输出全量问题列表（`node` 定位 + `property` 细化，HTML 门的 `property` 形如 `prop:value`），修复器按问题逐节点定向修复。这就是收集型 lint 存在的意义。

## evals 回归

- `python scripts/run_evals.py`：20 个语料（humanize 4 / content_gate 4 / render 5 / framework 7）一键回归，JSON 报告默认写 `outputs/evals/evals-report.json`
- 退出码：`0` 全绿 / `1` 回归 / `2` 环境错误
- 阈值集中在 `tests/evals/thresholds.py`（好文 ≥ 90 分、AI 味文 ≤ 50 分），调整只改这一个文件
- `python -m pytest tests/evals`：13 个回归测试锁住以上行为

## 规则（Judge 职责）

1. 判分只依据 validator 返回的问题列表，不做主观打分 —— Judge 永远是确定性代码（H8）
2. 任何门存在 error，不得宣告「可发布」（H5：无 PASS 裁决不发布）
3. 修复循环严格计数：渲染 / 发布各最多 3 轮，超限必须 REJECT，不得继续重试（H4）
4. 汇报问题一律引用 issue type（如 `structure_incomplete`、`external_resource`），不发明新名词
5. warning 不阻断流转；修复排序先清 error，再看 warning

## 组件

- [rules/content.md](rules/content.md) —— 内容门：四类检查、字数容差与 AI 味映射
- [rules/component.md](rules/component.md) —— 组件门：11 类错误、代码块感知与主题组件检查
- [rules/html.md](rules/html.md) —— HTML 门：标签 / 属性 / CSS 白名单全集
- [rules/wechat.md](rules/wechat.md) —— 公众号门：平台五项约束

## 参考资料

- [../../references/adversarial-constraints.md](../../references/adversarial-constraints.md) —— H 系列硬约束全文（H3 / H4 / H5 / H8）
- [../../references/wechat-rules.md](../../references/wechat-rules.md) —— 公众号平台规则与渲染器规避手法
- [../../references/content-policy.md](../../references/content-policy.md) —— 内容合规红线（引用规范的「为什么」）
- [../../references/seo.md](../../references/seo.md) —— 标题 / 摘要 / 关键词与搜一搜收录
