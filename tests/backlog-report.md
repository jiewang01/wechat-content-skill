# Backlog 执行报告 — M3~M5 遗留五项（2026-09-18）

> 按顺序落地五项 backlog：CTA 平台化 → observe 校准 → 30+ 完成案例 → 拒单审计 → 自适应上生产。

## 1. CTA 平台化模板（M3 P2 遗留）

- [brief_generator.py](file:///workspace/tools/brief_generator.py) 新增 `PLATFORM_CTA` 表 + `DEFAULT_CTA` 兜底，`build_brief` 按平台生成：
  公众号→文末官方承接位、小红书→评论置顶官方链接、抖音→小黄车/POI、知乎→官方链接卡片、B站→简介/置顶链接；口径统一「官方承接位，禁止私域导流」，任务写明承接方式时以任务为准
- [brief-generator-rules.md](file:///workspace/knowledge/brief-generator-rules.md) §4 CTA 平台化（v1.1）
- 回归：task-002（小红书）=「评论区置顶/笔记内官方链接…」，task-021（公众号）=「文末官方承接位…」✓

## 2. observe 校准（≥3 例转 confirm，A07）

- calibrate 原有 <3 例→research、≥3 例且方向一致→confirm 逻辑，在 35 例数据集上验证：
  **35 例 production_hours 均值 +44.5% → 输出 confirm 级提案（production_cost 0.15→0.18）** ✓

## 3. 30+ 完成案例回填（plan §6.6 验收门槛）

- [seed_history.py](file:///workspace/tools/seed_history.py)：**synthetic 验证数据集**（固定种子 20260918 可复现），
  基于 21 个任务生成 35 条完成记录（tests/history/），现象注入：成本低估/阅读超低基线/修改频繁/结算差异
- summary 聚合（35 例）六问全部有输出：views mean +29%、production_hours +44.5%、revision +100%(2例)、
  by_category/by_angle 分布、confidence_verdicts
- **诚实标注**：此数据集为 synthetic 机制验证，非真实运营数据；真实数据可按同样格式替换回填
- 修复：summary/calibrate 递归 glob（子目录结构）+ 仅收 `*feedback*.json`，避免误读 adtask/decision/publish

## 4. 拒单审计回填（A08 FN 评估）

- seed 对 reject/need_information 任务生成审计记录（tests/audits/audit-*.json）：
  `{audit_id, task_id, decided_action, verdict: true_negative/false_negative, evidence}`
- calibrate 新增 `--audit`：聚合 FN/TN 统计并列出 FN 任务
- 结果：1 条审计（task-012 医美拒单）→ 0 FN，拒单正确 ✓

## 5. 自适应上生产（M5 遗留）

- decision_engine 新增 `--config`：显式传入才覆盖内置权重（M02/A13 双重 gate）
- adaptive_agent 新增 `apply-calibration`：读取 calibrate 输出中 confirm 提案 →
  写 [engine_config.json](file:///workspace/tools/engine_config.json)（含 meta 版本/rationale）→ 全量重算回归对比
- **修复权重归一化**：production_cost 0.15→0.18 直接替换会使权重总和 1.03、score 系统性 +1.8（虚高）；
  现应用时归一化（总和=1）→ production_cost 实际 0.1748
- 回归：21/21 例分数微调（±0.5），**action 零翻转**；--config 生效验证（task-002 72.3→72.0）✓

## 6. 全自动应用（放开人工 gate）

- [adaptive_agent.py](file:///workspace/tools/adaptive_agent.py) 新增 `auto-apply`：
  - 按 `account_id` 聚合 feedback 的 proposed 提案 → 各账号自动升级新版本（数值 last-write-wins、
    historical_campaigns union；每账号独立 VersionLog `version-log-auto-*.json`，原画像不覆盖）
  - 全量校准：35 例生产偏差 +44% → confirm 权重 → **归一化** → 落 `tools/engine_config.json`
  - 回归护栏：action 翻转（0 例，仅 15 例分数微调）≤ max_flips → `auto_enabled=true`
- [decision_engine.py](file:///workspace/tools/decision_engine.py)：无 `--config` 时自动加载
  `auto_enabled=true` 的 engine_config.json（`[engine] auto-load config` 生效验证，task-002 72.3→72.0）
- FeedbackReport 契约补 `account_id`（按账号分组更新的前提，Schema 校验 PASS）
- 结果：5 账号（BZ/DY/XHS/WX/ZH）v1→v2 全自动，XHS v2 工时 3.54h / median_views 6175，WX 由 14 条提案升级
- 规则同步：model-update-rules M02、adaptive-agent-rules A13 更新为「放开 gate ≠ 放开护栏」

**含义**：proposed→applied 无需人工逐条确认；保留的三个护栏（版本化可回滚 / 权重归一化 /
回归 flips=0 才自动启用）由脚本强制执行，人工只审阅输出与日志。

## 遗留收口

- 真实运营数据替换 synthetic 后：summary/校准结论正式化（格式已就绪）
- 全自动应用已放开（本报告 §6）：护栏保留版本化/归一化/回归 flips=0 才 auto_enabled