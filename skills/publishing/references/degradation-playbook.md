# 降级手册（Degradation Playbook）

蓝图十二章：**发布不是 Workflow 的唯一出口**。微信 API 任何环节不可用时，
流程必须仍能以本地 HTML 收尾，绝不因第三方故障丢稿。

## 三级出口判定

| 出口 | 触发条件 | 处置动作 |
|------|----------|----------|
| `draft_created` | 封面上传 + 草稿创建全部成功 | 记录 draft_id；在公众号后台预览、群发 |
| `degraded` | 无可用封面 / 微信 API 业务错误 / HTTP 5xx / 网络不通 | 打开 `html_path` 本地副本，按下方「人工发布 Checklist」执行 |
| `failed` | 本地导出都失败（目录不可写、磁盘满） | 修复 output_dir 权限后重跑发布；此出口没有任何 artifact 落地 |

非 `failed` 出口都会落 `html_path` 本地留档；`degraded` 额外置 `degraded: true`。

## 常见 errcode 与处置

| errcode | 含义 | 系统行为 | 人工动作 |
|---------|------|----------|----------|
| 40001 / 42001 | access_token 失效 / 过期 | 自动废弃缓存并重试一次（`call_with_token_retry`） | 若仍失败，核对 app_id / app_secret 环境变量 |
| 45009 | API 调用次数超限 | 降级出口 | 次日重试；或减少正文图数量后重跑 |
| 40013 | invalid appid | 降级出口 | 核对 `accounts/*.yaml` 引用的环境变量名 |
| 48001 | api unauthorized（测试号无草稿权限） | 降级出口 | 换已认证账号，或走人工发布 |

## 人工发布 Checklist

1. 确认 `html_path` 指向的 HTML 文件存在且内容完整（样式全部内联，粘贴即生效）。
2. 封面：本地封面文件（或 data URI）→ 公众号后台「图文素材 → 上传封面」。
3. 正文：浏览器打开 HTML，全选复制，粘贴进公众号编辑器。
4. 标题 / 摘要 / 作者：从 WechatDocument 的 `title` / `digest` / `author` 字段取值。
5. 完成后在 run 目录记录人工发布时间与操作者（H6 审计链）。

## 禁止事项

- 不得因降级而丢弃或改写成稿内容。
- 不得在降级出口下静默重试超过既有的一次 token 重试——避免打爆限流配额。
- 不得绕过 H5 门禁把未通过校验的稿子直接人工发布。
