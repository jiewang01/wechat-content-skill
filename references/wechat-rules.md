# 公众号 HTML 安全规则（WeChat Rules）

公众号编辑器会**剥离或改写**它不认识的标签与属性。`WechatDocument.html` 必须满足以下全部规则，否则发布产物不可控。这些规则由确定性渲染器（`renderer/html/renderer.py`）保证，并由 gzh 验证器机器复核（H8）——**LLM 绝不手写发布 HTML**。

## 一、标签白名单

只允许 5 个标签：

| 标签 | 用途 |
|------|------|
| `section` | 块级容器（段落、组件、分隔线） |
| `span` | 行内文字与标记（列表符号、引用署名） |
| `strong` | 加粗 |
| `em` | 斜体 |
| `img` | 图片 |

其余一律禁止：`div`、`p`、`br`、`h1-h6`、`ul/ol/li`、`blockquote`、`style`、`script`、`iframe`、`a` 等。标题层级用 `section + 内联字号` 表达。

## 二、属性与样式

1. **全部内联样式**：只有 `style="..."` 一个样式通道；`<style>` 块、外部 CSS 一律禁止。
2. **无 class / id 钩子**：公众号环境不可控，任何选择器都不可靠。
3. **无 JavaScript**：`script`、`on*` 事件属性一律禁止。
4. **无外部资源**：字体、CSS、JS 的外链一律禁止；图片必须走公众号素材库 URL（发布时由上传流程替换）。
5. 所有属性值必须经 HTML 转义（`src`、`alt` 等）。

## 三、渲染器已内置的规避手法

这些是确定性渲染器的实现决策，改主题不改这些行为：

| 场景 | 手法 |
|------|------|
| 代码块换行 | `white-space: pre-wrap`，**不产生 `<br>`**（`br` 不在白名单） |
| 分隔线 `---` | 1px 高、带 `background` 颜色的 `section`，内容留一个空格（纯空节点会被编辑器吞掉） |
| 链接 `[text](url)` | 降级为纯文本 `text（url）`（`a` 标签在正文中不可靠） |
| 行内代码 `` `code` `` | 样式化 `span`，不用 `code` 标签 |
| 列表 | `section` 缩进 + 着色标记 `span`（`•` 或 `N.`），不用 `ul/ol/li` |
| 标题 | `section` + 主题字号/字重，不用 `h1-h6` |

## 四、排版约定

由主题（`renderer/themes/<theme>/typography.yaml` + `components.yaml`）决定，v0.1 内置 `default`：

- 正文 15-16px、行高 1.75 左右、`word-break: break-all`（防英文长词溢出手机屏）；
- 组件（note / quote / callout / card）用 `background` + `border-left` + 圆角区分层级；
- 图片内联 `width` / `max-width: 100%`，不依赖编辑器默认；
- 全部尺寸用 `px`，不用 `rem`/`em`/`%`（编辑器对相对单位处理不一致）。

## 五、验证与修复

1. 发布前必须过 gzh 验证器（机器检查白名单、禁用模式、样式通道），全部通过才允许 `PublishResult` 生成（H5）。
2. 验证失败时**定向修复**：按节点 id（`node_N` / `component_N`）只重渲染被标记的节点（H3）；修复循环 ≤ 3 轮（H4）。
3. 本地预览用 `python scripts/preview.py <wechat.html>`：预览页的 `<style>` 仅服务于预览框架（手机框），**绝不进入发布产物**。

## 六、发布产物形态

`WechatDocument.html` 是**片段**，不是完整 HTML 文档：无 `<!DOCTYPE>`、无 `<html>/<head>/<body>`；标题与摘要在公众号后台单独填写（`WechatDocument.title` / `.digest` 随产物一起交付）。
