# wechat-content-skill

An agent-native workflow skill for creating, designing, and publishing high-quality WeChat Official Account content.

新一代、可扩展、Agent-native 的微信公众号 AI Workflow Skill：从一句话需求到微信草稿箱的完整内容生产流水线。

> **一句话 → 研究 → 写作 → 排版 → 校验 → 微信草稿**

## 架构速览

- **Artifact Flow**：阶段间只传结构化 Artifact（`ResearchResult → ContentBrief → ArticleDraft → VisualPlan → ContentPackage → WechatDocument → ValidationReport → PublishResult`），不传自然语言。
- **Thin Orchestrator + Deep Skills**：根 `SKILL.md` 是薄编排入口（≤150 行），深度规则在各 Sub-Skill。
- **对抗式质量门**：Defender / Attacker / Judge 三角色硬约束（见 [references/adversarial-constraints.md](references/adversarial-constraints.md)），Judge 一律为确定性代码。
- **Targeted Repair**：验证失败只修被命中的节点，最多 3 轮，绝不整篇重写。
- **Graceful Degradation**：搜索 / 图片 / 微信 API 任一失败均有兜底出口；发布不是唯一出口。

完整架构见 [blueprint.md](blueprint.md)，v0.1 / v0.2 落地计划见 [v0.1-implementation-plan.md](v0.1-implementation-plan.md) 与 [v0.2-implementation-plan.md](v0.2-implementation-plan.md)。

## 快速上手（10 分钟，全程离线）

环境要求：Python ≥ 3.11。

```bash
# 1. 安装（含开发依赖）
pip install -e ".[dev]"

# 2. 跑通离线端到端：一句话 → 研究 → 写作 → 排版 → 三层校验 → mock 草稿创建
pytest tests/integration/test_e2e.py -q

# 3. 浏览首个可复现示例（含输入、全部中间 Artifact、最终 HTML）
#    产物逐份讲解见 examples/tutorial/README.md
ls examples/tutorial/run_20260910_001/
```

至此离线链路已跑通。想深入每个环节：

```bash
# 离线重放示例（固定 run_id，确定性输出，不触网）
python examples/tutorial/regenerate.py

# 渲染 ContentPackage 为公众号 HTML（inline CSS，主题驱动）
python scripts/render.py examples/tutorial/run_20260910_001/content_package.json -o wechat.html

# 发布门禁：组件 lint → 渲染 + 定向修复循环（≤3 轮）→ 平台检查，输出结构化 ErrorReport
python scripts/validate.py examples/tutorial/run_20260910_001/content_package.json

# 单产物快速检查（按扩展名分派：draft → Content QA；package → 组件 lint；html → 双层）
python scripts/lint.py examples/tutorial/run_20260910_001/article_draft.json

# evals 基准（20 个用例：humanize / 内容门 / 5 主题渲染 / 7 框架全链路）
python scripts/run_evals.py

# 全量测试（全部离线，无网络依赖）
pytest -q
```

## 能力清单（v0.2）

**主题（5 个，`renderer/themes/`）**：

| 主题 | 风格 |
|------|------|
| `default` | 默认通用 |
| `editorial` | 编辑部衬线风 |
| `minimal` | 极简黑白灰 |
| `tech` | 科技蓝 + 深色代码块 |
| `magazine` | 杂志高对比 |

**写作框架（7 个，`skills/content/frameworks/`）**：`tutorial`（教程）/ `news-analysis`（新闻解读）/ `opinion`（观点论证）/ `case-study`（案例复盘）/ `listicle`（清单体）/ `deep-dive`（深度长文）/ `narrative`（叙事文）。

**正式发布（v0.2）**：`WeChatPublisher.release()` 把草稿箱文章正式群发（内部轮询至终态），或 `load_deps(auto_release=True)` 草稿落位后自动续发；群发额度约束（订阅号每天 1 次 / 服务号每月 4 次）见 [skills/publishing/SKILL.md](skills/publishing/SKILL.md)。

**evals**：20 个用例（humanize 4 / content_gate 4 / render 5 主题 / framework 7）覆盖 13 份语料，`python scripts/run_evals.py` 一键回归，13 个测试锁定阈值。

## 真实环境发布

以上链路全部走 mock。要在真实环境完成一次「一句话 → 微信草稿箱」乃至「正式群发」，按 [docs/verification-checklist.md](docs/verification-checklist.md) 执行：环境变量配置（LLM / 搜索 / 图片 Provider 与微信凭证）、账号 YAML、真实链路运行、正式发布验证（§8）、降级出口验证与安全自检。

## 入口

- **Agent 入口**：根 [SKILL.md](SKILL.md)（编排 7 个 Sub-Skill：research / content / visual / native / layout / quality / publishing）
- **CLI 入口**：`scripts/`（render / validate / lint / preview / run_evals / export_schemas）
- **编程入口**：`core/workflow/pipeline.py` 的 `load_deps()` + `build_pipeline()`（真实 Provider 装配与全流程编排；`auto_release=True` 开启草稿落位后自动发布）

## 仓库结构

| 目录 | 职责 |
|------|------|
| `skills/` | 7 个 Sub-Skill 文档（research / content / visual / native / layout / quality / publishing） |
| `core/` | Artifact 模型、状态机 + Checkpoint、Orchestrator / Pipeline / Repair Loop |
| `renderer/` | 语义 Markdown → ContentAST → 主题化 HTML（5 个主题，LLM 不直接产出 HTML） |
| `validators/` | 质量门：component_lint / Content QA / gzh_validator（确定性代码） |
| `integrations/` | LLM / 搜索 / 图片 Provider（环境变量切换）+ 微信 API Facade（草稿 + 正式发布） |
| `schemas/` | 全部 Artifact 的 JSON Schema |
| `scripts/` | CLI：render / validate / lint / preview / run_evals / export_schemas |
| `examples/tutorial/` | 首个可复现示例（离线、确定性 run_id） |
| `docs/` | 真实环境验证清单（含正式发布 §8） |
| `accounts/` | 多账号配置示例（只引用环境变量，不落 secret） |
| `references/` | 对抗式约束（H1–H8）、SEO、内容合规等参考文档 |
| `tests/` | 全量测试（离线，CI 无网络依赖；含 evals 回归） |

## 约束

所有实现遵守 [references/adversarial-constraints.md](references/adversarial-constraints.md) 的 H1–H8 硬约束。

## 版本

当前 v0.2.0，变更记录见 [CHANGELOG.md](CHANGELOG.md)。v0.2 落地记录见 [v0.2-implementation-plan.md](v0.2-implementation-plan.md)。

## License

MIT
