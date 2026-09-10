---
name: publishing
description: wechat-content-skill 的发布子技能：把校验通过的 WechatDocument 经 WeChatPublisher Facade 落进公众号草稿箱；微信 API 不可用时按降级手册以本地 HTML 收尾——发布永远不是流程的唯一出口。
---

# Publishing Skill（发布技能）

## 目标

把一份**校验通过**的成稿安全地送进公众号草稿箱。安全的含义：

- 上层永远不碰 access_token / media_id / thumb_media_id 等微信细节（蓝图十三章）；
- 无论微信侧发生什么，流程总能以一个本地 artifact 收尾（蓝图十二章：发布不是 Workflow 的唯一出口）。

## 输入 / 输出

- 输入：`WechatDocument`（schemas/wechat_document.schema.json），且必须携带 `status == "passed"` 的 `ValidationReport`（H5 红线）
- 输出：`PublishResult`（schemas/publish_result.schema.json）

```json
{
  "status": "draft_created | degraded | failed",
  "media_id": "封面上传返回的素材 id（即 thumb_media_id 来源）",
  "draft_id": "草稿箱 media_id，后续群发 / 预览的句柄",
  "html_path": "本地 HTML 留档路径（非 failed 出口必有）",
  "degraded": false
}
```

## 工作流

1. **前置门禁（H5）** —— 只发布 `ValidationReport.status == "passed"` 的成稿；任何 error 都不允许进入发布环节。
2. **调用 Facade** —— 唯一入口 `publisher.create_draft(doc, author=..., cover_path=...)`；封面优先级：显式 `cover_path` > `doc.cover_asset`，支持本地文件与 data URI。
3. **按出口分流**：
   - `draft_created`：记录 draft_id，流程正常结束；
   - `degraded`：按 [references/degradation-playbook.md](references/degradation-playbook.md) 处理（人工发布或次日重试）；
   - `failed`：本地磁盘问题，排查 output_dir 权限后重跑发布。
4. **留档（H6）** —— 无论哪个出口，确认 `html_path` 指向的本地副本真实存在，作为审计链的最后一环。

## 规则（Defender 职责）

- 上层代码禁止直接调用 `WeChatClient` / `TokenManager` / `MediaService` / `DraftService`——一律经 `WeChatPublisher`（蓝图十三章）。
- token 失效（errcode 40001/42001）由 `call_with_token_retry` 自动废弃缓存并重试一次；上层不得自建重试循环。
- 远程封面 URL 不在发布层下载：视觉阶段必须先把素材物化为本地文件或 data URI。
- 降级只改变「送达方式」，不改变「内容」——禁止因降级而删改成稿。
- 被 Judge 攻击（错误出口、越权调用微信 API）时，只修复被点名的环节（H3）。

## 参考资料

- [references/degradation-playbook.md](references/degradation-playbook.md)
- [../../references/adversarial-constraints.md](../../references/adversarial-constraints.md)
