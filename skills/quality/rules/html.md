# HTML 门规则 —— `validators/html/checks.py`

入口：`lint_html(html) -> list[ValidationIssue]`

检查渲染产物 HTML（产物层）。白名单与 `renderer/html/renderer.py` 实际发射的标签 / 属性 / CSS **同步维护**（单测锚定：渲染器产出零误报），因此默认管线全绿 —— 这是 H5 / H8 的前提。

## 标签白名单

| 常量 | 取值 | 违规 issue type |
|------|------|-----------------|
| `ALLOWED_TAGS` | `section` / `span` / `strong` / `em` / `img` | `forbidden_tag` |
| `STYLE_TAGS` | `style` / `link` | `style_block`（公众号样式必须全部内联） |

注意：`<br>` / `<div>` / `<p>` 等常见标签都不在白名单内，会触发 `forbidden_tag` ——
换行用 `white-space: pre-wrap`，容器一律 `section`（见 wechat-rules.md 渲染器规避手法）。

## 属性与 CSS

- `ALLOWED_ATTRS = {style, src, alt}`，其他属性 → `disallowed_attribute`（`property` = 属性名）
- `ALLOWED_CSS_PROPS`（19 项）：color / font-size / font-weight / font-family / line-height / margin-top / margin-bottom / background / border / border-left / border-radius / padding / padding-left / display / width / max-width / height / white-space / word-break
  - 白名单外的 CSS 属性 → `unsupported_css`
- `RESTRICTED_CSS_VALUES`：`display` 仅允许 `block` / `inline` / `inline-block`，其他取值（如 `flex` / `grid`）→ `unsupported_css`
- `unsupported_css` 的 `property` 形如 `prop:value`，修复器据此定向替换（`core/workflow/repair.py`）

## 结构检查

| issue type | 判定 |
|-----------|------|
| `html_structure` | 多余的结束标签 / 闭合前有标签未闭合 / 文档结束仍有标签未闭合 / HTML 解析失败（语法严重非法） |
| `empty_node` | 空节点：非 void 标签自闭合（`<span/>`）或开标签内无任何文本与子元素 |

`img` 等 void 标签不会误报 `empty_node`；`style` / `link` / `script` 等标签豁免空节点检查（由 `style_block` / `forbidden_tag` / `external_resource` 各自负责）。

## 信任时机

- 渲染完成后立即执行；渲染修复循环（`repair_rendered`）内部逐轮运行本检查，error 未清零 → `gate="render"` 拒绝
- 产物是 HTML 片段（无 DOCTYPE / html / head / body）—— 这是公众号后台粘贴的预期形态，不是结构错误
- 组合校验：`validate_wechat_html(html)` = 本门 + 公众号门（蓝图 9.3 完整九项）
