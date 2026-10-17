---
name: ppt-chapter-tutor
description: 基于本地 PPT 逐章学习、讲解与出题批改。当用户要求“用课件/PPT 学某一章”“根据 PPT 出题、小测、复习”“生成章节练习并批改”“整理错题与掌握度”时使用。每个会话只处理一章，支持跨章累计复习。
---

# PPT 章节导师（V1.0）

把一份 PPT 变成“章节讲解 + 可配置试卷 + 浏览器答题 + 可追溯批改 + 本地学习状态”。
一个会话只处理一章；跨章复习通过 `.ppt-tutor/state.json` 完成。

## 一、硬约束

1. **数据真源是 JSON，不是 Markdown。** `state.json` 是掌握度的唯一真源，`wrongbook.md`、报告都只是派生视图。
2. **知识点 ID 必须稳定**：`chNN.kpNN`（如 `ch03.kp07`）。PPT 改名或重新导出时不得改变已有 ID。
3. **HTML 必须单文件自包含**：内联 CSS/JS/数据，零外部请求。`file://` 下 `fetch` 读取本地文件会被拦截。
4. **Answer 数据只能通过受控通道回传**：按 `references/submission.md` 的五级通道依次尝试，读不到就明确要求用户导出/粘贴，绝不猜测或编造作答。
5. **客观题分数由你复算**，HTML 的客户端判分只作即时反馈，不作权威。
6. **按语义判分，不死扣字眼。** 同义表述、中英术语、不同符号写法、语序差异都应接受；填空题尤其不能依赖字符串精确匹配。拿不准时按“学生答对了”处理，并记录理由。
7. **每道非满分题必须写两段**：`diagnosis`（错在哪里，具体指出学生答案与正确概念的差异）和 `fix`（怎么改，给出可执行的修正）。只给参考答案视为不合格。
8. **每轮命题前必须确认配置**：模式（practice/exam）、题数、题型分布。不得静默使用默认值；用户回复“默认”时也要把实际配置写出来。
9. **不得虚构“历年真题”**。每题必须标 `source: ppt | real_exam | web | generated`。
10. **不因措辞接近参考答案而给分**；主观题必须按 rubric 逐点给分并引用学生原文作证据。
11. **题型必须适配学科与期末考纲。** 先读 `course.json.exam_blueprint`；数学不应默认出 SQL，数据库不应默认出证明。不得把某一学科的题型强加给另一门课。
12. **图片只做本地识别。** 未经用户同意不得上传到外部服务；模型读不出图时标 `needs_manual_review`，不得编造识别结果。
13. **题干不写提示。** 不把评分要求、步骤提示、答案范围、“只写答案不给分”等写进题干；rubric 只放在 `quiz.json`，作答时只展示问题本身。
14. **公式必须按 LaTeX 渲染。** 使用 `$...$`；构建时内联 MathJax。出现 `mjx-merror` 或页面告警时必须修正，不能带着渲染错误交付。

## 二、会话生命周期

每个会话严格按四段执行：

1. `load`：读取 `<course>/.ppt-tutor/state.json`、`capabilities.json`、本章 `knowledge/chNN.json`。不存在则初始化。
2. `preflight`：探测运行环境并写入 `capabilities.json`（见 `references/submission.md`）。后续所有分支只读这个结果，不靠猜。
3. `work`：执行主流程 1–7。
4. `commit`：原子写回 `state.json`（先写临时文件再 rename），追加 `attempts/<quiz_id>.jsonl`，重建错题本与报告。

会话开始时若检测到 `state.json` 的 `updated_at` 晚于本会话开始时间，提示用户可能存在并行章节会话，写回前确认。

## 三、目录约定

所有产物放在课程根目录下，随课程文件一起移动：

```
<course>/
  ch01.pptx
  .ppt-tutor/
    capabilities.json
    course.json          # 课程画像：学科 + 期末考纲题型 + 题型注册表
    state.json
    knowledge/ch01.json
    extracted/ch01.md
    extracted/ch01.meta.json
    sessions/<quiz_id>/
      plan.json
      quiz.json
      exam.html
      review.html
      media/q09-1.jpg
      submission.json
      result.json
      report.md
    attempts/<quiz_id>.jsonl
    wrongbook.md
```

