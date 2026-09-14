# 更新日志

本项目的显著变更记录于此。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.3.0] - 2026-09-13

表达力、数据回流与去 AI 味迭代：语义标记受控嵌套、发布数据统计、humanize 规则 v2——范围与拆解见 [v0.3-implementation-plan.md](plan/v0.3-implementation-plan.md)。

### 新增

**语义标记受控嵌套（N1）**
- card 成为唯一容器：正文列表项之间可混排 `:::note` / `:::quote` / `:::callout` 子组件块，深度上限 2 层（`MAX_COMPONENT_DEPTH`）；嵌套合法性由 registry 的 `allowed_children` 契约驱动，parser 与 component_lint 同构校验，违例报 `invalid_nesting` 并归属父组件。
- 子组件 node_id 编号 `component_N.M`（容器内出现序号），同样是 Targeted Repair 的定位键；嵌套渲染覆盖全部 5 个主题。
- 「文档即测试」：native 技能文档中的全部 markdown 示例块由 `test_parser.py` 提取并断言可解析 + 往返序列化稳定。

**发布数据统计（N2）**
- datacube 数据统计（`integrations/wechat/datacube.py`）：`getarticletotaldetail` 接口封装，Pydantic 响应模型严格校验（`ArticleTotalDetail` 含按 `stat_date` 逐日展开的 `detail_list[]`，指标覆盖阅读 / 分享 / 在看 / 点赞 / 收藏 / 评论 / 完读率 / 送达率）。
- `scripts/stats.py` CLI：默认查昨日，`--date YYYY-MM-DD` / `--account <name>` 可选；stdout 摘要（每篇文章一行核心指标 + 合计行，发表当日口径），回执幂等落盘 `outputs/stats/<date>_article_stats.json`；退出码 0 成功 / 1 查询失败 / 2 环境配置错误。
- `skills/publishing/SKILL.md` 新增「发布后数据回流」节；`docs/verification-checklist.md` 新增 §9 发布数据统计验证。

**humanize 规则 v2（N3）**
- 新增 3 条 warning 级节奏维度：`connective_density`（连接词密度）/ `opening_monotony`（开头单一化）/ `sentence_length_uniformity`（句长均匀度），与既有 6 维共 9 维（2 error + 7 warning）；共用 CJK≥150 字且句数≥6 门限，短文豁免防误伤。
- 规则版本 1 → 2，旧字段不删不改（向后兼容）；黑名单短语与成对句式清单按 v0.2 观察扩充。

**evals（20 → 27 用例）**
- 27 个用例（humanize 6 / content_gate 4 / render 10 / framework 7）覆盖 16 份语料（新增 `render_nested.md`），14 个测试锁定阈值。

### 工程基线

- ruff 全绿；pytest 383 passed（v0.2 为 324）；evals 27/27 全过。

### 明确不做（推迟至 v0.4）

- 深度 > 2 的嵌套与任意组件互嵌：表达力够用，先观察真实用法。
- 定时自动统计 / 数据看板：stats 保持一次性 CLI 查询 + 回执留档。
- humanize 新语言风格维度（如情感基调、口语化程度）：待积累真实读者反馈。
- Web UI / 性能优化 / i18n：延续 v0.1 决策。

## [0.2.0] - 2026-09-11

内容能力扩展：多主题、7 个写作框架、正式发布与 evals 基准——范围与拆解见 [v0.2-implementation-plan.md](plan/v0.2-implementation-plan.md)。

### 新增

**多主题（1 → 5）**
- 新增 4 个主题：`editorial`（编辑部衬线风）/ `minimal`（极简黑白灰）/ `tech`（科技蓝 + 深色代码块）/ `magazine`（杂志高对比），与 `default` 共 5 个；全部 YAML 驱动（theme / typography / components），切换主题零代码改动。

**写作框架（2 → 7）**
- 新增 5 个框架：`opinion`（观点论证）/ `case-study`（案例复盘）/ `listicle`（清单体）/ `deep-dive`（深度长文）/ `narrative`（叙事文），与 `tutorial` / `news-analysis` 共 7 个；按选题路由，新增框架无需改 Orchestrator。

**正式发布（freepublish）**
- `WeChatPublisher.release(draft_id, ...)`：把草稿箱文章正式群发并轮询至终态（默认 10 次 × 1s），绝不抛出；仅 `publish_state=0` 才返回 `published`（含 `article_url`），其余一律 `degraded`——草稿保留在草稿箱，可再次 release，无需重跑内容管线。
- `load_deps(auto_release=True)`：草稿落位后自动续发；默认关闭，不开启时行为与 v0.1 完全一致（向后兼容）。
- 群发额度约束落档：订阅号每天 1 次、服务号每月 4 次。

**evals（基准回归）**
- 20 个用例（humanize 4 / content_gate 4 / render 5 主题 / framework 7）覆盖 13 份语料（`tests/evals/cases/`），`scripts/run_evals.py` 一键批量回归；13 个测试锁定阈值基线。

**skills/quality/（质量门目录）**
- 校验子技能 SKILL.md + 4 份规则文档（content / component / html / wechat，与 `validators/` 模块一一对应），作为「何时信任哪个门」的唯一权威说明。

**参考文档**
- `references/seo.md`：标题 / 摘要 / 关键词 / 搜一搜收录四节——SEO 是参考，不是质量门。
- `references/content-policy.md`：内容合规红线（敏感内容 / 引用规范 / 免责边界），被 content 与 quality 子技能引用。

**文档修正**
- 根 `SKILL.md`：路由表补 quality 行；CLI 段修正与实现不符的三处（`validate.py` / `lint.py` 参数、移除不存在的 `scripts/publish.py`——发布走库调用）。

### 明确不做（推迟至 v0.3）

- 语义标记嵌套（`:::card` 内嵌 `:::note` 等）：解析器大改，v0.2 不动 parser。
- humanize 规则集大幅迭代：仅随 evals 校准阈值，不新增检测维度。
- Web UI / 复杂 CLI 交互：入口仍是 Agent（SKILL.md）+ `scripts/`。
- 性能优化、并发、缓存、i18n：延续 v0.1 决策。
- 监控告警（发布后数据回流）：仅提供 `status()` 查询；群发数据统计进 v0.3。

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

正式发布 / 群发 / 定时 / 监控、多主题（editorial / minimal / tech / magazine）、更多写作框架（opinion / case-study / listicle / deep-dive / narrative）、`skills/quality/` 目录、evals、SEO、Web UI。详见 [v0.1-implementation-plan.md](plan/v0.1-implementation-plan.md) 第 7 节。
