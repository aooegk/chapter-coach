# 批改：复算、rubric、SQL 与错因

## 两条铁律

1. **客户端分数不是权威。** HTML 的即时反馈只用于体验；客观题必须由 Agent 从 `submission.answers` 复算。
2. **每个扣分点要有证据。** `rubric[].evidence` 必须引用学生原文或明确指出缺失内容，不能只写“不完整”。

## 语义等价优先（避免死扣字眼）

判分看的是**意思是否成立**，不是字符串是否与参考答案一致。以下情况一律接受：

- 同义表述：`任意子串` ≡ `任意多个字符` ≡ `多个字符`（只要语境是“任意数量”）。
- 中英混用：`主键` ≡ `primary key`；`部分函数依赖` ≡ `partial dependency`。
- 符号/写法差异：`<>` ≡ `!=`；`A→B` ≡ `A 决定 B`。
- 语序不同、要点顺序不同、简写与全称。
- 大小写、空格、标点、全角半角差异。

只有**语义确实不成立**时才扣分。例如 `%` 答成“一个字符”是错的，因为那是 `_` 的含义；答成“多个字符”应当接受。拿不准时，按正确处理并在 feedback 中注明“按语义等价接受”，不要为了“严格”牺牲正确性。

填空题默认由 Agent 语义判分；`accepted_answers` 只是提示，不是唯一判据。HTML 端不对填空题做二元判定。

## 每个错题必须给两段

对任何未满分的题，result 中必须有：

- `diagnosis`：**错在哪里**。指出学生答案与正确概念的具体差异，不要只说“回答不完整”。
- `fix`：**怎么改**。给出可执行的修正：正确概念、正确步骤或改正后的 SQL。

只给“参考答案”而不解释错因与改法，视为不合格批改。

## 客观题复算

- `single_choice` / `true_false`：归一化后比较。判断题统一映射：对/正确/true/是 → true，错/错误/false/否 → false。
- `multi_select`：集合相等才满分；若试卷规定了部分得分规则，按规则执行，否则全对才得分。
- `fill_blank`：按 `accepted_answers` 逐空匹配，忽略大小写与首尾空白；多空题按空计分。
- 复算结果与 `client_score` 不一致时：
  - 以复算为准；
  - 在 result 中写 `client_discrepancy`；
  - 在报告中提示“试卷模板的即时反馈可能有误”，必要时修模板。

## 主观题 rubric

逐点执行，不整体印象打分：

1. 列出 `rubric` 每个评分点。
2. 对每点判断 `hit`，并写 `evidence`：
   - 命中：引用学生原句（截断到必要长度）。
   - 未命中：写明缺少什么，例如“未说明事务隔离级别”。
3. `awarded = Σ(weight × hit)`，且 `awarded <= max_score`。
4. 若学生给出了 rubric 未覆盖但正确的等价解法：可以给分，但必须在 `feedback` 中说明并建议把该解法补进参考答案。
5. **不得因为措辞接近参考答案而给分**；只看语义是否满足评分点。
6. 若答案无法判定（表述歧义、OCR 混乱），标 `confidence: low`，给中间分或要求用户补充，不要硬判。

## SQL 题

1. 有 `sql_context.ddl` 时，优先实际执行：
   - 建临时 SQLite 库，导入 `ddl` 与 `rows`；
   - 执行学生 SQL 与参考答案，比较结果集（列名、行集合、排序若题目要求）；
   - 执行报错按 `procedure_error` 处理。
2. 无 sqlite3 或题目未给数据时，退回 rubric，标 `executed: false`，并在报告里注明“未执行验证”。
3. 常见评分点：选对表、JOIN 条件、过滤条件、聚合/分组、去重、排序、空值处理。
4. 不要因为写法不同扣分（子查询 vs JOIN、别名不同），除非题目明确要求。

## 图片作答的批改

先读取附件文件（`media/qNN-1.jpg`），再做判定：

1. 先检查 `capabilities.json.model_vision`。
   - `true` / `unknown` 但模型实际能看图：转写出文字、公式或代码，写入 result 的 `transcript`，再按 rubric 判分。
   - `false` 或读图失败：标 `needs_manual_review: true`，可以给“未判定”而不要猜；在反馈中说明原因。
2. 证据引用 transcript，而不是“图片看起来像”。例如：“你写的第 2 步是 …”。
3. **所有会展示的数学内容都用 `$...$` 包裹**：`transcript`、`rubric[].point`、`rubric[].evidence`、`diagnosis`、`fix`、`feedback`。多行 transcript 逐行包裹；否则 review 页会把它们当普通文本显示。
4. 数学证明/计算：保留公式与步骤，rubric 按步骤命中；字迹不清的步骤标 `confidence: low`。
5. 手写 SQL：先转写再执行验证；转写不确定时 `executed: false`，不要声称已验证。
6. 作图题：按图中可见要素（坐标、标注、结构）判分，并说明“基于图像识别的局限”。
7. 不要把文件名、EXIF、拍摄时间当作作答内容；不要读取与题目无关的隐私信息。

## 错因分类

| error_type | 含义 | 是否影响 mastery |
| --- | --- | --- |
| concept_confusion | 概念混淆、定义记反 | 是 |
| missing_knowledge | 该 KP 完全没掌握 | 是 |
| procedure_error | 步骤/语法/执行顺序错误 | 是 |
| incomplete | 思路对但漏要点 | 是（按比例） |
| careless | 看错题、漏选、单位笔误 | 否 |
| expression | 表述不清但理解正确 | 否 |
| none | 无错误 | — |

只有前三类与 `incomplete` 影响掌握度；`careless` / `expression` 只进错题本与报告，避免把“会但写错”误判为“不会”。

## 输出

写入 `sessions/<quiz_id>/result.json`，必须通过 `schemas/result.schema.json`。字段至少包括：

- 每题 `kp_ids`、`awarded`、`max_score`、`provenance`、`rubric`（含 `hit` 与 `evidence`）
- `error_type`、`feedback`、`review_slides`
- SQL 题额外带 `executed`

结果落盘后，再更新掌握度。不要在批改中途改状态。
