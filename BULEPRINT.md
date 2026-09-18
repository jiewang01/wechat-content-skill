# 广告任务自动分析 Skill

## Blueprint v0.1

> 本文是「广告任务自动分析 Skill」的总体设计蓝图与数据契约。
>
> 目标：在后续 Agent、Skill、MCP、Prompt、数据源和自动化流程持续演进的过程中，保持核心模型、决策逻辑和可信度体系不跑偏。

---

# 1. Design Philosophy

## 1.1 Skill 的定位

本 Skill 不是一个单纯的「广告自动接单工具」。

它是一个围绕广告任务形成：

```text
Understand
    ↓
Evaluate
    ↓
Decide
    ↓
Produce
    ↓
Publish
    ↓
Learn
    ↓
Update
```

的 **广告运营决策与内容生产闭环**。

核心目标：

> 帮助运营判断「什么广告值得接、为什么值得接、接了如何低成本做好，以及做完以后如何让下一次判断更准确」。

---

# 2. Core Architecture

整个系统以四个核心数据对象为基础：

```text
                    ┌─────────────────┐
                    │     AdTask      │
                    │   广告任务模型   │
                    └────────┬────────┘
                             │
                             │
                    ┌────────▼────────┐
                    │    Evidence     │
                    │ 事实 / 证据层    │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
      ┌───────▼────────┐          ┌────────▼───────┐
      │ AccountProfile │          │    Decision    │
      │    账号画像     │          │    运营决策     │
      └────────────────┘          └────────────────┘
```

四个对象的职责严格区分：

| 对象               | 解决的问题                |
| ---------------- | -------------------- |
| `AdTask`         | 「这个广告任务是什么？」         |
| `AccountProfile` | 「我的账号是什么样？」          |
| `Evidence`       | 「我们凭什么这么判断？」         |
| `Decision`       | 「基于当前证据，应该采取什么运营动作？」 |

---

# 3. Fundamental Rules

## Rule 01：事实、推断、决策必须分层

禁止：

```text
任务 → LLM判断 → 接单
```

必须：

```text
Raw Data
   ↓
Normalized Data
   ↓
Evidence
   ↓
Analysis
   ↓
Decision
```

---

## Rule 02：Score 不是 Decision

禁止：

```text
Score = 82
因此接单
```

允许：

```text
Decision:
  action: ACCEPT

Reasons:
  - audience_fit 高
  - production_cost 低
  - expected_profit 明确

Score:
  decision_score: 82
```

Score 是辅助运营决策的指标，不是独立的业务事实。

---

## Rule 03：任何关键推断必须可以追溯

例如：

```text
账号匹配度：88
```

必须能够追溯到：

```text
Evidence
 ├── 粉丝人群
 ├── 历史内容
 ├── 历史广告
 └── 同类任务表现
```

不能出现：

```text
account_fit = 88
```

但无法解释为什么是 88。

---

## Rule 04：不确定性必须显式表达

所有预测类数据必须至少包含：

```text
value
confidence
evidence
```

例如：

```yaml
expected_views:
  value: "8000-15000"
  confidence: 0.62
  evidence:
    - EVD-001
    - EVD-008
```

---

## Rule 05：缺失信息不能默认为正常

未知 ≠ 低风险。

例如：

```text
修改次数未知
```

不能自动解释成：

```text
修改次数 = 1
```

应该表达为：

```yaml
revision_rounds:
  value: null
  confidence: 0
  status: unknown
```

---

# 4. Core Model ① — AdTask

## 4.1 定义

`AdTask` 是对新榜广告任务进行标准化后的任务对象。

它描述：

> 广告主希望创作者完成什么，以及完成后能够获得什么商业回报。

---

