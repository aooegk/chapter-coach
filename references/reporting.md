# 报告与错题本

## 数据流

```
submission.json + quiz.json
        ↓ 批改
result.json
        ↓ 更新
state.json + attempts/<quiz_id>.jsonl
        ↓ 派生
sessions/<quiz_id>/report.md
wrongbook.md
（可选）report.html / report.docx
```

Markdown 与 HTML 都是**派生视图**，不得作为后续计算的输入。

## review.html 只显示错题

默认只收录 `awarded < max_score` 的题；答对的题不展开，只在摘要里给出“答对 X / 共 Y 题”。需要完整回顾时用 `build_review.py --include-correct`。

结果页不显示正确题，不代表记录丢失：原始作答在 `submission.json`，图片在 `media/`，逐题记录在 `attempts/*.jsonl`。

## report.md 结构

```markdown
# 第三章 小测报告

- 试卷: 20261017-ch03-01
- 模式: practice
- 时间: 2026-10-17 19:00–19:15
- 得分: 12 / 15（80%）
- 数据来源: 下载通道 submission.json

## 总体

- 客观题 9 / 10
- 主观题 3 / 5
- 知识类错误: 2；表达/笔误: 1

## 逐题

### q01 单选（2/2）✓
- 考点: ch03.kp01 函数依赖
- 你的答案: B
- 解析: ...

### q05 SQL（3/4）△
- 考点: ch03.kp04
- rubric:
  - [x] JOIN 条件正确（2/2）证据: `a.id = b.aid`
  - [ ] 去重正确（0/1）缺少 DISTINCT
- 建议回看: PPT 第 21 页

## 掌握度变化

| KP | 之前 | 现在 | 下次复习 |
| --- | --- | --- | --- |
| ch03.kp01 | 2 | 3 | 2026-10-24 |
| ch03.kp04 | 1 | 0 | 2026-10-18 |

## 下一步

1. 优先重看 ch03.kp04（函数依赖 → 范式判断）
2. 3 天内做一次 5 题小测，只考 kp04
```

要求：

- 每条错题都带 `review_slides`。
- 主观题必须展示 rubric 命中情况与证据。
- SQL 题注明 `executed: true/false`；未执行时说明是 rubric 推断。
- 不堆砌鼓励性套话；用户要的是定位问题。

## wrongbook.md 结构

按 KP 分组，而不是按时间堆叠：

```markdown
# 错题本

## ch03.kp04 范式判断（mastery 0，错 3 次）

### 2026-10-17 20261017-ch03-01 q05（3/4）
- 题目: ...
- 你的答案: ...
- 问题: 缺少 DISTINCT；对 1NF/2NF 的边界判断混淆
- 回看: PPT 第 21–22 页
- 错因: concept_confusion

### 2026-10-10 20261010-ch03-01 q03（0/2）
...
```

重建规则：

- 每次批改后整体重建，保证按 KP 聚合；
- 从 `attempts/*.jsonl` 与 `result.json` 读取，不解析旧 Markdown；
- 同一题重复错多次要合并展示，不要复制多份。

## 报告导出

- **Markdown**：始终生成，作为默认交付。
- **HTML**：把 report.md 渲染为单文件 HTML（可复用简单样式），便于浏览与打印。
- **Word**：仅 A 档且用户明确要求时生成。优先用 python-docx；失败就用 Word COM；都不可用则明确说明并交付 Markdown/HTML。
- 文件放 `sessions/<quiz_id>/`，不要把临时文件写到系统目录。

## 汇报给用户

最后一条消息至少包含：

1. 得分与正确率；
2. 错在哪几个 KP，各自对应哪些 slide；
3. 掌握度变化与下次复习时间；
4. 本轮数据实际走的是哪个回传通道（便于排查）。

不要只给一个总分，也不要把报告全文粘进对话。