`<quiz_id>` 格式：`<yyyymmdd>-<chNN>-<两位序号>`，全 ASCII。

> 路径基准：`scripts/`、`assets/`、`schemas/`、`references/` 均相对**本技能目录**；`.ppt-tutor/` 相对**课程根目录**。调用脚本时先定位技能目录，不要假设当前工作目录就是课程目录。

### 课程画像 `course.json`（首次会话建立，之后复用）

第一次处理某门课时，先确认这两件事，再进入章节学习：

1. **学科**：例如数学、数据库、操作系统、英语。
2. **期末考试题型**：有哪些题型、各多少题/多少分、是否闭卷、时长。

处理规则：

- 用户知道考纲 → `exam_blueprint.source = "user"`，按用户给的题型和分值建立蓝图。
- 用户不知道 → 从 PPT 内容与学科惯例推断，`source = "inferred"`，并明确告诉用户：“以下题型是按课件推断的，你可以改。”
- 两者都没有 → `source = "unknown"`，本轮按课件能支撑的题型出，下一轮再确认。

`course.json` 同时保存 `type_registry`（题型注册表）。核心题型之外，学科特有题型按需登记，例如：

| 学科 | 常见题型 |
| --- | --- |
| 数学 | 证明 `proof`、计算 `calculation`、解答 `solution` |
| 数据库 | SQL `sql`、关系模式设计 `design`、范式判断 |
| 编程 | 编程 `programming`、改错、代码阅读 |
| 英语 | 翻译 `translation`、阅读、写作 `essay` |
| 文科 | 简答 `short_answer`、论述 `essay`、案例分析 `case_analysis` |

蓝图只决定**默认分布**，不锁死每轮配置；用户在配置闸门里仍可改题型和题数。

### 图片作答（可选）

适用于证明、计算、作图、手写 SQL、简答等不便打字的题。题目加 `"allow_image": true`（`max_attachments` 默认 3）。

链路：

1. HTML 提供“上传图片 / 拍照”，浏览器内压缩到最长边 2000px 的 JPEG。
2. 图片以 base64 随 `submission.answers[].attachments` 回传。
3. localhost 接收器自动解码到 `sessions/<quiz_id>/media/qNN-1.jpg`；下载/剪贴板通道用 `scripts/extract_attachments.py` 解码。
4. 批改时先看 `capabilities.json.model_vision`：
   - 能读图 → 识别出文字/公式/代码写入 `transcript`，再按 rubric 判分。
   - 不能读图 → 标 `needs_manual_review: true`，不要凭空猜。
5. 图片仅本地处理；不要读取与作答无关的隐私内容。

注意：图片不写入 localStorage 草稿（容量限制），提交前不要关闭页面。

## 四、能力分级

启动时判定，不要假设所有平台能力相同：

| 档位 | 条件 | 可用能力 |
| --- | --- | --- |
| A | 有 Python 3 | 完整：pptx 抽取、题目校验、SQL 执行、localhost 接收器、Word 导出 |
| B | 无 Python，有解压/文本工具 | 抽取降级为 XML 直读或 LibreOffice→PDF；校验改为逐条人工检查；SQL 走 rubric |
| C | 无浏览器自动化，也无脚本运行时 | 下载/剪贴板回传；由用户手工提供文本或作答 |

**不要因为处于 B/C 档就静默降低质量**：明确告诉用户哪些能力不可用、哪些结论是 rubric 推断而非执行验证。

## 五、主流程

### 0. 预检

探测：OS、Python、浏览器自动化（MCP）、默认下载目录、剪贴板读取命令（`pbpaste` / `Get-Clipboard` / `clip` / `xclip`）。
结果写入 `capabilities.json`，格式见 `schemas/capabilities.schema.json`。

### 1. 摄取（Ingest）