## 4.2 Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "AdTask",
  "type": "object",
  "required": [
    "task_id",
    "source",
    "brand",
    "campaign",
    "commercial",
    "production",
    "requirements",
    "risk"
  ],
  "properties": {
    "task_id": {
      "type": "string"
    },

    "source": {
      "type": "object",
      "required": ["platform"],
      "properties": {
        "platform": {
          "type": "string"
        },
        "source_url": {
          "type": ["string", "null"]
        },
        "captured_at": {
          "type": "string",
          "format": "date-time"
        }
      }
    },

    "brand": {
      "type": "object",
      "required": ["name"],
      "properties": {
        "name": {
          "type": "string"
        },
        "product": {
          "type": ["string", "null"]
        },
        "category": {
          "type": ["string", "null"]
        }
      }
    },

    "campaign": {
      "type": "object",
      "properties": {
        "objective": {
          "type": ["string", "null"]
        },
        "target_audience": {
          "type": ["string", "null"]
        },
        "content_type": {
          "type": ["string", "null"]
        },
        "key_messages": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "mandatory_points": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "forbidden_points": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      }
    },

    "commercial": {
      "type": "object",
      "properties": {
        "creator_fee": {
          "type": ["number", "null"]
        },
        "commission": {
          "type": ["number", "null"]
        },
        "bonus": {
          "type": ["number", "null"]
        },
        "estimated_total_income": {
          "type": ["number", "null"]
        },
        "settlement_rule": {
          "type": ["string", "null"]
        }
      }
    },

    "production": {
      "type": "object",
      "properties": {
        "deadline": {
          "type": ["string", "null"],
          "format": "date-time"
        },
        "estimated_hours": {
          "type": ["number", "null"]
        },
        "content_format": {
          "type": ["string", "null"]
        },
        "word_count": {
          "type": ["integer", "null"]
        },
        "image_count": {
          "type": ["integer", "null"]
        },
        "video_required": {
          "type": ["boolean", "null"]
        },
        "special_requirements": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      }
    },

    "requirements": {
      "type": "object",
      "properties": {
        "platform_rules": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "brand_review": {
          "type": ["string", "null"]
        },
        "revision_limit": {
          "type": ["integer", "null"]
        },
        "approval_required": {
          "type": ["boolean", "null"]
        }
      }
    },

    "risk": {
      "type": "object",
      "properties": {
        "policy_risk": {
          "type": ["string", "null"]
        },
        "copyright_risk": {
          "type": ["string", "null"]
        },
        "claim_risk": {
          "type": ["string", "null"]
        },
        "account_reputation_risk": {
          "type": ["string", "null"]
        }
      }
    }
  }
}
```

---

# 5. Core Model ② — AccountProfile

## 5.1 定义

`AccountProfile` 描述当前账号的：

```text
人群
+
内容
+
历史表现
+
商业能力
+
生产能力
+
风险边界
```

它不是静态账号介绍，而应该逐渐成为一个：

> **Account Digital Twin / 账号运营数字画像**

---

## 5.2 Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "AccountProfile",
  "type": "object",
  "required": [
    "account_id",
    "platform",
    "audience",
    "content",
    "performance",
    "commercial",
    "production",
    "risk"
  ],
  "properties": {
    "account_id": {
      "type": "string"
    },

    "platform": {
      "type": "string"
    },

    "account": {
      "type": "object",
      "properties": {
        "name": {
          "type": ["string", "null"]
        },
        "category": {
          "type": ["string", "null"]
        },
        "followers": {
          "type": ["integer", "null"]
        }
      }
    },

    "audience": {
      "type": "object",
      "properties": {
        "age_distribution": {
          "type": "object"
        },
        "gender_distribution": {
          "type": "object"
        },
        "location_distribution": {
          "type": "object"
        },
        "interest_tags": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      }
    },

    "content": {
      "type": "object",
      "properties": {
        "niches": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "preferred_topics": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "forbidden_topics": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "content_formats": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "style": {
          "type": ["string", "null"]
        }
      }
    },

    "performance": {
      "type": "object",
      "properties": {
        "avg_views": {
          "type": ["number", "null"]
        },
        "median_views": {
          "type": ["number", "null"]
        },
        "avg_engagement_rate": {
          "type": ["number", "null"]
        },
        "conversion_rate": {
          "type": ["number", "null"]
        },
        "historical_campaigns": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      }
    },

    "commercial": {
      "type": "object",
      "properties": {
        "historical_revenue": {
          "type": ["number", "null"]
        },
        "historical_cpm": {
          "type": ["number", "null"]
        },
        "historical_cpe": {
          "type": ["number", "null"]
        },
        "preferred_categories": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "rejected_categories": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      }
    },

    "production": {
      "type": "object",
      "properties": {
        "avg_production_hours": {
          "type": ["number", "null"]
        },
        "ai_generation_capability": {
          "type": ["string", "null"]
        },
        "available_formats": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      }
    },

    "risk": {
      "type": "object",
      "properties": {
        "brand_risk_tolerance": {
          "type": ["string", "null"]
        },
        "restricted_categories": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "platform_risk_tolerance": {
          "type": ["string", "null"]
        }
      }
    }
  }
}
```

