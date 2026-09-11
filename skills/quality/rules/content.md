# 内容门规则 —— `validators/content/qa.py`

入口：`lint_content(draft, research=None, brief=None, rules=None) -> list[ValidationIssue]`

检查对象是 `ArticleDraft`（文本层），与标记 / HTML 无关；`rules` 可覆盖默认 humanize 规则（缺省加载 `skills/content/humanize/rules.yaml`）。

## 四类检查

| 检查 | issue type | severity | 判定条件 | 定位 |
|------|-----------|----------|----------|------|
| 结构完整 | `structure_incomplete` | error | 标题为空 / 正文为空 / 正文无标题行 | `node="draft"`，`property="title"` 或 `"markdown"` |
| 字数一致 | `word_count_mismatch` | error | 声明 `word_count` 与实际估算的偏差超过容差 | `property="word_count"` |
| 字数偏薄 | `word_count_below_target` | warning | 实际字数低于 `brief.word_target` 的 50% | `property="word_count"` |
| AI 味 | `ai_flavor_{kind}` | error / warning | 见下节映射表 | `property` = 命中证据文本 |
| 引用溯源 | `unknown_source_ref` | error | 事实引用的 source_id 不在 research 来源登记表 | `node=fact_id`，`property=source_id` |
| 引用溯源 | `unknown_fact_ref` | error | draft.fact_ids 或 brief.sections[].fact_ids 引用了不存在的事实 | `node="draft"` / `"section_N"`，`property=fact_id` |

细节：

- 标题行判定：`^#{1,6}[ \t]+\S`（多行模式），`#` 到 `######` 均可，`#` 后必须有空格
- 字数按 `estimate_word_count` 重新估算，**不信任** `draft.word_count` 自报值；容差 = `max(20, round(实际字数 × 0.05))`
- `word_count_below_target` 在 brief 为空或正文为空时跳过
- 引用类检查仅在传入 `research` 时执行

## AI 味映射（ai_flavor_*）

lint 内部重跑 `skills/content/humanize` 的检测器 —— **不信任** draft 缓存的 `humanize` 报告。
检测结果逐条映射为 `ai_flavor_{kind}`，severity 与检测器一致：

| kind | severity | 扣分 | 判定 |
|------|----------|------|------|
| `blacklist_phrase` | error | −8/次 | 命中 23 个黑名单短语（首先，/其次，/值得注意的是/赋能/抓手/闭环/底层逻辑……全表见 rules.yaml） |
| `paired_phrase` | error | −8 | 命中 4 组套话对（不仅…而且 / 随着…的发展 / 在这个…的时代 / 扮演着…角色） |
| `long_sentence` | warning | −3 | 单句超过 60 字 |
| `avg_sentence_length` | warning | −5 | 平均句长超过 35 字（至少 3 句才统计） |
| `long_paragraph` | warning | −3 | 单段超过 200 字 |
| `repetition` | warning | −5 | 5 字 n-gram 重复出现 ≥ 3 次 |

humanize 评分：起始 100，按上表扣减后夹在 [0, 100]，`passed = score ≥ 60`（pass_score）。
全部阈值集中在 `skills/content/humanize/rules.yaml`，调整只改该文件。

## 信任时机

- 初稿完成、进入视觉规划前执行；evals 的 `content_gate` 套件（好文零 error、结构缺失文必检出 `structure_incomplete`）回归此行为
- 通过 = 文本层达标，**不代表可发布**（仍需过组件 / HTML / 公众号门）
- 管线中 error → 抛 `ContentGateError`，gate 记为 `content`
