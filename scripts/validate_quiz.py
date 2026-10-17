#!/usr/bin/env python3
"""命题质检。退出码 0=通过（可有警告），1=有错误。

用法:
    python validate_quiz.py quiz.json [--knowledge .ppt-tutor/knowledge/ch03.json]

检查项对应 SKILL.md “命题质检”清单与 references/authoring.md。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

KNOWN_TYPES = {
    "single_choice", "multi_select", "true_false", "fill_blank",
    "short_answer", "design", "sql", "code",
    "proof", "calculation", "solution", "programming",
    "drawing", "translation", "essay", "case_analysis",
}
OBJECTIVE = {"single_choice", "multi_select", "true_false"}
SUBJECTIVE = {
    "fill_blank", "short_answer", "design", "sql", "code",
    "proof", "calculation", "solution", "programming",
    "drawing", "translation", "essay", "case_analysis",
}
FORBIDDEN_OPTION_PATTERNS = [
    "以上都", "都不对", "全部正确", "全部错误", "以上均", "以上所述",
]
LEAK_PATTERNS = ["正确答案", "答案是", "应选", "故选"]
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def check_latex_text(tag: str, label: str, text, report: "Report") -> None:
    if not isinstance(text, str) or not text:
        return
    if CONTROL_CHARS.search(text):
        report.error(
            f"{tag}: {label} 含控制字符（很可能是 LaTeX 反斜杠转义错误，"
            f"例如 \\f 被解释成换页符）；请检查 JSON 转义"
        )
    if text.count("$") % 2:
        report.warn(f"{tag}: {label} 中 $ 数量为奇数，可能有未闭合的公式")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def dump(self) -> int:
        for msg in self.errors:
            print(f"[error] {msg}")
        for msg in self.warnings:
            print(f"[warn ] {msg}")
        print(f"\n结果: {len(self.errors)} error(s), {len(self.warnings)} warning(s)")
        return 1 if self.errors else 0


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def norm_bool(value) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    text = normalize(value)
    if text in {"对", "正确", "true", "t", "是", "√"}:
        return "true"
    if text in {"错", "错误", "false", "f", "否", "×", "x"}:
        return "false"
    return text


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise SystemExit(f"[error] 文件不存在: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[error] JSON 解析失败: {path}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="试卷质检")
    parser.add_argument("quiz", type=Path)
    parser.add_argument("--knowledge", type=Path, help="knowledge/chNN.json，用于校验 KP 是否存在")
    parser.add_argument("--course", type=Path, help="course.json，用于读取题型注册表")
    args = parser.parse_args()

    quiz = load_json(args.quiz)
    report = Report()

    for key in ("quiz_id", "chapter_id", "mode", "config", "questions"):
        if key not in quiz:
            report.error(f"缺少顶层字段: {key}")
    questions = quiz.get("questions") or []
    if not isinstance(questions, list) or not questions:
        report.error("questions 必须是非空数组")
        return report.dump()

    if quiz.get("mode") not in ("practice", "exam"):
        report.error("mode 必须是 practice 或 exam")

    cfg = quiz.get("config") or {}
    if cfg.get("count") != len(questions):
        report.warn(f"config.count={cfg.get('count')} 与实际题数 {len(questions)} 不一致")
    type_counts = Counter(q.get("type") for q in questions)
    for qtype, expected in (cfg.get("types") or {}).items():
        actual = type_counts.get(qtype, 0)
        if actual != expected:
            report.warn(f"题型 {qtype} 配置 {expected} 题，实际 {actual} 题")

    known_kps = None
    if args.knowledge:
        knowledge = load_json(args.knowledge)
        known_kps = {kp.get("id") for kp in knowledge.get("knowledge_points", [])}

    allowed_types = set(KNOWN_TYPES)
    if args.course:
        course = load_json(args.course)
        for entry in course.get("type_registry", []):
            if entry.get("type"):
                allowed_types.add(entry["type"])

    seen_ids: set[str] = set()
    seen_stems: dict[str, str] = {}

    for idx, q in enumerate(questions, start=1):
        tag = q.get("id") or f"#{idx}"
        qtype = q.get("type", "")

        for key in ("id", "type", "kp_ids", "source", "source_slides", "stem", "max_score"):
            if key not in q:
                report.error(f"{tag}: 缺少字段 {key}")

        qid = q.get("id")
        if qid:
            if not re.match(r"^q[0-9]{2,}$", str(qid)):
                report.warn(f"{tag}: id 建议使用 q01 形式")
            if qid in seen_ids:
                report.error(f"{tag}: id 重复")
            seen_ids.add(str(qid))

        if qtype not in allowed_types and not str(qtype).startswith("custom:"):
            report.error(
                f"{tag}: 未知题型 {qtype}（请在 course.json type_registry 中登记，"
                f"或使用 custom:<name>）"
            )

        if q.get("source") not in ("ppt", "real_exam", "web", "generated"):
            report.error(f"{tag}: source 必须是 ppt/real_exam/web/generated")

        slides = q.get("source_slides")
        if not isinstance(slides, list):
            report.error(f"{tag}: source_slides 必须是数组")
        elif not slides:
            if q.get("source") != "generated":
                report.error(f"{tag}: source_slides 不能为空（仅 source=generated 可省略）")
            else:
                report.warn(f"{tag}: generated 题无 slide 出处，题干必须自包含")
        elif not all(isinstance(s, int) and s >= 1 for s in slides):
            report.error(f"{tag}: source_slides 必须是正整数数组")

        kp_ids = q.get("kp_ids")
        if not isinstance(kp_ids, list) or not kp_ids:
            report.error(f"{tag}: kp_ids 不能为空")
        else:
            for kp in kp_ids:
                if not re.match(r"^ch[0-9]{2,}\.kp[0-9]{2,}$", str(kp)):
                    report.error(f"{tag}: KP ID 格式错误 {kp}")
                if known_kps is not None and kp not in known_kps:
                    report.error(f"{tag}: KP {kp} 不在 knowledge 文件中")

        max_score = q.get("max_score")
        if not isinstance(max_score, (int, float)) or max_score <= 0:
            report.error(f"{tag}: max_score 必须大于 0")

        stem = q.get("stem") or ""
        if not stem.strip():
            report.error(f"{tag}: 题干为空")
        check_latex_text(tag, "题干", stem, report)
        for opt in (q.get("options") or []):
            if isinstance(opt, dict):
                check_latex_text(tag, "选项", opt.get("text"), report)
        if isinstance(q.get("answer"), dict):
            check_latex_text(tag, "参考答案", q["answer"].get("reference"), report)
        check_latex_text(tag, "解析", q.get("explanation"), report)
        norm_stem = normalize(stem)
        if norm_stem in seen_stems:
            report.error(f"{tag}: 与 {seen_stems[norm_stem]} 题干重复")
        else:
            seen_stems[norm_stem] = tag
        for pat in LEAK_PATTERNS:
            if pat in stem:
                report.error(f"{tag}: 题干疑似泄露答案（包含“{pat}”）")

        if qtype in ("single_choice", "multi_select", "true_false"):
            options = q.get("options")
            if qtype == "true_false" and not options:
                options = [{"key": "true", "text": "正确"}, {"key": "false", "text": "错误"}]
            if not isinstance(options, list) or len(options) < 2:
                report.error(f"{tag}: 选择题至少需要 2 个选项")
                continue
            keys = [str(o.get("key", "")).strip() for o in options]
            texts = [normalize(o.get("text", "")) for o in options]
            if any(not k for k in keys):
                report.error(f"{tag}: 存在空选项 key")
            if len(set(keys)) != len(keys):
                report.error(f"{tag}: 选项 key 重复")
            if len(set(texts)) != len(texts):
                report.error(f"{tag}: 选项文本重复")
            for text in texts:
                for pat in FORBIDDEN_OPTION_PATTERNS:
                    if pat in text:
                        report.error(f"{tag}: 选项包含禁用表述“{pat}”")

            answer = q.get("answer")
            if answer is None:
                report.error(f"{tag}: 缺少 answer")
            elif qtype == "multi_select":
                picked = answer if isinstance(answer, list) else [answer]
                if len(picked) < 2:
                    report.error(f"{tag}: 多选题答案应至少 2 项")
                for key in picked:
                    if str(key) not in keys:
                        report.error(f"{tag}: 答案 {key} 不在选项中")
            elif qtype == "true_false":
                picked = answer if isinstance(answer, list) else [answer]
                if len(picked) != 1:
                    report.error(f"{tag}: 判断题应恰好一个答案")
                elif norm_bool(picked[0]) not in [norm_bool(k) for k in keys]:
                    report.error(f"{tag}: 判断题答案 {picked[0]} 不在选项中")
            else:
                picked = answer if isinstance(answer, list) else [answer]
                if len(picked) != 1:
                    report.error(f"{tag}: 单选题应恰好一个答案")
                if str(picked[0]) not in keys:
                    report.error(f"{tag}: 答案 {picked[0]} 不在选项中")

        if qtype in SUBJECTIVE:
            rubric = q.get("rubric")
            if not isinstance(rubric, list) or not rubric:
                report.error(f"{tag}: 主观题缺少 rubric")
            else:
                total = 0.0
                for point in rubric:
                    if not point.get("point"):
                        report.error(f"{tag}: rubric 存在空评分点")
                    weight = point.get("weight")
                    if not isinstance(weight, (int, float)) or weight <= 0:
                        report.error(f"{tag}: rubric 权重必须大于 0")
                    else:
                        total += weight
                if isinstance(max_score, (int, float)) and abs(total - max_score) > 1e-6:
                    report.warn(f"{tag}: rubric 权重和 {total} != max_score {max_score}")

        if qtype == "sql":
            ctx = q.get("sql_context") or {}
            if not ctx.get("ddl"):
                report.error(f"{tag}: SQL 题缺少 sql_context.ddl")
            if not ctx.get("dialect"):
                report.error(f"{tag}: SQL 题缺少 sql_context.dialect")

    return report.dump()


if __name__ == "__main__":
    raise SystemExit(main())