---

# 6. Core Model ③ — Evidence / Confidence

这是整个 Skill 的基础设施层。

## 6.1 为什么单独设计 Evidence

Agent 最容易出现的问题不是不会分析，而是：

> **分析结果看起来合理，但不知道依据是什么。**

因此任何重要判断都必须能够回溯：

```text
Decision
   ↓
Analysis
   ↓
Evidence
   ↓
Source
```

---

# 7. Evidence Model

## 7.1 Evidence

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Evidence",
  "type": "object",
  "required": [
    "evidence_id",
    "type",
    "source",
    "content",
    "reliability"
  ],
  "properties": {
    "evidence_id": {
      "type": "string"
    },

    "type": {
      "type": "string",
      "enum": [
        "task_fact",
        "account_fact",
        "historical_data",
        "platform_rule",
        "brand_requirement",
        "model_inference",
        "user_input"
      ]
    },

    "source": {
      "type": "object",
      "required": ["origin"],
      "properties": {
        "origin": {
          "type": "string"
        },
        "url": {
          "type": ["string", "null"]
        },
        "captured_at": {
          "type": ["string", "null"],
          "format": "date-time"
        }
      }
    },

    "content": {
      "type": "string"
    },

    "data": {
      "type": ["object", "array", "string", "number", "boolean", "null"]
    },

    "reliability": {
      "type": "number",
      "minimum": 0,
      "maximum": 1
    }
  }
}
```

---

# 8. Confidence Model

Confidence 不等于 Evidence Reliability。

二者必须区分。

```text
Evidence Reliability
        ↓
「这个数据源本身可靠吗？」

Confidence
        ↓
「基于现有证据，这个判断有多确定？」
```

例如：

```text
新榜任务明确写明广告费 ¥1000
```

则：

```text
Evidence Reliability = 0.98
Confidence = 0.99
```

而：

```text
预测这篇内容能获得 20,000 阅读
```

即使历史数据非常可靠：

```text
Evidence Reliability = 0.95

Confidence = 0.62
```

因为“历史表现可靠”不等于“未来预测确定”。

---

# 9. Confidence Object

```json
{
  "value": 0.72,

  "level": "medium",

  "status": "estimated",

  "evidence_refs": [
    "EVD-001",
    "EVD-008",
    "EVD-011"
  ],

  "uncertainty_reasons": [
    "历史同类广告样本不足",
    "品牌修改轮次未知"
  ]
}
```

Confidence Level：

```text
0.00 - 0.39 → low
0.40 - 0.69 → medium
0.70 - 0.89 → high
0.90 - 1.00 → very_high
```

注意：

> Confidence 不是准确率。

它只是系统对当前判断确定程度的表达。

---

# 10. Evidence Graph

随着系统发展，Evidence 不应该只是数组，而应该形成关系：

```text
                     ┌──────────────┐
                     │   AdTask     │
                     └──────┬───────┘
                            │
                            ▼
                     ┌──────────────┐
                     │  Evidence    │
                     └──────┬───────┘
                            │
             ┌──────────────┼──────────────┐
             ▼              ▼              ▼
       Account Fit       Cost         Revenue
             │              │              │
             └──────────────┼──────────────┘
                            ▼
                         Decision
