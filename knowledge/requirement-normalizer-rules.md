# Requirement Normalizer 规则

> 来源：plan §3.3、BLUEPRINT Rule 05
> 版本：v1

## 1. 目标

把任务中的自然语言要求归一到四类：

```text
mandatory  — 必须满足（客户硬性要求、`必须`/`需要`/产品露出等）
optional   — 可选（`可以`/`建议`/加分项）
forbidden  — 禁止（`不得`/`不能`/竞品比较等）
unknown    — 未写明（修改次数、审核轮次等）
```

## 2. 示例

```yaml
requirements:
  mandatory:
    - 产品露出
    - 指定卖点

  optional:
    - 真人出镜

  forbidden:
    - 竞品比较

  unknown:
    - 修改次数
```

## 3. 规则

1. 语义模糊、无法判定 mandatory/optional/forbidden 的要求 → 归入 `unknown`，并记录到 Evidence 的 `uncertainty_reasons`。
2. `unknown` 类必须显式存在，禁止静默忽略。
3. 归一结果必须保留原始原文到 Evidence，保证可追溯（Rule 03）。