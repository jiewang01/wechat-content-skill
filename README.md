# wechat-content-skill

新一代、可扩展、Agent-native 的微信公众号 AI Workflow Skill：从一句话需求到微信草稿箱的完整内容生产流水线。

> **一句话 → 研究 → 写作 → 排版 → 校验 → 微信草稿**

## 架构速览

- **Artifact Flow**：阶段间只传结构化 Artifact（`ResearchResult → ContentBrief → ArticleDraft → VisualPlan → ContentPackage → WechatDocument → ValidationReport → PublishResult`），不传自然语言。
- **Thin Orchestrator + Deep Skills**：根 `SKILL.md` 是薄编排入口（≤150 行），深度规则在各 Sub-Skill。
- **对抗式质量门**：Defender / Attacker / Judge 三角色硬约束（见 [references/adversarial-constraints.md](references/adversarial-constraints.md)），Judge 一律为确定性代码。
- **Targeted Repair**：验证失败只修被命中的节点，最多 3 轮，绝不整篇重写。
- **Graceful Degradation**：搜索 / 图片 / 微信 API 任一失败均有兜底出口；发布不是唯一出口。

完整架构见 [blueprint.md](blueprint.md)，v0.1 落地计划见 [v0.1-implementation-plan.md](v0.1-implementation-plan.md)。

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

# 全量测试（全部离线，无网络依赖）
pytest -q
```

## 真实环境发布

以上链路全部走 mock。要在真实环境完成一次「一句话 → 微信草稿箱」，按 [docs/verification-checklist.md](docs/verification-checklist.md) 执行：环境变量配置（LLM / 搜索 / 图片 Provider 与微信凭证）、账号 YAML、真实链路运行、降级出口验证与安全自检。

## 入口

- **Agent 入口**：根 [SKILL.md](SKILL.md)（编排 6 个 Sub-Skill：research / content / visual / native / layout / publishing）
- **CLI 入口**：`scripts/`（render / validate / lint / preview / export_schemas）
- **编程入口**：`core/workflow/pipeline.py` 的 `load_deps()` + `build_pipeline()`（真实 Provider 装配与全流程编排）

## 仓库结构

| 目录 | 职责 |
|------|------|
| `skills/` | 6 个 Sub-Skill 文档（research / content / visual / native / layout / publishing） |
| `core/` | Artifact 模型、状态机 + Checkpoint、Orchestrator / Pipeline / Repair Loop |
| `renderer/` | 语义 Markdown → ContentAST → 主题化 HTML（LLM 不直接产出 HTML） |
| `validators/` | 质量门：component_lint / Content QA / gzh_validator（确定性代码） |
| `integrations/` | LLM / 搜索 / 图片 Provider（环境变量切换）+ 微信 API Facade |
| `schemas/` | 全部 Artifact 的 JSON Schema |
| `scripts/` | CLI：render / validate / lint / preview / export_schemas |
| `examples/tutorial/` | 首个可复现示例（离线、确定性 run_id） |
| `docs/` | 真实环境验证清单 |
| `accounts/` | 多账号配置示例（只引用环境变量，不落 secret） |
| `references/` | 对抗式约束（H1–H8）等硬约束文档 |
| `tests/` | 全量测试（离线，CI 无网络依赖） |

## 约束

所有实现遵守 [references/adversarial-constraints.md](references/adversarial-constraints.md) 的 H1–H8 硬约束。

## 版本

当前 v0.1.0，变更记录见 [CHANGELOG.md](CHANGELOG.md)。v0.2 范围（多主题、更多写作框架、正式发布、evals）见 [v0.1-implementation-plan.md](v0.1-implementation-plan.md) 第 7 节。

## License

MIT
