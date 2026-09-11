---
name: publishing
description: wechat-content-skill 的发布子技能：把校验通过的 WechatDocument 经 WeChatPublisher Facade 落进公众号草稿箱，可选经 freepublish 正式发布并轮询状态；微信 API 不可用时按降级手册以本地 HTML 收尾——发布永远不是流程的唯一出口。
---

# Publishing Skill（发布技能）

## 目标

把一份**校验通过**的成稿安全地送进公众号草稿箱，并可继续**正式发布**（freepublish 群发）。安全的含义：

- 上层永远不碰 access_token / media_id / thumb_media_id / publish_id 等微信细节（蓝图十三章）；
- 无论微信侧发生什么，流程总能以一个本地 artifact 收尾（蓝图十二章：发布不是 Workflow 的唯一出口）。

## 输入 / 输出

- 输入：`WechatDocument`（schemas/wechat_document.schema.json），且必须携带 `status == "passed"` 的 `ValidationReport`（H5 红线）
- 输出：`PublishResult`（schemas/publish_result.schema.json）

```json
{
  "status": "draft_created | published | degraded | failed",
  "media_id": "封面上传返回的素材 id（即 thumb_media_id 来源）",
  "draft_id": "草稿箱 media_id，群发 / 预览的句柄",
  "publish_id": "freepublish 任务 id（仅 release 链路产生）",
  "article_url": "正式文章链接（仅 published 出口）",
  "html_path": "本地 HTML 留档路径（非 failed 出口必有）",
  "degraded": false
}
```

## 工作流

### 草稿链路（默认）

1. **前置门禁（H5）** —— 只发布 `ValidationReport.status == "passed"` 的成稿；任何 error 都不允许进入发布环节。
2. **调用 Facade** —— 唯一入口 `publisher.create_draft(doc, author=..., cover_path=...)`；封面优先级：显式 `cover_path` > `doc.cover_asset`，支持本地文件与 data URI。
3. **按出口分流**：
   - `draft_created`：记录 draft_id，流程正常结束；
   - `degraded`：按 [references/degradation-playbook.md](references/degradation-playbook.md) 处理（人工发布或次日重试）；
   - `failed`：本地磁盘问题，排查 output_dir 权限后重跑发布。
4. **留档（H6）** —— 无论哪个出口，确认 `html_path` 指向的本地副本真实存在，作为审计链的最后一环。

### 发布链路（release，v0.2）

1. **发起** —— `publisher.release(draft_id, media_id=..., html_path=...)`，或管线装配时 `PipelineDeps(auto_release=True)` 在草稿落位后自动续发（不开启时行为与 v0.1 完全一致）。
2. **群发次数约束** —— 公众号群发有硬性额度（订阅号每天 1 次、服务号每月 4 次）：auto_release 默认关闭，正式发布是显式决策；额度耗尽时 submit 会返回 errcode，按降级出口处理，次日凭 draft_id 重新 release 即可，**不需要重跑内容管线**。
3. **状态语义（publish_state）** —— 0 成功（含 article_url）；4 发布中（release 内部自动轮询，默认 10 次 × 1s）；1 审核失败 / 2 原创申明失败 / 3 常见错误，均为终态失败。
4. **按出口分流**：
   - `published`：记录 publish_id 与 article_url，流程结束；
   - `degraded`：草稿仍在草稿箱——可人工在后台发布，或排障后再次 release；
   - 提交前草稿缺失（draft_id 为空）：直接 degraded，不发起任何 API 调用。

## 规则（Defender 职责）

- 上层代码禁止直接调用 `WeChatClient` / `TokenManager` / `MediaService` / `DraftService` / `FreepublishService`——一律经 `WeChatPublisher`（蓝图十三章）。
- token 失效（errcode 40001/42001）由 `call_with_token_retry` 自动废弃缓存并重试一次；上层不得自建重试循环。
- `release()` 绝不抛出：任何 ProviderError 都收敛为 `status="degraded"` + message；发布未确认成功（轮询超时仍在 state=4）同样只算 degraded。
- 远程封面 URL 不在发布层下载：视觉阶段必须先把素材物化为本地文件或 data URI。
- 降级只改变「送达方式」，不改变「内容」——禁止因降级而删改成稿。
- 被 Judge 攻击（错误出口、越权调用微信 API）时，只修复被点名的环节（H3）。

## 参考资料

- [references/degradation-playbook.md](references/degradation-playbook.md)
- [../../references/adversarial-constraints.md](../../references/adversarial-constraints.md)