```

未来可以进一步演进为：

```text
Evidence Graph
```

实现：

* 判断可追溯
* 结论可解释
* 数据冲突检测
* 历史判断回溯
* Decision Debugging

---

# 11. Core Model ④ — Decision

## 11.1 Decision 的定义

`Decision` 不负责描述任务。

也不负责描述账号。

它回答：

> **在当前证据、当前账号状态和当前运营目标下，应该采取什么行动。**

---

# 12. Decision Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Decision",
  "type": "object",
  "required": [
    "decision_id",
    "task_id",
    "action",
    "decision_score",
    "dimensions",
    "reasons",
    "confidence",
    "evidence_refs"
  ],
  "properties": {
    "decision_id": {
      "type": "string"
    },

    "task_id": {
      "type": "string"
    },

    "action": {
      "type": "string",
      "enum": [
        "accept",
        "observe",
        "reject",
        "need_information"
      ]
    },

    "decision_score": {
      "type": ["number", "null"],
      "minimum": 0,
      "maximum": 100
    },

    "dimensions": {
      "type": "object",
      "properties": {
        "revenue": {
          "type": ["number", "null"]
        },
        "account_fit": {
          "type": ["number", "null"]
        },
        "production_cost": {
          "type": ["number", "null"]
        },
        "opportunity_cost": {
          "type": ["number", "null"]
        },
        "risk": {
          "type": ["number", "null"]
        }
      }
    },

    "reasons": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "statement",
          "evidence_refs"
        ],
        "properties": {
          "statement": {
            "type": "string"
          },
          "evidence_refs": {
            "type": "array",
            "items": {
              "type": "string"
            }
          }
        }
      }
    },

    "blockers": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },

    "next_actions": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },

    "confidence": {
      "type": "object",
      "required": [
        "value",
        "status"
      ],
      "properties": {
        "value": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "status": {
          "type": "string"
        },
        "evidence_refs": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      }
    },

    "evidence_refs": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },

    "created_at": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

---

# 13. Decision Action Model

决策不是二元：

```text
接 / 不接
```

而是：

```text
┌──────────────────┐
│      Decision    │
└────────┬─────────┘
         │
 ┌───────┼──────────────┐
 ↓       ↓              ↓
ACCEPT  OBSERVE       REJECT
         │
         ↓
 NEED_INFORMATION
```

## ACCEPT

当前证据足够支持接单。

## OBSERVE

任务存在价值，但当前不满足立即决策条件。

例如：

```text
收益不错
账号匹配
但品牌修改规则未知
```

## REJECT

当前条件下不值得继续投入。

## NEED_INFORMATION

不是判断“不接”，而是：

> **当前信息不足以形成可靠决策。**

这是非常重要的状态。

---

# 14. Decision Dimensions

初始版本建议只保留五个核心维度：

```text
Revenue
Account Fit
Production Cost
Opportunity Cost
Risk
```

形成：

```text
                 AdTask
                    │
        ┌───────────┼───────────┐
        ↓           ↓           ↓
     Revenue      Fit         Cost
        │           │           │
        └───────────┼───────────┘
                    ↓
             Opportunity Cost
                    ↓
                  Risk
                    ↓
             Decision Score
```

不要一开始加入十几个评分维度。

**维度应该少，但每个维度必须能够解释。**

---

# 15. Decision Score

初始版本可以采用：

```text
Decision Score
=
Revenue Value
×
Account Fit
×
Production Efficiency
×
Risk Adjustment
×
Opportunity Adjustment
```

但这个公式只作为：

> **运营辅助指标**

不能作为业务规则的唯一依据。

特别是：

```text
高分 ≠ 一定接
```

例如：

```text
Decision Score = 92
```

但是：

```text
Risk = blocking
```

仍然可以：

```text
action = reject
```

因此 Decision Engine 必须支持：

```text
Hard Constraint
+
Soft Score
```

---

# 16. Hard Constraint vs Soft Score

## Hard Constraint

任何一个成立都可能直接阻断：

```text
平台禁止
品牌要求无法满足
账号明确拒绝该品类
时间无法完成
法律 / 合规风险不可接受
```

模型：

```text
Hard Constraint
       │
       ├── fail → REJECT
       │
       └── pass
             ↓
          Soft Score
             ↓
          Decision
```

---

# 17. Decision Example

```json
{
  "decision_id": "DEC-20260918-001",
  "task_id": "NB-10086",

  "action": "accept",

  "decision_score": 82,

  "dimensions": {
    "revenue": 85,
    "account_fit": 91,
    "production_cost": 78,
    "opportunity_cost": 70,
    "risk": 82
  },

  "reasons": [
    {
      "statement": "目标人群与账号核心受众高度重合",
      "evidence_refs": [
        "EVD-001",
        "EVD-006"
      ]
    },
    {
      "statement": "历史同类广告平均生产耗时较低",
      "evidence_refs": [
        "EVD-012"
      ]
    }
  ],

  "blockers": [],

  "next_actions": [
    "生成 Campaign Brief",
    "确认品牌审核规则"
  ],

  "confidence": {
    "value": 0.84,
    "status": "high",
    "evidence_refs": [
      "EVD-001",
      "EVD-006",
      "EVD-012"
    ]
  },

  "evidence_refs": [
    "EVD-001",
    "EVD-006",
    "EVD-012"
  ]
}
```

---

# 18. Four Core Objects Relationship

最终形成：

```text
┌─────────────────┐
│     AdTask      │
│  广告任务事实    │
└────────┬────────┘
         │
         │ compare
         ▼
