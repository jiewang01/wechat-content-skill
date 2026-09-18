# Evidence Policy

> 适用范围：全链路（Stage 2 产出，Stage 4/5/6 消费）。Evidence 是全 Skill 的「一等公民」。

## 1. 定义：事实层 vs 观点层

```text
事实层（可以写成 evidence）：发生了什么 / 谁说了什么 / 数据是多少 / 产品何时发布
观点层（禁止写成 evidence）："我认为……" / "xx 很热门" / "用户肯定需要"
```

判断标准：一条陈述能否被独立核实？能 → evidence；不能 → 观点，需要降级为 finding 的 `signals` 并标注低置信，或者丢弃。

## 2. 统一结构

所有阶段复用同一结构（见 `schemas/research-finding.yaml` 的 `evidence` 定义）：

```yaml
source:       来源名称 / URL
source_type:  news | product | community | discussion | search_trend | official_doc | analytics | social | other
date:         YYYY-MM-DD；未知填 unknown
claim:        可验证的事实陈述
confidence:   高 | 中 | 低
```

## 3. 使用要求

- 每个**重要**结论（支撑选题、评分、insight 的判断）至少 1 条 evidence。
- 无证据支撑的信号：必须在对应字段标注性或字段级别注明 `confidence: low`，且不得作为评分的高分依据。
- evidence 在 Candidate → Ranking → Top1 → Brief 全链路随选题流动（`source_signals` 保证可追溯），不允许中途丢失来源。

## 4. 置信度分级

| 级别 | 判定 |
|---|---|
| high | 官方文档 / 一手数据 / 权威媒体报道，且时间新鲜、来源具体 |
| medium | 高信誉社区讨论 / 二次转述，或来源次权威，或时间略旧 |
| low | 单一来源 / 无法核对日期 / 含推测成分；只能作为弱信号 |

## 5. 冲突处理

- Evidence 冲突：**同时保留双方**（Evidence A / Evidence B），分别保留各自 source 与 confidence，不武断选取一方当作事实；冲突本身可作为 content_gap 或选题风险记录。
- 时效冲突（旧数据 vs 新数据）：优先新近且 confidence 更高的一方，但保留旧的备查。

## 6. 禁止行为

- 为补足数量而编造来源 / 日期；
- 把观点写成事实；
- 用模型记忆冒充检索结果（同 research-policy §2）。

---

## 7. 微信生态优先原则

针对**微信公众号内容赛道**的 evidence 采集优先级：

### 7.1 数据源优先级矩阵

| 优先级 | 来源类型 | 示例 | 权重系数 |
|--------|---------|------|---------|
| **P0** | 微信搜一搜收录的文章 | 任何在搜一搜首页能看到的公众号文章 | 1.0 |
| **P1** | 头部公众号实测/原创 | 粉丝 50w+ 账号的原创深度文 | 0.9 |
| **P2** | 行业媒体转载 | 少数派/鸟哥笔记/人人都是产品经理等 | 0.8 |
| **P3** | 权威官方媒体 | 新华社/人民日报/工人日报等公众号 | 0.85 |
| **P4** | 用户评论/留言原话 | 文章评论区的高赞提问 | 0.7 |
| **P5** | 第三方数据平台 | 新榜/清博/西瓜数据 | 0.75 |
| **P6** | 外部补充源 | 知乎/小红书/Reddit（仅用于交叉验证） | 0.6 |

### 7.2 强制要求

每个 `research_finding` 必须满足以下证据结构：

```yaml
evidence:
  - priority: P0/P1  # 至少 1 条 P0-P2 级别的微信生态证据
    source: "公众号名称"
    article_title: "文章标题"
    pub_date: "YYYY-MM-DD"
    view_count: "10w+"  # 如可见
    like_count: 500   # 点赞数
    credibility_tier: A/B/C/D
    excerpt: "用户原话或关键结论引用"
  - priority: P3~P6  # 可选补充源
    ...
```

### 7.3 饱和度判断规则

基于微信搜一搜结果的客观指标：

```text
very_low: 搜一搜显示 < 100 篇相关结果
low: 100 ~ 500 篇，且无头部垄断
medium: 500 ~ 2000 篇，有 2~3 个号长期产出
high: 2000 ~ 5000 篇，同质化严重
very_high: > 5000 篇，爆款标题模式高度重复
```

**禁止**使用「我感觉」「大概」等主观描述替代上述量化指标。

### 7.4 竞品扫描清单

每个 finding 需标注已扫描的对标账号：

```yaml
competitor_scan:
  scanned_accounts: ["账号 1", "账号 2", "账号 3"]  # 至少 3 个
  scan_period: "近 3 个月"
  key_insights:
    - "账号 1 的 Top10 高阅读集中在 X 类选题"
    - "账号 2 的评论区高频问题是 Y"
    - "账号 3 的标题多用数字型 + 反常识句式"
```