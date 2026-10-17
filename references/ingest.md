# PPT 摄取与知识点划分

## 目标

从课件产出三个东西，缺一不可：

1. `extracted/chNN.md` — 可反复阅读的文本（正文 + 表格 + 备注）
2. `extracted/chNN.meta.json` — hash、页数、图片页清单、是否有备注
3. `knowledge/chNN.json` — 稳定 ID 的知识点及其 slide 映射

## 抽取链（按能力降级）

### A 档：python-pptx

```bash
python scripts/extract_pptx.py ch03.pptx --chapter-id ch03 --out .ppt-tutor
```

抽取内容必须包括：

- 文本框正文（含组合形状内的文本）
- 表格（转 Markdown）
- **备注页** `notes_slide`，常含真正的讲解与考点
- 图片页识别：文本少于 15 字且含图片 → 记入 `image_only_slides`

### B 档：无 python-pptx

```bash
# 解压后直接读 XML
unzip -o ch03.pptx -d /tmp/ch03
# 正文在 ppt/slides/slideN.xml，备注在 ppt/notesSlides/notesSlideN.xml
# 用任意 XML/文本工具剥出 <a:t> 文本节点
```

或：

```bash
soffice --headless --convert-to pdf ch03.pptx --outdir /tmp
pdftotext -layout /tmp/ch03.pdf /tmp/ch03.txt
```

注意：PDF 路径会丢失页与页的对应关系，必须重新标注 slide 号；备注页也不会被导出，需单独说明“备注未纳入”。

### C 档：无可用工具

要求用户提供以下任一：导出的 PDF、逐页文本、或直接把关键内容粘贴进对话。明确告知“本次不包含图片页与备注页”。

## 清洗规则

抽取后、划分知识点前，逐条处理：

- 丢弃：封面、目录、致谢、纯章节过渡页、纯复习页（内容与前面重复）。
- 合并：跨页连续的一段内容、同一表格被拆到两页。
- 保留：slide 号；后续所有引用都靠它回溯。
- 术语统一：中英文混排时保留 PPT 原词，括号补常用译名，不擅自改写定义。
- 公式/代码页：保留原文与缩进；排版错乱时标注“原页为公式/代码，文本抽取可能失真”。
- 图片页：不能解析就明确列出页码，不要假装已经读懂。

## 知识点划分

一条 KP 应当满足：

- 是一个**可独立考查**的概念、方法或结论；
- 对应 1–5 页 slides，通常以一个小节标题为中心；
- 能写出一句不含糊的 `summary`；
- 有 `importance`（1–5），用于出题加权；
- 有 `prerequisites`（可跨章），用于讲解顺序与错因归因。

约束：

- 每章建议 5–12 个 KP。过少会粗到无法定位薄弱点，过多会让复习调度碎片化。
- ID 一旦分配不再改动：`ch03.kp01`、`ch03.kp02`……增补内容用新 ID，不要重排。
- PPT 重新导出导致页号变化时，更新 `slides`，保留 ID。
- `knowledge/chNN.json` 必须通过 `schemas/knowledge.schema.json`。

## 缓存与失效

`meta.json` 记录 `sha256`。每次开始时比对：

- 相同 → 直接复用 `extracted` 与 `knowledge`，不重新解析。
- 不同 → 重新抽取；`knowledge` 保留原 ID，仅更新页号与新增内容，并在报告中提示“课件已更新，历史掌握度仍按 KP ID 延续”。

## 验收

- 随机抽 3 个 KP，能仅凭 `slides` 指到的页面复述其要点。
- 每页至少归属一个 KP，或明确列入“非考点页”。
- 图片页清单非空时，已向用户说明处理方式。