┌─────────────────┐
│ AccountProfile  │
│     账号事实     │
└────────┬────────┘
         │
         │ supported by
         ▼
┌─────────────────┐
│    Evidence     │
│   证据 / 来源    │
└────────┬────────┘
         │
         │ reasoning
         ▼
┌─────────────────┐
│    Decision     │
│     运营决策     │
└─────────────────┘
```

其中：

```text
AdTask
+
AccountProfile
        ↓
    Analysis
        ↓
    Evidence
        ↓
    Decision
```

---

# 19. Skill Runtime Blueprint

未来真正运行时，不应该是一个超级 Agent。

建议：

```text
                    NewBang
                      │
                      ▼
               Task Collector
                      │
                      ▼
                Task Parser
                      │
                      ▼
               ┌────────────┐
               │  AdTask    │
               └─────┬──────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
 Account Analyzer        Economics Analyzer
          │                     │
          └──────────┬──────────┘
                     ▼
              Evidence Builder
                     │
                     ▼
              Decision Engine
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
        ACCEPT    OBSERVE     REJECT
          │          │
          ▼          ▼
      Brief Agent  Info Agent
          │          │
          ▼          └───────┐
     Content Agent           │
          │                  │
          ▼                  │
      Human Review           │
          │                  │
          ▼                  │
       Publish               │
          │                  │
          ▼                  │
    Performance Agent        │
          │                  │
          └──────────┬───────┘
                     ▼
                Learn / Update
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
      Account      Cost       Decision
       Model       Model       Model
```

---

# 20. Data Flow

系统内部统一采用：

```text
RAW
 ↓
NORMALIZED
 ↓
EVIDENCE
 ↓
ANALYSIS
 ↓
DECISION
 ↓
ACTION
 ↓
RESULT
 ↓
LEARNING
```

每一层职责不能混淆。

---

# 21. 禁止的架构演进

后续开发中禁止出现：

### 21.1 把所有东西塞进 SKILL.md

错误：

```text
SKILL.md
 ├── 新榜抓取
 ├── 账号分析
 ├── Prompt
 ├── 评分公式
 ├── 内容模板
 ├── 平台规则
 └── 历史数据
```

正确：

```text
SKILL.md
    ↓
Orchestration / Instructions

Schemas
    ↓
Data Contract

Knowledge
    ↓
Domain Knowledge

Tools
    ↓
External Capabilities

Data
    ↓
Account / Task / Performance
```

---

### 21.2 Agent 直接修改核心数据

Agent 不应该随意修改：

```text
AccountProfile
AdTask
Decision
```

必须经过：

```text
Validation
→
Update
→
Audit
```

---

### 21.3 用 LLM 判断代替数据

错误：

```text
「这个账号看起来很适合母婴广告」
```

正确：

```text
Audience overlap = 78%

Historical similar campaigns:
3

Average performance:
+24% vs account baseline
```

然后 LLM 再进行解释。

---

### 21.4 把预测当事实

禁止：

```text
预计阅读量 15000
```

直接作为事实。

必须：

```text
prediction:
  value: 15000
  confidence: 0.61
  evidence_refs:
    - EVD-001
    - EVD-009
```

---

# 22. Evolution Path

这个 Skill 不应该一开始追求全自动。

建议分四阶段：

## Phase 1 — Decision Assistant

```text
抓任务
 ↓
分析
 ↓
生成 Decision
 ↓
人工接单
```

目标：

> **先验证决策模型是否有价值。**

---

## Phase 2 — Content Copilot

加入：

```text
Decision
 ↓
Brief
 ↓
Draft
 ↓
Human Review
```

目标：

> **验证“接什么 + 怎么做”是否形成生产价值。**

---

## Phase 3 — Closed-loop Operations

加入：

```text
Publish
 ↓