- 先看 `extracted/chNN.meta.json` 的 `sha256`：未变化则直接复用，不重复解析。
- 抽取顺序：`python-pptx` → 直接读 `ppt/slides/*.xml` 与 `ppt/notesSlides/*.xml` → LibreOffice 转 PDF 后抽文本。
- 必须抽取：正文、表格、**备注页**（常含真正的知识点）。
- 纯图片/图表页单独列入 `image_only_slides`；若当前模型不能看图，明确告知“第 X 页无法解析”，不要跳过不提。
- 清洗目录页、致谢页、纯复习页；合并跨页重复内容。
- 详细规则见 `references/ingest.md`。

### 2. 建立知识点

- 从抽取文本生成 `knowledge/chNN.json`，每个 KP 含 `id/title/slides/summary/importance/prerequisites`。
- 映射必须落到 slide 号；后续每道题都要能反查 `source_slides`。
- 用户确认或修正知识点划分后再进入出题；不要跳过确认直接生成大量题目。

### 3. 章节讲解

- **先总览**：只从 `knowledge/chNN.json` 生成，每个 KP 1–2 句 + slide 号，控制在可一屏读完。
- **按需深入**：用户追问某个 KP 时，才读取该 KP 对应 slide 的原文，不要一次把整章塞进上下文。
- 讲解中标注“PPT 原文未覆盖、以下为补充”，补充内容标 `source: web` 或 `generated`。

### 4. 配置闸门（命题前必须执行）

每轮命题前，先给用户一张紧凑配置表，等确认后再生成。**不得静默使用默认值。**

| 项目 | 选项 | 建议默认 |
| --- | --- | --- |
| 模式 | practice（提交后即时反馈）/ exam（不内嵌答案） | practice |
| 题数 | 1–30 | 8 |
| 题型分布 | 单选/多选/判断/填空/简答/SQL/证明/计算/编程/自定义 | 由 `exam_blueprint` 按题数缩放；无蓝图时按课件推断 |
| 难度 | 1–5 | 3 |
| 范围 | 仅本章 / 含历史复习 | 仅本章；有逾期 KP 时建议含复习 |

- 用户回复“默认/来一套”时，采用建议值，但仍要在消息中写出实际配置，不能省略。
- 用户只改其中一项时，其余沿用建议值。
- 自定义题型用 `custom:<name>` 登记，HTML 渲染为 textarea。
- 校验：题型分布之和 = 总题数；题数 > 0；每题分值合理。
- 模式含义与答案下发方式见 `references/submission.md`：
  - `practice`：HTML 可内嵌答案，提交后显示即时反馈，但最终以 Agent 复算为准。
  - `exam`：HTML 剥离 `answer/rubric/explanation/accepted_answers/expected_rows`，批改后生成 `review.html`。

### 5. 命题（三段式，不得跳过）

1. **覆盖计划** `plan.json`：按 `(5 - mastery) × importance × 逾期因子` 选 KP；当前章权重 ×1.5；历史章题量封顶 30%。每个 KP 记录选题理由。
2. **逐点生成**：只加载该 KP 的摘要与对应 slides，生成题目。题型、难度、分值按配置。
3. **质检**：运行 `scripts/validate_quiz.py`（A 档）或逐条执行 `references/authoring.md` 的清单（B/C 档）。不通过就重出该题，不要带病交付。

质检项至少包括：单选唯一正确、选项不互斥、禁用“以上都对/都不对”、题干不泄答案、无重复题、每题有 `kp_ids` 与 `source_slides`、仅凭本章 PPT 可答、SQL 题有 DDL 与样例数据。

### 6. 生成并打开试卷

- `scripts/build_exam.py` 把 `quiz.json` 与提交配置注入 `assets/exam-template.html`，写出 `sessions/<quiz_id>/exam.html`。
- 构建时会把 `assets/mathjax-tex-svg.min.js` 内联进 HTML（约 2.1MB），按完整 LaTeX 规则渲染 `$...$`；资产缺失时回退轻量渲染器。
- `mode: practice`（内嵌答案、提交后即时反馈）或 `mode: exam`（不内嵌答案）。
- 打开后**必须结束本轮并交还用户**，明确说：
  “已生成试卷。答完点提交，然后回来告诉我‘已完成’，或把下载的文件路径/JSON 发给我。”
  不要轮询等待，不要假设用户已经答完。

