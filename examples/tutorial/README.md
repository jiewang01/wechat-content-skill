# Tutorial：《缓存穿透》一次完整离线运行

本目录是 v0.1 的**首个可复现示例**：一句话意图经过 13 状态管线，产出全部中间
Artifact、checkpoint 与最终公众号 HTML。全程离线、确定性（时间戳字段除外），
不访问外网、不读取任何凭证。

## 输入

见 [input.json](input.json)：

| 字段 | 值 |
| --- | --- |
| intent | 写一篇讲清缓存穿透的公众号文章 |
| author | 端到端作者 |
| audience | 初中级后端工程师 |
| word_target | 600 |

## 产物：`run_20260910_001/`

建议按管线阶段顺序阅读：

| 文件 | 阶段 | 内容要点 |
| --- | --- | --- |
| `research_result.json` | 研究 | 事实清单（claim + source_ids）、可选切入角、搜索来源 |
| `content_brief.json` | 大纲 | goal / framework / tone / sections（每节 heading + key_points + fact_ids） |
| `article_draft.json` | 写作 | Markdown 初稿 + 去AI味检测（humanize_score） |
| `content_package.json` | 语义稿 | `:::note` 等语义标记 + visual 视觉计划（封面 / 插图，嵌入不单独落盘） |
| `validation_report.json` | 校验 | 内容 / 组件 / 公众号三层门禁的结构化结果 |
| `wechat_document.json` | 渲染 | 最终公众号 HTML（内联样式）+ 纯文本 + 字节数 + 封面 / 插图资产 |
| `publish_result.json` | 发布 | 出口状态 / media_id / draft_id / 本地 HTML 留档路径 |
| `checkpoint.json` | 全程 | 断点续跑元数据 + 三道门禁攻防记录（adversarial_history） |
| `缓存穿透-一次查询如何拖垮数据库.html` | 留档 | 发布 Facade 的本地 HTML 副本（与 wechat_document.html 一致） |

`checkpoint.json` 的 `adversarial_history` 记录三道门禁（content / render / publish），
每条含 Attacker 的 attack_report、Defender 的 defense_report（有修复时）与 Judge 的
verdict；本示例三道门禁均一次 PASS。

> 说明：`publish_result.json` 中的 `media_id=MEDIA-9`、`draft_id=DRAFT-9` 为
> MockTransport 模拟值；真实链路中是微信返回的永久素材 / 草稿 ID。

## 再生成

```bash
python examples/tutorial/regenerate.py
```

脚本复用 `tests/integration/test_e2e.py` 的桩实现：LLM 四段响应全部由
`tests/fixtures/` 的《缓存穿透》故事线派生（fixtures 即文档），微信 API 走
httpx.MockTransport。run_id 固定，重复执行结果一致。

## 深入了解

- 离线端到端断言（产物与 fixtures 逐字锚定）：`tests/integration/test_e2e.py`
- 用真实 LLM / 搜索 / 图片 / 微信账号跑同一条链路：[docs/verification-checklist.md](../../docs/verification-checklist.md)
- 对任意产物单独复检：`python scripts/validate.py run_20260910_001/content_package.json`
