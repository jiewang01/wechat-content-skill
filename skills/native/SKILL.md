---
name: native
description: wechat-content-skill 的原生信息子技能：为文章 Markdown 标注四种语义标记（:::note、:::quote、:::callout、:::card），由确定性渲染器转换为主题组件。LLM 绝不写 HTML。
---

# Native Skill（语义标记层）

## 目标

在写作与渲染之间加入原生信息结构：Agent 用语义标记表达意图，渲染器独占全部 HTML。这正是主题切换与微信兼容得以成立的前提。

## 输入 / 输出

- 输入：`ArticleDraft` + `VisualPlan`
- 输出：`ContentPackage`（schemas/content_package.schema.json）—— `semantic_markdown` 携带标记

## 四种标记（全集，没有其他）

```markdown
:::note
默认蓝色提示。用于补充说明、背景信息。
:::

:::quote cite="Linus Torvalds, 2025"
引用原话。cite 可选。
:::

:::callout type="warning" title="注意"
type ∈ info | warning | tip | danger；title 可选。
:::

:::card title="核心要点"
- 第一条
- 第二条
:::
```

## 嵌套（v0.3）

只有 card 是容器：正文列表项之间可插入 note / quote / callout 子组件块，深度上限 2 层（`MAX_COMPONENT_DEPTH`，子组件内不可再嵌套）。子组件 node_id 为 `component_N.M`，同样是 lint 定向修复的定位键。

```markdown
:::card title="核心要点"
- 文本要点
:::note
局部旁注：只与这张卡片相关的补充。
:::
- 收尾要点
:::
```

| 容器 | 允许的子组件 | 更深一层 |
|------|--------------|----------|
| card | note / quote / callout | 不允许（深度上限 2） |
| note / quote / callout | 无 —— 任何 `:::` 标记都报 `invalid_nesting` | — |

## 规则（Defender 职责）

- 标记只允许使用 [components/](components/) 与 `renderer/components/registry.py` 中定义的属性；未知属性是 lint 错误。
- **受控嵌套（v0.3）**：仅 card 可作容器，子组件只允许 note / quote / callout，深度上限 2 层（子组件内不可再嵌套）；其余任何嵌套组合报 `invalid_nesting`。语法见上方「嵌套」一节。
- 克制使用：大约每 300–500 字一个组件；文章不能变成幻灯片。
- 绝不输出 `<div>`、`<span>`、内联样式或任何 HTML —— 只用语义标记；HTML 由渲染器确定性生成。
- lint 攻击某个组件（`component_N`，嵌套子组件 `component_N.M`）时，只修复该组件（H3）。

## 组件规格

- [components/note.md](components/note.md)
- [components/quote.md](components/quote.md)
- [components/callout.md](components/callout.md)
- [components/card.md](components/card.md)

## lint 错误类型速查

组件 lint（`validators/component/`）容错扫描，一次报告全部问题；
`node` 为 `component_N`，`property` 为涉事属性 —— 两者是定向修复的定位键（H3）。

| error_type | 触发 |
|------------|------|
| `unknown_component` | 使用注册表之外的组件名 |
| `unsupported_attribute` | 组件不支持的属性 |
| `missing_required_prop` | 缺少必填属性 |
| `invalid_prop_value` | 属性值不在枚举内（如 callout 的 type） |
| `invalid_nesting` | 不允许的嵌套：card 之外的组件内出现 `:::` 标记、card 内嵌 card、深度超过 2 层 |
| `invalid_card_content` | card 正文不是列表 |
| `unclosed_marker` | `:::` 开始标记未闭合 |
| `stray_marker` | 出现未配对的 `:::` 结束标记 |
| `invalid_marker_syntax` | 标记行语法非法（如 `:::note foo`） |
| `theme_component_missing` | 主题未启用组件或缺样式定义 |
| `unclosed_code_block` | 代码围栏未闭合 |

