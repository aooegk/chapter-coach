# 掌握度与跨章复习

## 掌握度更新（每次 quiz 结束后，按 KP 聚合）

对每个出现在本卷中的 KP：

```
全部相关题正确  → mastery += 1
存在知识类错误  → mastery -= 1
只有 careless/expression 错误 → 不变
mastery = clamp(mastery, 0, 5)
```

- 同一 KP 在一卷内多题时按“是否全部正确”聚合，不按题数累加，避免刷题快速拉满。
- `attempts` 累加题目数；`correct` 累加正确题数；`streak` 在全部正确时 +1，否则归零。
- `sessions_correct`：本次该 KP 全部正确则 +1，否则不变。
- `last_seen` 写本次日期。
- `error_types` 累加本次的错因计数。

### 掌握判定

```
mastered = mastery >= 4 且 sessions_correct >= 2
```

不要用“连续答对次数”单独判定，跨会话才算。

## 复习间隔

按更新后的 mastery 映射 `next_due`：

| mastery | 间隔 |
| --- | --- |
| 0 | 1 天 |
| 1 | 2 天 |
| 2 | 4 天 |
| 3 | 7 天 |
| 4 | 15 天 |
| 5 | 30 天 |

`next_due = 今天 + 间隔`。若本次有知识类错误，间隔取上一档（更早复习）。

## 复习选题

```
weight = (5 - mastery) × importance × overdue
overdue = clamp(1 + 距 next_due 天数 / 7, 1, 3)
```

- 当前章：`weight × 1.5`
- 历史章：按 weight 降序取，但总题量不超过配置的 30%
- 至少保证：每卷有 1 题来自“已逾期”的 KP（若存在）
- 若历史章 KP 与当前章有 `prerequisites` 关系，优先纳入

### 示例

配置 10 题，当前章 ch04 有 6 个 KP：

1. 先给当前章分配 ≥70% 题量（7 题），按 weight 分配到 3–4 个 KP。
2. 历史章最多 3 题；从 ch01–ch03 中按 weight 选 2–3 个 KP。
3. 若某个历史 KP `overdue > 2` 且 `mastery <= 2`，至少给它 1 题。
4. 剩余题量回到当前章最高 weight 的 KP。

## 并行会话

`state.json` 只有一个。若用户在两个会话里同时学两章：

- 写回前检查 `updated_at` 是否晚于本会话开始时读取的值；
- 若已变化，重新读取并合并：按 KP 取 `last_seen` 较晚的记录，不要整文件覆盖；
- 无法安全合并时，把冲突的 KP 写入 `attempts/` 并在报告中提示用户，不要静默丢数据。

## 不做什么

- 不因一次满分就把 mastery 提到 5。
- 不因一次失误就把 mastery 清零。
- 不让“表达不清”拉低掌握度。
- 不用 Markdown 错题本反推状态；所有计算只读 `state.json`。
