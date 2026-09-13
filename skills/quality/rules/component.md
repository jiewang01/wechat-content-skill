# 组件门规则 —— `validators/component/lint.py`

入口：`lint_components(semantic_markdown, theme=None) -> list[ValidationIssue]`

检查对象是语义 Markdown（标记层），在渲染之前执行。与 parser 的关系：

- parser（`renderer/ast/parser.py`）：fail-fast，首错即抛 → 渲染门直接拦截
- lint（本模块）：收集型，一次报告**全部**问题 → 为 H3 定向修复提供完整可修复点位列表

## 11 类错误（全部 error 级）

| issue type | 判定 |
|-----------|------|
| `unknown_component` | 标记名不在组件注册表 |
| `missing_required_prop` | 缺少必填属性 |
| `unsupported_attribute` | 属性不被该组件支持 |
| `invalid_prop_value` | 属性值类型 / 取值非法 |
| `invalid_nesting` | 不允许的嵌套：card 之外的组件内出现 `:::` 标记、card 内嵌 card、深度超过 2 层（归属父组件 node） |
| `invalid_card_content` | card 正文必须是列表行（`-` 或 `1.` 开头） |
| `stray_marker` | 未配对的 `:::` 结束标记 |
| `invalid_marker_syntax` | 以 `:::` 开头但不是合法的 `:::name key="value"` 标记行 |
| `unclosed_marker` | 到文件末尾仍未闭合（嵌套时每一层各报一条，归属各自 node） |
| `unclosed_code_block` | 到文件末尾仍未闭合的 ``` 代码块 |
| `theme_component_missing` | 组件未被主题启用或缺样式（两种情形见下） |

前四类复用 `renderer/components/registry` 的 `validate_marker` 契约（`MarkerValidationError.error_type`）——
注册表是组件属性契约的单一事实来源，lint 与 parser 不另设一套。

## v0.3 受控嵌套

栈式扫描与 parser 同构，嵌套合法性由 registry 的 `allowed_children` 驱动：

- 仅 card 可作容器，子组件为 note / quote / callout；顶层组件编号 `component_N`，子组件 `component_N.M`
- 深度上限 `MAX_COMPONENT_DEPTH = 2`：card + 一层子组件，子组件内不可再嵌套
- 嵌套违例归属**父组件**报 `invalid_nesting`，违例行跳过不建子栈（与 parser 不构建该节点同构）
- 子组件自身的属性错误归属子组件自己的 `component_N.M`
- card 正文里的子组件块不占列表行，不触发 `invalid_card_content`
- 组件内的非法标记行（如 `:::note foo`）同样按嵌套违例处理：报 `invalid_nesting` 归属父组件

## theme_component_missing 的两种情形

传入 `theme` 时，对注册表内已知组件额外检查：

1. `theme.components_enabled[name]` 为假 → 主题**未启用**该组件（去 theme.yaml 的 `components` 配置启用）
2. 已启用但 `name` 不在 `theme.components` → 主题**缺样式定义**（去 components.yaml 补样式）

## 定位与修复

- 问题节点 id 形如 `component_N`（按标记出现顺序编号）；`stray_marker` / `invalid_marker_syntax` / `unclosed_code_block` 无节点 id（`node=""`）
- 注册表错误携带 `property`（出错的属性名）
- 修复按 node 定向处理（H3），不要整篇重写

## 代码块感知

``` 围栏内的内容不参与标记解析 —— 代码示例里的伪 `:::` 标记不会误报。

## 信任时机

- 语义标记生成后、渲染前；管线中本门错误记在 `gate="content"`（组件错误本质是内容层标记问题），抛 `ContentGateError`
- 设计阶段（DESIGNING）LLM 产出的语义标记也先过这道门，有错则整段弃用、回退纯 Markdown
