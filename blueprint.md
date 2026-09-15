# WeChat Content Skill — v1 架构蓝图

> **项目定位：** An agent-native content operating system for WeChat Official Accounts.
> **本文档地位：** 本蓝图是 `wechat-content-skill` 的 v1 架构基线，后续所有演进（v0.1 skeleton 落地、功能迭代、重构）均以本文档为准。
>
> **版本：** v1.0
> **状态：** 已采纳（Approved）

---

## 目录

- [核心原则](#核心原则)
- [一、总体架构](#一总体架构)
- [二、Artifact Flow（最重要的架构升级）](#二artifact-flow最重要的架构升级)
- [三、Content Pipeline](#三content-pipeline)
- [四、Humanize：Quality Gate 而非 Prompt](#四humanizequality-gate-而非-prompt)
- [五、Visual Skill](#五visual-skill)
- [六、Native Information Layer](#六native-information-layer)
- [七、Theme Engine](#七theme-engine)
- [八、HTML Renderer](#八html-renderer)
- [九、Quality Gate：整个项目的护城河](#九quality-gate整个项目的护城河)
- [十、Repair Loop](#十repair-loop)
- [十一、Workflow State](#十一workflow-state)
- [十二、Graceful Degradation](#十二graceful-degradation)
- [十三、WeChat API Facade](#十三wechat-api-facade)
- [十四、多账号](#十四多账号)
- [十五、Repository 结构](#十五repository-结构)
- [十六、SKILL.md 设计：薄编排 + 深 Skill](#十六skillmd-设计薄编排--深-skill)
- [十七、端到端 Workflow](#十七端到端-workflow)
- [十八、架构的五个核心特质](#十八架构的五个核心特质)
- [十九、产品层级总览](#十九产品层级总览)

---

## 核心原则

不做「把三个项目代码简单拼起来」，而是抽象成一个 **Agent-native、可测试、可降级、可扩展的公众号内容生产系统**。

> **LLM 做决策与生成，Skill 做编排，References 提供知识，Scripts/Validators 做确定性约束，Adapter 隔离微信 API。**

---

## 一、总体架构

```text
┌──────────────────────────────────────────────────────────────────────┐
│                        WeChat Content Agent                           │
│                                                                      │
│                            SKILL.md                                  │
│                    Agent Entry / Policy / Routing                    │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       Workflow Orchestrator                           │
│                                                                      │
│  Plan → Execute → Validate → Repair → Render → Publish              │
│                                                                      │
│  State / Artifacts / Checkpoints / Retry / Graceful Degradation      │
└───────────────┬──────────────────┬──────────────────┬────────────────┘
                │                  │                  │
                ▼                  ▼                  ▼
      ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
      │    RESEARCH    │ │    CONTENT     │ │     VISUAL     │
      │                │ │                │ │                │
      │ Topic          │ │ Framework      │ │ Cover          │
      │ Discovery      │ │ Outline        │ │ Hero Image     │
      │ Web Search     │ │ Writing        │ │ Illustrations  │
      │ Source Extract │ │ Humanize       │ │ Diagrams       │
      │ Fact Check     │ │ SEO            │ │ Image Search   │
      └───────┬────────┘ └───────┬────────┘ └───────┬────────┘
              │                  │                  │
              └──────────────────┼──────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   CONTENT ARTIFACT      │
                    │                         │
                    │ article.md              │
                    │ metadata.json           │
                    │ sources.json             │
                    │ assets/                 │
                    │ visual-plan.json        │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │  NATIVE INFORMATION     │
                    │                         │
                    │ 微信原生信息模块        │
                    │ Quote / Card / Note     │
                    │ Callout / Reference     │
                    │ Rich Content Blocks     │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │     HTML RENDERER       │
                    │                         │
                    │ Theme Engine            │
                    │ Component System        │
                    │ Inline CSS              │
                    │ Image Embedding         │
                    │ WeChat Compatibility   │
                    └────────────┬────────────┘
                                 │
                                 ▼
             ┌─────────────────────────────────────────┐
             │             QUALITY GATE                │
             │                                         │
             │  ┌─────────────────┐ ┌───────────────┐ │
             │  │ component_lint  │ │ gzh_validator │ │
             │  │                 │ │               │ │
             │  │ Schema          │ │ HTML          │ │
             │  │ Components      │ │ CSS           │ │
             │  │ Attributes      │ │ Image         │ │
             │  │ Structure       │ │ WeChat Rules  │ │
             │  └────────┬────────┘ └──────┬────────┘ │
             │           └──────────┬─────┘          │
             │                      ▼                 │
             │              PASS / REPAIR            │
             └──────────────────────┬──────────────────┘
                                    │
                                    ▼
                    ┌─────────────────────────┐
                    │   WECHAT API FACADE     │
                    │                         │
                    │ Auth / Token            │
                    │ Media Upload            │
                    │ Draft Management        │
                    │ Publish                 │
                    │ Preview                 │
                    │ Account Routing         │
                    └────────────┬────────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
             ┌─────────────┐           ┌─────────────┐
             │    DRAFT    │           │   PUBLISH   │
             │             │           │             │
             │ Save        │           │ Release     │
             │ Preview     │           │ Schedule*   │
             │ Review      │           │ Monitor*    │
             └─────────────┘           └─────────────┘
```

`*` 具体能力根据微信公众号 API 权限而定。

---

## 二、Artifact Flow（最重要的架构升级）

整个系统**不要让 Agent 在步骤之间传「自然语言」**，而是传递**结构化 Artifact**。

> 这是整个架构最重要的升级：最重要的不是目录结构，而是 Artifact Flow。

```text
ResearchResult
       ↓
ContentBrief
       ↓
ArticleDraft
       ↓
VisualPlan
       ↓
ContentPackage
       ↓
WechatDocument
       ↓
ValidationReport
       ↓
PublishResult
```

### 2.1 ResearchResult

```json
{
  "topic": "AI Agent 的下一阶段",
  "intent": "explainer",
  "audience": "AI 从业者",
  "sources": [
    {
      "title": "...",
      "url": "...",
      "credibility": 0.92
    }
  ],
  "facts": [
    {
      "claim": "...",
      "source_ids": ["src_001"]
    }
  ],
  "angles": [
    "...",
    "...",
    "..."
  ]
}
```

Research Skill 只负责：

```text
搜索
↓
阅读
↓
提取
↓
交叉验证
↓
结构化
```

**不要在 Research 阶段直接写完整文章。**

---

## 三、Content Pipeline

Content Skill 接收：

```text
ResearchResult
+
Brand Voice
+
Audience
+
Content Goal
```

处理流程：

```text
ContentBrief
      ↓
Framework Selection
      ↓
Outline
      ↓
Draft
      ↓
Critique
      ↓
Rewrite
      ↓
Humanize
      ↓
Final Article
```

### Framework 不应该写死

```text
frameworks/
├── news-analysis.md
├── tutorial.md
├── opinion.md
├── case-study.md
├── listicle.md
├── deep-dive.md
└── narrative.md
```

Agent 根据选题自动选择：

```text
if topic = 新闻:
    news-analysis

if topic = 教程:
    tutorial

if topic = 案例:
    case-study
```

这样以后增加 `startup-analysis`、`product-review`、`research-summary`、`founder-story` 等新框架时，**不需要改 Orchestrator**。

---

## 四、Humanize：Quality Gate 而非 Prompt

Humanize 不应该只是一个 Prompt，而是一个带检测与评分的闭环：

```text
Draft
 ↓
AI Pattern Detector
 ↓
Rewrite
 ↓
Specificity Check
 ↓
Rhythm Check
 ↓
Final
```

### 检测项：AI 味模式

```text
❌ 首先、其次、最后
❌ 值得注意的是
❌ 在当今...
❌ 不仅...而且...
❌ 总而言之
❌ AI 式总结
```

### 检测项：写作质量

```text
句子长度
段落长度
观点密度
具体案例
个人判断
重复表达
```

### 输出

```json
{
  "humanize_score": 87,
  "issues": [],
  "passed": true
}
```

这样 Humanize 才是一个 **Quality Gate**，而不是另一个 Prompt。

---

## 五、Visual Skill

Visual 不要只做「给文章配几张图」，而应该**先产生结构化的 VisualPlan**，再由 Renderer 消费。

```json
{
  "cover": {
    "style": "editorial",
    "ratio": "2.35:1",
    "prompt": "..."
  },
  "images": [
    {
      "position": 2,
      "purpose": "concept",
      "prompt": "..."
    }
  ],
  "diagrams": [
    {
      "position": 5,
      "type": "flowchart"
    }
  ]
}
```

流程：

```text
Article
   ↓
Visual Planner
   ↓
VisualPlan
   ├── Cover
   ├── Illustration
   ├── Diagram
   └── Screenshot
```

这比让 LLM 写文章时顺便决定图片要成熟很多。

---

## 六、Native Information Layer

这一层**单独做**（这是 `wechat-skill` 思路里非常值得保留的东西）。

不要让 Agent 直接输出 HTML（`<div style="...">`），而是先输出语义化标记：

```markdown
:::note
这是一个重要结论
:::

:::quote
Agent 的核心不是自动化，而是...
:::

:::card
...
:::
```

转换链路：

```text
Semantic Content
       ↓
Native Components
       ↓
Theme
       ↓
HTML
```

例如语义标记：

```text
:::callout type="warning"
不要把所有决策交给 LLM。
:::
```

最终才变成：

```html
<section style="...">
    ...
</section>
```

这样 Theme 可以随时更换。

---

## 七、Theme Engine

Theme 是一等公民：

```text
themes/
├── default/
│   ├── theme.yaml
│   ├── typography.yaml
│   ├── components.yaml
│   ├── imagery.yaml   # 可选：配图风格画像（缺省时用内置默认画像）
│   └── renderer.py
│
├── editorial/
│
├── minimal/
│
├── tech/
│
├── magazine/
│
└── orange-heart/
```

主题配置示例：

```yaml
name: editorial

typography:
  body:
    font_size: 16px
    line_height: 1.8

heading:
  h2:
    font_size: 22px

colors:
  primary: "#111111"
  secondary: "#666666"

components:
  quote: true
  callout: true
  card: true
```

Agent 只说 `theme = editorial`，Renderer 负责具体 HTML。

---

## 八、HTML Renderer

> **强烈建议：LLM 不直接生成最终 HTML。**

正确方式：

```text
Article AST
     ↓
Component AST
     ↓
Theme Engine
     ↓
HTML Renderer
     ↓
wechat.html
```

例如 Article AST 节点：

```json
{
  "type": "heading",
  "level": 2,
  "text": "为什么 Agent 正在改变软件"
}
```

Renderer 处理：

```text
HeadingNode
      ↓
Theme.heading.h2
      ↓
HTML
```

这样可以彻底解决：

```text
HTML 风格漂移
CSS 不一致
微信兼容性
重复 inline style
```

---

## 九、Quality Gate：整个项目的护城河

至少做 **4 层验证**：

```text
                 QUALITY GATE
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
  Content QA      Component QA    HTML QA
       │              │              │
       ▼              ▼              ▼
  Fact Check       Schema         CSS
  Structure        Props          DOM
  Humanize         Nesting        Images
  Readability      Components      Size
       │              │              │
       └──────────────┼──────────────┘
                      ▼
                 Publish QA
                      │
                      ▼
                PASS / REPAIR
```

### 9.1 Content QA

检查：

```text
事实
引用
结构
标题
重复
AI 味
敏感内容
字数
段落
```

### 9.2 Component Lint

检查：

```text
Unknown component
Missing required prop
Invalid nesting
Unsupported attribute
Theme component missing
```

### 9.3 GZH Validator

专门解决微信公众号兼容性：

```text
HTML structure
Inline CSS
Image URL
Image dimensions
Unsupported CSS
External resource
HTML size
Empty node
Broken image
```

---

## 十、Repair Loop

**不要 Validate → Fail → 整篇重新生成。**

正确机制：

```text
Render
  ↓
Validate
  ↓
Error Report
  ↓
Targeted Repair
  ↓
Render
  ↓
Validate
```

Error Report 示例：

```json
{
  "status": "failed",
  "errors": [
    {
      "type": "unsupported_css",
      "node": "component_17",
      "property": "display:grid"
    }
  ]
}
```

Repair Agent 只修改 `component_17`，而不是重新生成整篇文章。

> 这会显著降低 token 消耗和内容漂移。

---

## 十一、Workflow State

整个 Workflow 有明确 State：

```text
INIT
 ↓
RESEARCHING
 ↓
RESEARCHED
 ↓
DRAFTING
 ↓
DRAFTED
 ↓
ANNOTATING
 ↓
ANNOTATED
 ↓
STYLING
 ↓
STYLED
 ↓
IMAGERY
 ↓
RENDERING
 ↓
VALIDATING
 ↓
REPAIRING ──────┐
 ↓               │
VALIDATED ←──────┘
 ↓
READY_TO_PUBLISH
 ↓
UPLOADING
 ↓
DRAFT_CREATED
 ↓
PUBLISHED
```

每一步都产生 checkpoint。Agent 中途挂掉之后可以 **resume**，而不是从头再来。

---

## 十二、Graceful Degradation

（这是 `wechat-article` 设计中值得直接吸收的地方。）

### Web Search 挂了

```text
Research
 ↓
Search unavailable
 ↓
use existing sources
 ↓
continue
```

### 图片生成挂了

```text
Imagery（配图 prompt）
 ↓
LLM 不可用 → 确定性五要素模板兜底（degraded: true）
 ↓
:::figure 占位块（生图 prompt 直接呈现在正文）
 ↓
发布不阻塞；生图后回填 CDN URL 再渲染
```

配图是 prompt-first：占位块本身就是合法产物，渲染 / 校验 / 发布全链路都能带着占位块走通；封面生成推迟到 UPLOADING 阶段按 prompt 兜底，失败时无封面照样建草稿（后续手工补）。

### 微信 API 挂了

```text
Publishing
 ↓
API unavailable
 ↓
export HTML
 ↓
save local artifact
 ↓
manual publish
```

> **发布不是 Workflow 的唯一出口。** 这非常重要。

---

## 十三、WeChat API Facade

最底层不要让 Skill 直接调用微信 API：

```text
WeChatPublisher
        │
        ├── AuthProvider
        ├── MediaService
        ├── DraftService
        ├── PublishService
        └── AccountService
```

上层只需要：

```python
publisher.create_draft(article)
```

而不需要知道 `access_token`、`media_id`、`thumb_media_id`、`author`、`digest`、`content`、`show_cover_pic` 等微信细节——全部封装掉。

---

## 十四、多账号

从第一天就设计多账号支持：

```text
accounts/
├── account-a.yaml
├── account-b.yaml
└── account-c.yaml
```

**不要把 Token 放进 YAML。** 账号配置只引用环境变量：

```yaml
name: Tech Account

env:
  app_id: WECHAT_APP_ID_A
  app_secret: WECHAT_APP_SECRET_A
```

真正的 secret 存放于 Environment / Secret Manager。

---

## 十五、Repository 结构

项目名：**`wechat-content-skill`**

```text
wechat-content-skill/
│
├── SKILL.md
├── README.md
├── LICENSE
├── pyproject.toml
│
├── skills/
│   │
│   ├── research/
│   │   ├── SKILL.md
│   │   └── references/
│   │
│   ├── content/
│   │   ├── SKILL.md
│   │   ├── frameworks/
│   │   ├── writing/
│   │   └── humanize/
│   │
│   ├── visual/
│   │   ├── SKILL.md
│   │   ├── prompts/
│   │   └── references/
│   │
│   ├── native/
│   │   ├── SKILL.md
│   │   └── components/
│   │
│   ├── layout/
│   │   ├── SKILL.md
│   │   ├── themes/
│   │   └── components/
│   │
│   ├── quality/
│   │   ├── SKILL.md
│   │   └── rules/
│   │
│   └── publishing/
│       ├── SKILL.md
│       └── references/
│
├── core/
│   ├── orchestrator/
│   ├── artifacts/
│   ├── state/
│   ├── workflow/
│   └── config/
│
├── renderer/
│   ├── ast/
│   ├── components/
│   ├── themes/
│   └── html/
│
├── validators/
│   ├── content/
│   ├── component/
│   ├── html/
│   └── wechat/
│
├── integrations/
│   ├── wechat/
│   │   ├── auth.py
│   │   ├── media.py
│   │   ├── draft.py
│   │   ├── publish.py
│   │   └── client.py
│   │
│   ├── search/
│   ├── image/
│   └── llm/
│
├── references/
│   ├── writing-guide.md
│   ├── wechat-rules.md
│   ├── seo.md
│   ├── humanize.md
│   └── content-policy.md
│
├── examples/
│   ├── tutorial/
│   ├── news-analysis/
│   ├── case-study/
│   └── opinion/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── evals/
│
├── scripts/
│   ├── render.py
│   ├── validate.py
│   ├── lint.py
│   ├── preview.py
│   └── publish.py
│
└── outputs/
    └── .gitkeep
```

---

## 十六、SKILL.md 设计：薄编排 + 深 Skill

**不要把 3000 行规则全部塞进 `SKILL.md`。** 它应该非常薄，只包含 Purpose / Workflow / Rules / Routing：

```markdown
# WeChat Content Skill

## Purpose

Create, validate and publish high-quality
WeChat Official Account content.

## Workflow

1. Research
2. Plan
3. Write
4. Humanize
5. Design
6. Render
7. Validate
8. Repair
9. Publish

## Rules

- Never invent factual claims.
- Never directly generate final HTML.
- Always validate before publishing.
- Never publish when validation fails.
- Prefer deterministic tools over LLM judgment.
- Preserve artifacts between stages.

## Routing

Research → skills/research/SKILL.md
Content → skills/content/SKILL.md
Visual → skills/visual/SKILL.md
Layout → skills/layout/SKILL.md
Quality → skills/quality/SKILL.md
Publishing → skills/publishing/SKILL.md
```

这就是：

> **Thin Orchestrator + Deep Skills**，而不是 **Mega Prompt**。

---

## 十七、端到端 Workflow

用户只需要说：

> 帮我写一篇「OpenAI Agent 正在如何改变 SaaS」的公众号文章，面向 AI 创业者，偏深度分析，最后放到公众号草稿箱。

Agent 自动执行：

```text
USER
 │
 ▼
Intent Parser
 │
 ▼
Workflow Plan
 │
 ├───────────────┐
 ▼               ▼
Research       Content
 │               │
 ├─ Search       ├─ Framework
 ├─ Sources      ├─ Outline
 ├─ Facts        ├─ Draft
 └─ Fact Check   └─ Humanize
 │               │
 └───────┬───────┘
         ▼
    Visual Plan
         │
         ├─ Cover
         ├─ Images
         └─ Diagram
         │
         ▼
 Native Information
         │
         ▼
   Content AST
         │
         ▼
  Theme Renderer
         │
         ▼
      HTML
         │
         ▼
 ┌─────────────────┐
 │   Quality Gate  │
 │                 │
 │ Content QA      │
 │ Component Lint  │
 │ GZH Validator   │
 └────────┬────────┘
          │
       FAIL
          │
          ▼
    Targeted Repair
          │
          └───────────────┐
                          ▼
                     Quality Gate
                          │
                        PASS
                          │
                          ▼
                  WeChat API Facade
                          │
                          ▼
                     Draft Created
```

---

## 十八、架构的五个核心特质

如果目标是做一个能在 GitHub 上长期发展的项目，核心不是「公众号自动写文章」，而是 **An agent-native content operating system for WeChat Official Accounts**。

### ① Agent-native

```text
SKILL.md
+
Sub Skills
+
References
+
Tools
```

而不是传统 Web App。

### ② Artifact-native

```text
ResearchResult
ContentBrief
Article
VisualPlan
ContentAST
ValidationReport
PublishResult
```

所有阶段可复用、可缓存、可恢复。

### ③ Deterministic-first

```text
LLM
 ↓
Decision
 ↓
Tool
 ↓
Validator
```

而不是：

```text
LLM → "我觉得应该没问题"
```

### ④ Repair-oriented

```text
Error
 ↓
Local Repair
 ↓
Revalidate
```

而不是整篇重写。

### ⑤ Provider-agnostic

LLM 可替换：`OpenAI / Claude / Gemini / Qwen / DeepSeek`
搜索可替换：`Google Search / Bing / Tavily / Exa`
图片可替换：`DALL·E / Flux / Gemini Image`

**核心 Workflow 都不需要动。**

---

## 十九、产品层级总览

```text
                 wechat-content-skill
                         │
             ┌───────────┴───────────┐
             │                       │
       Agent Interface         Programmatic API
             │                       │
             └───────────┬───────────┘
                         │
                  Workflow Engine
                         │
       ┌─────────┬───────┼───────┬─────────┐
       │         │       │       │         │
    Research  Content  Visual  Layout   Publish
       │         │       │       │         │
       └─────────┴───────┼───────┴─────────┘
                         │
                    Artifact Bus
                         │
                 ┌───────┴───────┐
                 │               │
             Validators       Renderer
                 │               │
                 └───────┬───────┘
                         │
                    WeChat Adapter
```