Data
 ↓
Performance
 ↓
Postmortem
```

目标：

> **验证预测与实际之间的误差。**

---

## Phase 4 — Adaptive Agent

最终形成：

```text
Historical Data
       ↓
Model Update
       ↓
Decision Update
       ↓
Production Optimization
       ↓
Performance
       ↓
Historical Data
```

目标：

> **让 Skill 根据真实运营结果持续修正，而不是固定 Prompt。**

---

# 23. Versioning Strategy

四个核心 Schema 必须独立版本化：

```text
AdTask@v1
AccountProfile@v1
Evidence@v1
Decision@v1
```

后续：

```text
AdTask@v1.1
AdTask@v2
```

规则：

### Minor Version

新增非必填字段，不破坏已有数据。

### Major Version

字段语义发生变化、删除字段、改变必填规则时升级。

---

# 24. Minimum Viable Contract

第一阶段实际上只需要保证以下字段：

```text
AdTask
├── task_id
├── brand
├── campaign
├── commercial
├── production
└── requirements

AccountProfile
├── account_id
├── platform
├── audience
├── content
├── performance
└── production

Evidence
├── evidence_id
├── type
├── source
├── content
└── reliability

Decision
├── decision_id
├── task_id
├── action
├── decision_score
├── dimensions
├── reasons
├── confidence
└── evidence_refs
```

**不要为了“未来可能用到”提前设计几十个字段。**

---

# 25. Golden Rule

整个 Skill 后续演进必须遵循：

```text
                ┌──────────────┐
                │    Facts     │
                │ AdTask       │
                │ Account      │
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │   Evidence   │
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │   Analysis   │
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │   Decision   │
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │    Action    │
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │    Result    │
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │    Learn     │
                └──────┬───────┘
                       │
                       └──────────→ Update
```

**任何新增能力，都必须能够回答：**

1. 它属于哪个数据对象？
2. 它产生什么 Evidence？
3. 它影响哪个 Analysis？
4. 它影响哪个 Decision？
5. 它产生什么 Action？
6. Action 完成后产生什么 Result？
7. Result 是否能够反哺模型？

如果无法回答以上问题，就不应该直接加入核心 Skill。

---

# 26. Blueprint End State

最终目标不是：

```text
一个会自动写广告的 Agent
```

而是：

```text
                 ┌─────────────────────┐
                 │   Advertising Pool  │
                 └──────────┬──────────┘
                            ↓
                      Task Understanding
                            ↓
                     Evidence System
                            ↓
               ┌────────────┴────────────┐
               │                         │
        Account Digital Twin       Economics Model
               │                         │
               └────────────┬────────────┘
                            ↓
                      Decision Engine
                            ↓
                    Operational Action
                            ↓
                     Content Production
                            ↓
                         Publish
                            ↓
                       Performance
                            ↓
                         Learning
                            ↓
                 ┌──────────┴──────────┐
                 ↓                     ↓
           Account Model          Decision Model
                 │                     │
                 └──────────┬──────────┘
                            ↓
                       Next Decision
```

最终形成的核心能力是：

> **从“广告任务自动分析”演进成“广告运营决策系统”。**

---

# 27. Current Scope Boundary

v0.1 暂不定义：

* 新榜具体抓取实现
* MCP 工具协议
* 浏览器自动化
* AI 写作 Prompt
* 图片 / 视频生成方案
* 自动发布方案
* 平台具体 API
* 具体评分权重
* 机器学习模型
* 自动接单

这些属于 **Implementation Layer**，不能反过来污染 Core Blueprint。

当前阶段唯一需要优先稳定的是：

```text
AdTask
AccountProfile
Evidence / Confidence
Decision
```

一旦四者的数据契约稳定，后续：

```text
MCP
Agent
Skill
Prompt
Workflow
UI
Database
Analytics
```

均围绕这套 Contract 演进。

---

# 28. One-line Architecture

最终将整个 Skill 浓缩为一句话：

> **以 AdTask 和 AccountProfile 为事实输入，以 Evidence/Confidence 建立可信分析基础，以 Decision 驱动运营行动，以 Result 反哺 Account / Cost / Decision Model，形成可解释、可验证、可持续演进的广告运营 Agent。**
