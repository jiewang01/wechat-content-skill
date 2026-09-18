# Evidence 规则

> 来源：BLUEPRINT §6/§7/§10、plan P0-04
> 版本：v1

## 1. 追溯链

任何重要判断必须能够回溯：

```text
Decision
   ↓
Reason
   ↓
Evidence
   ↓
Source
```

禁止出现无法解释来源的判断（BLUEPRINT Rule 03）。

## 2. Evidence type 枚举

| type | 含义 |
|---|---|
| `task_fact` | 广告任务原文中的事实 |
| `account_fact` | 账号画像中的事实 |
| `historical_data` | 历史数据/历史任务表现 |
| `platform_rule` | 平台规则 |
| `brand_requirement` | 品牌方要求 |
| `model_inference` | 模型推断（必须显式标注、不可当作事实） |
| `user_input` | 用户直接输入 |

## 3. reliability 给分指引

`reliability` 表达的是「这个数据源本身可靠吗」，取值 0~1：

| 场景 | 参考值 |
|---|---|
| 任务明写（如广告费 ¥1000） | 0.98 |
| 平台官方规则 | 0.95 |
| 用户人工提供 | 0.90 |
| 历史数据统计 | 0.85~0.95（看样本量） |
| 来源不明的二手信息 | ≤ 0.6 |
| 模型推断 | ≤ 0.5 |

## 4. 缺失信息处理（RULE 05）

缺失信息不能默认为正常：

- 「未写明修改次数」→ 记为 `unknown`，**禁止**解释成「修改次数 = 1」。
- 以 `null` / `status: unknown` 表达，并保留为显式不确定性来源。

## 5. 未来：Evidence Graph

证据不应只是数组，逐步演进为可关联的图结构，支持：

- 判断可追溯
- 结论可解释
- 数据冲突检测
- 历史判断回溯
- Decision Debugging