HTML 层（`validators/html/`，蓝图 9.3）与公众号平台层（`validators/wechat/`）
在渲染后执行，`validate_wechat_html()` 一次组合九项检查；
`property` 形如 `display:grid`，同样是定向修复的定位键。

| error_type | 层 | 触发 |
|------------|----|------|
| `forbidden_tag` | html | 标签不在 {section, span, strong, em, img} |
| `style_block` | html | 出现 `<style>`/`<link>`（样式必须全部内联） |
| `disallowed_attribute` | html | 属性不在 {style, src, alt}（如 class/id） |
| `html_structure` | html | 标签交叉、未闭合或多余结束标签 |
| `unsupported_css` | html | CSS 属性不在白名单，或 `display` 取值非 block/inline/inline-block |
| `empty_node` | html | 节点无文本、无子元素（hr 的单空格 section 豁免） |
| `broken_image` | gzh | 图片缺少 src |
| `insecure_image_url` | gzh | 图片地址非 `https://` 开头 |
| `missing_image_dimensions` | gzh | 图片 style 缺 width 声明 |
| `external_resource` | gzh | `<script>`/`<iframe>` 等引用标签或 style 中的 `url()` |
| `html_too_large` | gzh | UTF-8 体积超过 1MB 上限（可配置） |

Content 层（`validators/content/`，蓝图 9.1 v1 四项）在成稿后、渲染前执行：
结构完整性 / 字数 / AI 味复检 / 引用 ID 一致性。AI 味复检不信任
`draft.humanize` 缓存而是重跑检测器；`research` 缺省时跳过引用检查（降级）；
字数口径与 parser 一致（`core.utils.estimate_word_count`）。

| error_type | 触发 |
|------------|------|
| `structure_incomplete` | 标题为空 / 正文为空 / 正文无 Markdown 标题行 |
| `word_count_mismatch` | 声明字数与实际相差超过 max(20, 5%) |
| `word_count_below_target` | 实际字数低于大纲目标的 50%（warning） |
| `ai_flavor_blacklist_phrase` | AI 高频套话命中（error） |
| `ai_flavor_paired_phrase` | 同句关联句式如「随着…的发展」（error） |
| `ai_flavor_long_sentence` | 单句超 60 字（warning，evidence 即 property） |
| `ai_flavor_avg_sentence_length` | 平均句长超 35 字（warning） |
| `ai_flavor_long_paragraph` | 段落超 200 字（warning） |
| `ai_flavor_repetition` | 5-gram 重复出现 ≥3 次（warning） |
| `unknown_source_ref` | Fact.source_ids 引用不存在的 source_id |
| `unknown_fact_ref` | 文章或大纲小节引用不存在的 fact_id |

## 修复循环（渲染层）

lint 报错之后由 `core/workflow/repair.py` 执行定向修复（蓝图十章）：

- 输入是渲染段（`node_id` + `html`），错误归属**以段为准**——段的 `node_id`
  覆盖 lint 返回的 node，是 H3 定位键的唯一事实来源。
- 修复策略全部确定性（H8）：

| 错误场景 | 修复动作 |
|----------|----------|
| `display` 受限取值（如 `display:grid`） | 替换为回退值 `display:block` |
| 白名单外 CSS 属性（如 `position:fixed`） | 删除该声明，其余声明保留 |
| 删除后 `style` 为空 | 连 `style` 属性一并移除 |
| 其他错误类型（如 `forbidden_tag`） | 无确定性修复手段，原样留档 |

- 每轮修复后全量复检，至多 3 轮（H4）；无可修复项或无进展提前终止。
- 3 轮后仍 failed → ErrorReport（`gate="render"`）留档，发布门禁拦截（H5）。
- `repair_rendered(ast, renderer)` 一步完成渲染 + 修复闭环；
  `RepairOutcome.repaired_nodes` 记录被改动的节点（H6 审计线索）。

## 参考资料

- [../../references/adversarial-constraints.md](../../references/adversarial-constraints.md)
