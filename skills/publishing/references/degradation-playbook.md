# 降级手册（Degradation Playbook）

蓝图十二章：**发布不是 Workflow 的唯一出口**。微信 API 任何环节不可用时，
流程必须仍能以本地 HTML 收尾，绝不因第三方故障丢稿。

## 四级出口判定

| 出口 | 触发条件 | 处置动作 |
|------|----------|----------|
| `published` | release 确认 publish_state=0 | 记录 publish_id 与 article_url；流程结束 |
| `draft_created` | 封面上传 + 草稿创建全部成功（未开启 auto_release） | 记录 draft_id；需要正式发布时调 `release(draft_id)` 或在后台群发 |
| `degraded` | 无可用封面 / 微信 API 业务错误 / HTTP 5xx / 网络不通 / 发布未确认成功 | 打开 `html_path` 本地副本，按下方「人工发布 Checklist」执行 |
| `failed` | 本地导出都失败（目录不可写、磁盘满） | 修复 output_dir 权限后重跑发布；此出口没有任何 artifact 落地 |

非 `failed` 出口都会落 `html_path` 本地留档；`degraded` 额外置 `degraded: true`。

## release（正式发布）降级场景

release 绝不抛出：任何失败都收敛为 `degraded` + message。处置对照：

| 场景 | 表现 | 处置动作 |
|------|------|----------|
| 提交被拒（errcode） | submit 返回业务错误（额度耗尽 / 草稿不合规等） | 看 message 中的 errcode；草稿仍在草稿箱，排障后凭 draft_id 重新 release |
| 群发额度耗尽 | 订阅号每天 1 次、服务号每月 4 次 | 次日凭 draft_id 重新 release，不重跑内容管线 |
| 审核 / 原创申明失败 | publish_state=1/2/3（终态失败） | message 含具体 state；按驳回原因改稿后重建草稿再 release |
| 轮询超时 | 超过 max_polls（默认 10 次 × 1s）仍是 publish_state=4 | 大多数为延迟非失败：稍后在公众号后台或用 publish_id 查询确认，不盲目重复 submit |

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
3. 正文：HTML 片段自带 UTF-8 BOM（字节层编码签名，无 charset 声明的片段在浏览器 / IDE 中裸打开也能正确显示中文）；如需带手机框的完整效果，跑 `python scripts/preview.py <wechat.html>` 生成预览页。全选复制正文区域，粘贴进公众号编辑器（BOM 不会进入剪贴板内容）。
4. 标题 / 摘要 / 作者：从 WechatDocument 的 `title` / `digest` / `author` 字段取值。
5. 完成后在 run 目录记录人工发布时间与操作者（H6 审计链）。

## 禁止事项

- 不得因降级而丢弃或改写成稿内容。
- 不得在降级出口下静默重试超过既有的一次 token 重试——避免打爆限流配额。
- 不得绕过 H5 门禁把未通过校验的稿子直接人工发布。