### 7. 读取作答并校验

按 `references/submission.md` 的五级通道依次尝试。读到后先校验：

- `quiz_id` 与本卷一致；
- `schema_version` 可识别；
- 每题 qid 在本卷中存在且不重复；
- 时间戳合理（`submitted_at >= started_at`）。

校验失败就要求用户重新提交，不进入批改。

### 8. 批改

- **客观题**：从 `submission.answers` 复算，与客户端分数比对；不一致时以复算为准并记录 `client_discrepancy`。
- **主观题 / SQL / 设计题**：按 rubric 逐点判定，每点必须有 `hit` 和 `evidence`（引用学生原文）。
- **SQL**：有 sqlite3 且题目带 `sql_context` 时执行比对结果集；否则退回 rubric，并在结果中标注 `executed: false`。
- 区分 `error_type`：`concept_confusion | missing_knowledge | procedure_error | careless | expression | incomplete`。
  **只有知识类错误影响掌握度**，笔误/表达问题只记录不扣 mastery。
- 允许部分得分；总分不得超过 `max_score`。详细规则见 `references/grading.md`。

### 9. 更新状态与报告

- 按 `references/review.md` 的规则更新每个 KP 的 `mastery/streak/sessions_correct/next_due/error_types`。
- 原子写回 `state.json`，追加 attempts JSONL。
- A 档可用 `scripts/apply_result.py` 完成确定性记账（掌握度、attempts、报告、错题本）；**评分本身仍由你完成**，不要把这个脚本当成评分器。
- 重建 `wrongbook.md`（按 KP 分组，附 slide 号与证据）和 `sessions/<quiz_id>/report.md`。
- 每轮批改后默认生成 `review.html`（参考答案、rubric 证据、错在哪里、怎么改、作答图片与识别结果）；`exam` 模式必须生成。
- 报告可导出 HTML；Word 仅在 A 档且用户要求时生成。
- 最后向用户汇报：得分、逐题结果、掌握度变化、下次复习建议。不要只丢一个总分。

## 六、错误处理

- 浏览器打不开：改用“用户手动打开 + 下载/剪贴板回传”，不要卡在启动浏览器上。
- 下载目录未知或被策略禁用：切换到剪贴板通道；仍失败则让用户粘贴 JSON。
- JSON 损坏/截断：要求重新提交，不要尝试“修复后猜测”。
- PPT 加密、损坏、无文本：明确报告，并提供“用户导出 PDF/文本”的降级路径。
- 任何环节无法完成时，说清“哪一步、为什么、用户可以怎么做”，不要静默降级。

## 七、参考文件

按需加载，不要一次全部读入：

- `references/ingest.md` — PPT 抽取与清洗
- `references/authoring.md` — 覆盖计划、题型、命题与质检
- `references/grading.md` — 复算、rubric、SQL、错因分类
- `references/review.md` — 掌握度与跨章复习算法
- `references/submission.md` — 预检、五级回传通道、校验
- `references/reporting.md` — 报告与错题本格式
- `schemas/*.json` — 数据契约（含 `course.schema.json`）
- `assets/exam-template.html` — 单文件试卷模板
- `assets/review-template.html` — 批改复习页模板
- `scripts/*.py` — A 档可选工具（缺失时按 B/C 档执行）
  - `extract_pptx.py`、`build_exam.py`、`validate_quiz.py`、`receive_submission.py`
  - `extract_attachments.py` — 下载/剪贴板通道：把 submission 里的 base64 图片落盘
  - `build_review.py` — 由 quiz/result/submission 生成文本化的批改复习页
  - `apply_result.py` — 应用 result.json：更新状态、attempts、报告、错题本
