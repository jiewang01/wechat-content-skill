# ID 规则

> 来源：BLUEPRINT §23、plan P0-03
> 版本：v1

## 前缀

| 对象 | 前缀 | 示例 |
|---|---|---|
| AdTask | `TASK-` | `TASK-NB-20260918-001` |
| AccountProfile | `ACCOUNT-` | `ACCOUNT-XHS-001` |
| Evidence | `EVD-` | `EVD-20260918-0001` |
| Decision | `DEC-` | `DEC-20260918-0001` |

## 命名格式

```text
TASK-{平台简写}-{YYYYMMDD}-{序号}
ACCOUNT-{平台简写}-{序号}
EVD-{YYYYMMDD}-{序号}
DEC-{YYYYMMDD}-{序号}
```

- 序号起始为 `001`，同一天内递增。
- 平台简写示例：`NB`（新榜）、`XHS`（小红书）、`WX`（公众号）等。

## 规则

1. ID 在全局唯一，一旦生成不可复用。
2. `EVD-*` 与 `DEC-*` 按生成当天日期编号，跨天不连续（不要求全局递增）。
3. 引用关系一律使用完整 ID 字符串，禁止缩写或省略。