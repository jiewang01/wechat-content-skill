# 公众号门规则 —— `validators/wechat/gzh.py`

入口：`lint_gzh(html, *, max_bytes=None) -> list[ValidationIssue]`

检查渲染产物 HTML 的平台约束（产物层最后一道门）。蓝图 9.3 九项中的平台侧五项落在本模块；
`max_bytes` 缺省 1MB，可传更小值便于测试。

## 五项约束（全部 error 级）

| issue type | 判定 |
|-----------|------|
| `html_too_large` | UTF-8 字节数超过 `DEFAULT_MAX_HTML_BYTES = 1_000_000`（公众号正文约限 1MB） |
| `external_resource` | 出现外部资源引用标签（`script` / `iframe` / `embed` / `object` / `video` / `audio` / `source` / `track` / `link`），或 style 中的 `url()` |
| `broken_image` | `img` 缺少 src（地址为空） |
| `insecure_image_url` | `img` 的 src 不以 `https://` 开头（应为已上传的微信素材域名），`property` = 图片地址 |
| `missing_image_dimensions` | `img` 的 style 缺少 `width` 声明（避免横向溢出） |

细节：

- HTML 语法问题由 HTML 门负责；本门解析失败时静默返回（体积检查仍生效）
- 图片必须走「上传素材 → https 素材域名」链路，禁止外链图床

## 信任时机

- 发布前最后一道门（管线 VALIDATING 状态）：error → REPAIR 修复循环，每轮定向修复后复检，最多 3 轮（`_MAX_PUBLISH_ROUNDS`，H4）；清零 → VALIDATED，超限 → REJECT
- 通过 = 可进入 READY_TO_PUBLISH；正式发布还受配额与审核约束（见 [../SKILL.md](../SKILL.md) 与 [../../publishing/SKILL.md](../../publishing/SKILL.md)）
- 组合校验：`validate_wechat_html(html)` = HTML 门 + 本门（蓝图 9.3 完整九项）
