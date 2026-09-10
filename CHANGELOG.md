# 更新日志

本项目的显著变更记录于此。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.0] - 2026-09-10

首个可用版本：从一句话需求到微信草稿箱的完整链路——离线端到端可复现，真实环境按清单验证。

### 新增

**Artifact 流水线**
- 8 个结构化 Artifact 模型（`ResearchResult → ContentBrief → ArticleDraft → VisualPlan → ContentPackage → WechatDocument → ValidationReport → PublishResult`），Pydantic v2 严格校验 + JSON Schema 导出至 `schemas/`。
- 13 状态工作流状态机 + Checkpoint 持久化（`outputs/<run_id>/`）：任意阶段中断后 `resume` 从最近 checkpoint 继续，不重跑已完成阶段。
- 完整 Pipeline 编排（`core/workflow/pipeline.py`）：一句话 → 草稿创建的全流程串联与 `load_deps()` 真实 Provider 装配。

**内容生产 Skills**
- 根 `SKILL.md` 薄编排入口（≤150 行）+ 6 个 Sub-Skill：research / content / visual / native / layout / publishing。
- 2 个写作框架（tutorial / news-analysis），按选题路由，新增框架无需改 Orchestrator。
- humanize 确定性检测器：AI 味黑名单短语 + 句长 / 段落 / 重复指标，规则外置可配置。

**语义渲染**
- 4 种语义标记（`:::note` / `:::quote` / `:::callout` / `:::card`）→ ContentAST → 主题化 HTML；LLM 不直接产出 HTML。
- default 主题（YAML 驱动：theme / typography / components），输出全 inline CSS、零外链。

**质量门与定向修复**
- component_lint：unknown component / missing prop / invalid nesting / unsupported attribute / theme component missing 共 5 类语义标记错误。
- Content QA：结构完整性、字数、AI 味复检（不信任缓存）、引用 ID 一致性。
- gzh_validator：inline CSS 白名单、图片 URL / 尺寸、外部资源、HTML 体积、空节点、坏图等平台检查。
- Targeted Repair：按 node 定位定向修复，上限 3 轮，绝不整篇重写。
- CLI：`scripts/validate.py`（渲染 + 修复循环 + 三层门禁）、`scripts/lint.py`（按扩展名分派单产物检查）、`scripts/render.py`、`scripts/preview.py`。

**集成层（Provider-agnostic）**
- LLM / 搜索 / 图片三个 Provider 接口 + 默认实现（openai_compat / tavily / openai_compat），环境变量切换供应商。
- 微信 API Facade（client / auth / media / draft / publish）：token 缓存与过期刷新，上层零感知细节。
- 多账号配置（`accounts/*.yaml` 只引用环境变量，不落 secret）。
- Graceful Degradation：搜索失败 → 既有 sources 继续；图片三级降级（生成 → 搜索 → 占位图）；微信 API 失败 → 本地 HTML 收尾——发布不是唯一出口。

**工程与文档**
- 全量测试离线运行（含 e2e：mock LLM / 搜索 / 图片 / 微信），CI（ruff + pytest）无网络依赖。
- `examples/tutorial/`：首个可复现示例——固定 run_id、确定性输出，含输入、全部中间 Artifact 与最终 HTML，`regenerate.py` 可一键重放。
- `docs/verification-checklist.md`：真实环境 happy path 人工验证清单（环境变量、账号配置、降级出口、安全自检）。
- `references/adversarial-constraints.md`：Defender / Attacker / Judge 三角色对抗 H1–H8 全程硬约束。

### 明确不做（推迟至 v0.2）

正式发布 / 群发 / 定时 / 监控、多主题（editorial / minimal / tech / magazine）、更多写作框架（opinion / case-study / listicle / deep-dive / narrative）、`skills/quality/` 目录、evals、SEO、Web UI。详见 [v0.1-implementation-plan.md](v0.1-implementation-plan.md) 第 7 节。
