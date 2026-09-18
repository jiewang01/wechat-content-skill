# Decision Dimension — Risk 规则

> 来源：BLUEPRINT §14、plan §4.4
> 版本：v1

## 1. 风险五类（初始版）

```text
Platform Risk
Brand Risk
Claim Risk
Copyright Risk
Account Reputation Risk
```

## 2. 判定要点

| 信号 | Risk 得分为低分（高风险）的依据 |
|---|---|
| 品类敏感度 | 金融 / 医美 / 财富 / 保健等强监管品类 ⇒ 基准分下调至 50-60 |
| compliance 信号 | adtask.requirements.approval_required / brand_review（法务/合规审核）⇒ 流程风险+，但审核本身是保护 |
| 宣称风险 | claim_risk 已标注（禁止功效/绝对化表述）⇒ 内容合规压力 |
| 政策风险 | policy_risk 已标注 ⇒ 高风险（50-） |
| 账号声誉 | "不伤粉"等要求或 fan-lost 风险 ⇒ 中性偏下 |
| 版权 / 授权 | 授权范围、素材版权要求明确 ⇒ 中性；不明确 ⇒ +uncertainty |

## 3. 输出

- `dimensions.risk`：0-100，**分越高风险越低**（让 Risk 与其余四维方向一致参与加权）。
- 高敏感品类（金融/医美）且无任何合规保护信号时，Risk ≤ 40，若同时触发 Hard Constraint ⇒ REJECT。