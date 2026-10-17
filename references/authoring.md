# 命题：配置、覆盖计划、题型与质检

题目必须服务三个目标：**覆盖本章考点**、**暴露薄弱点**、**对齐期末考纲**。不要按 slide 顺序平均分配，也不要一次生成后直接交付。

## 第一步：配置闸门（不可跳过）

命题前先让用户确认下面这张表，不要替用户决定，也不要用“上次的配置”直接开跑：

| 项目 | 说明 |
| --- | --- |
| 模式 | `practice` 提交后即时反馈；`exam` 不内嵌答案，批改后生成 review |
| 题数 | 本轮总题数 |
| 题型分布 | 各题型各几题；支持 `custom:<name>` |
| 难度 | 1–5；一套卷内尽量覆盖 2–4 |
| 范围 | 仅当前章，或加入历史章节复习 |

用户说“默认/来一套”时，给出建议值并复述实际配置；只改一项时其余沿用建议值。配置确认后再进入覆盖计划。

## 第二步：覆盖计划

先写 `plan.json`，再动笔出题。

单个 KP 的复习权重：

```
weight = (5 - mastery) × importance × overdue
overdue = clamp(1 + 距 next_due 天数 / 7, 1, 3)
```

- 当前章 KP：`weight × 1.5`
- 历史章 KP：总题量封顶 30%，且至少 1 题来自“已逾期 + mastery ≤ 2”的 KP
- 若某 KP 从未练过：`mastery` 按 2 计
- 用户显式指定题型/题数时，先满足配置，再按权重分配考点

计划里每个 KP 必须写 `reason`，例如：`mastery=1, importance=4, 逾期 5 天`。写不出理由的题不要出。

## 第三步：按学科与考纲选题型

先读 `course.json.exam_blueprint`。题型不是固定的，SQL 只属于数据库/数据类课程，数学课应当出证明与计算。

### 考纲已知（`source = user`）

按蓝图缩放，而不是每套卷都平均分配所有题型：

```
本轮某题型题数 ≈ 本轮总题数 × 该题型在期末中的占比
```

例如期末是 20 单选 + 5 SQL + 3 简答，本轮 10 题 → 约 6 单选 + 2 SQL + 2 简答。四舍五入后修正总和；题数很少时优先保留高分/核心题型。

### 考纲未知（`source = inferred` 或 `unknown`）

从课件内容与学科惯例推断，**不要随机**：

- 公式、推导、定理 → `proof`、`calculation`
- SQL 示例、表结构、关系模式 → `sql`、`design`
- 代码片段、算法 → `programming`、`code`
- 定义、分类、对比 → `single_choice`、`true_false`、`short_answer`
- 图、流程、结构 → `drawing`、`design`
- 语言课 → `translation`、`essay`、阅读理解

推断结果必须明确告诉用户（“以下题型是按课件推断的，你可以改”），不能静默使用。

### 题型注册表

| 题型 | 渲染 | 判分 |
| --- | --- | --- |
| `proof` 证明 | textarea | rubric |
| `calculation` 计算 | textarea（数值结果可确定性校验，过程仍需 rubric） | rubric/hybrid |
| `solution` 解答 | textarea | rubric |
| `sql` | 代码框 + schema/样例数据 | execution_or_rubric |
| `programming` 编程 | 代码框 | execution_or_rubric |
| `drawing` 作图 | textarea 描述步骤（后续可扩展画布） | rubric |
| `translation` / `essay` / `case_analysis` | textarea | rubric |
| 自定义 `custom:<name>` | textarea | rubric |

约束：

- 不得出材料无法支撑的题型：没有 schema/数据就不出 SQL，没有代码就不出编程。
- 单选必须只有一个站得住的答案；多选必须至少两个。
- 填空题不要考无唯一写法的表述；`accepted_answers` 只是提示，批改时仍由 Agent 做语义判定。
- 证明/计算/简答/设计必须给 rubric，权重和等于 `max_score`。
- 难度按 `difficulty` 1–5 标注，一套卷内尽量覆盖 2–4。
- 题干只写问题本身。不要把评分要求、“写出步骤”“只写答案不给分”“本题考查……”之类的内容写进题干；这些属于 rubric 或内部评分规则，放在 `quiz.json` 里。
- 数学公式用 `$...$` 包起来，例如 `$\int_0^1 x e^x\,dx$`；由内联 MathJax 3.2.2（TeX→SVG）按完整 LaTeX 规则渲染，支持分式、根号、矩阵、cases 等，离线可用、不依赖 CDN。字面美元符号写成 `\$`。
- 写 JSON 时注意反斜杠：LaTeX 命令写成 `\\frac`；矩阵/分段的换行 `\\` 写成 `\\\\`。用 Python 生成时避免 `\f`、`\b` 被解释成控制字符，可用 `chr(92)` 或正确的 raw string。构建后打开页面，若出现“公式未能正确渲染”告警，按 MathJax 报错修正。
- 不便打字的题（证明、计算、作图、手写 SQL、长简答）设 `"allow_image": true`，必要时设 `max_attachments`（1–3）。计算题要在题干里要求“写出步骤”，否则 rubric 无法判过程分。

## 第四步：生成约束

- 只加载该 KP 的 `summary` 与对应 slides，不要拿整章上下文硬生成。
- 题干自包含：不得依赖“如上图”“见第 3 页”这类浏览器里看不到的指代。
- 不得使用 PPT 里没有的术语作为必需知识；扩展内容必须标 `source: web | generated` 并在解析中说明。
- 数值、单位、符号与 PPT 保持一致。
- 每题必须写 `source_slides`；写不出页码的题说明它不来自课件，应改标 `generated` 或删除。

## 第五步：质检清单

A 档运行：

```bash
python scripts/validate_quiz.py quiz.json --knowledge .ppt-tutor/knowledge/ch03.json
```

B/C 档逐条人工检查，任何一条不过就重出该题：

1. 单选恰好一个正确项；多选至少两个；答案 key 确实在选项里。
2. 选项互不重叠、不互相蕴含；禁用“以上都对/都不对/全部正确”。
3. 选项长度不泄露答案（正确项明显更长或更短都要改）。
4. 题干不含“正确答案是”“故选”等提示。
5. 无重复题（语义重复也算）；同一 KP 不出两道考同一句话的题。
6. 非 `generated` 题必须有 `kp_ids` 与 `source_slides`，且该页确实支持答案；`generated` 题可以没有 slide 出处，但题干必须自包含。
7. 仅凭本章 PPT 可作答；超纲题标 `web` 且可跳过。
8. SQL 题有 `sql_context.ddl` 与样例数据，参考答案可执行；无数据时不得出结果判定题。
9. rubric 权重之和等于 `max_score`。
10. 自定义题型在 HTML 中有可用的 fallback 渲染（textarea）。

## 常见坏题模式

- “下列说法正确的是”配四个都对的选项。
- 把 PPT 原句挖一个词当填空，但存在多个同义表达。
- 选项里有“以上都是”，且它确实是答案。
- 题干与选项合起来就能推出答案，不需要理解 KP。
- 简答题参考答案是一段泛泛而谈的话，没有可判定的评分点。

出现以上任一情况，重写，不要靠 `explanation` 补救。
