#!/usr/bin/env python3
"""从 quiz.json + result.json + submission.json 生成批改复习页 review.html。

考试模式（exam）不把答案注入试卷，批改后用本脚本生成复习页，
在其中展示参考答案、rubric 命中、错在哪里与怎么改。

用法:
    python build_review.py \
        --quiz   sessions/<quiz_id>/quiz.json \
        --result sessions/<quiz_id>/result.json \
        --submission sessions/<quiz_id>/submission.json \
        --knowledge knowledge/ch03.json \
        --template ../assets/review-template.html \
        --out sessions/<quiz_id>/review.html
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

TYPE_LABELS = {
    "single_choice": "单选", "multi_select": "多选", "true_false": "判断",
    "fill_blank": "填空", "short_answer": "简答", "design": "设计",
    "sql": "SQL", "code": "代码",
    "proof": "证明", "calculation": "计算", "solution": "解答",
    "programming": "编程", "drawing": "作图", "translation": "翻译",
    "essay": "论述", "case_analysis": "案例分析",
}
OBJECTIVE = {"single_choice", "multi_select", "true_false", "fill_blank"}
KNOWLEDGE_ERRORS = {"concept_confusion", "missing_knowledge", "incomplete"}


def load_json(path: Path, optional: bool = False) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        if optional:
            return None
        raise SystemExit(f"[error] 文件不存在: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[error] JSON 解析失败: {path}: {exc}")


def embed_json(obj: object) -> str:
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def replace_block(document: str, elem_id: str, payload: str) -> str:
    pattern = re.compile(
        r'(<script type="application/json" id="%s">)(.*?)(</script>)'
        % re.escape(elem_id),
        re.S,
    )
    replaced, count = pattern.subn(lambda m: m.group(1) + payload + m.group(3), document)
    if count != 1:
        raise SystemExit(f"[error] 找不到或找到多个占位块: {elem_id}")
    return replaced


def display_answer(value) -> str:
    if value is None:
        return "（未作答）"
    if isinstance(value, bool):
        return "正确" if value else "错误"
    if isinstance(value, list):
        return "、".join(display_answer(v) for v in value)
    if isinstance(value, dict):
        return value.get("reference") or value.get("text") or json.dumps(value, ensure_ascii=False)
    return str(value)


def answer_keys(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bool):
        return ["true" if value else "false"]
    if isinstance(value, list):
        return [str(v).strip().lower() for v in value]
    return [str(value).strip().lower()]


def reference_of(question: dict):
    answer = question.get("answer")
    if isinstance(answer, dict):
        return answer.get("reference") or answer.get("text") or json.dumps(answer, ensure_ascii=False)
    return answer


def inject_mathjax(document: str) -> str:
    placeholder = "<!--__MATHJAX__-->"
    if placeholder not in document:
        return document
    asset = Path(__file__).resolve().parent.parent / "assets" / "mathjax-tex-svg.min.js"
    if not asset.exists():
        print("[warn] 未找到 assets/mathjax-tex-svg.min.js，使用轻量渲染器兜底")
        return document.replace(placeholder, "<!-- MathJax asset not bundled -->")
    js = asset.read_text(encoding="utf-8")
    if "</script" in js:
        js = js.replace("</script", "<\\/script")
    return document.replace(placeholder, "<script>\n" + js + "\n</script>")


def build_review(quiz: dict, result: dict, submission: dict | None,
                 knowledge: dict | None, include_correct: bool = False) -> dict:
    questions = {q["id"]: q for q in quiz.get("questions", [])}
    answer_objs = {a.get("qid"): a for a in (submission or {}).get("answers", [])}
    kp_titles = {kp["id"]: kp.get("title", "") for kp in (knowledge or {}).get("knowledge_points", [])}

    items = []
    obj_awarded = obj_max = subj_awarded = subj_max = 0
    knowledge_errors = procedure_errors = other_errors = 0
    total_count = correct_count = 0

    for result_item in result.get("items", []):
        qid = result_item.get("qid")
        q = questions.get(qid, {})
        qtype = q.get("type", "")
        answer_obj = answer_objs.get(qid) or {}
        response = answer_obj.get("response")
        attachments = [
            att.get("path")
            for att in (answer_obj.get("attachments") or [])
            if isinstance(att, dict) and att.get("path")
        ]
        reference = reference_of(q)
        response_text = display_answer(response)
        if attachments and (response is None or str(response).strip() == ""):
            response_text = "见作答图片"

        options = q.get("options")
        if not options and qtype == "true_false":
            options = [{"key": "true", "text": "正确"}, {"key": "false", "text": "错误"}]

        kp_ids = result_item.get("kp_ids") or q.get("kp_ids") or []
        awarded = float(result_item.get("awarded", 0))
        max_score = float(result_item.get("max_score", 0))
        total_count += 1
        fully_correct = awarded >= max_score - 1e-9
        if fully_correct:
            correct_count += 1

        if qtype in OBJECTIVE:
            obj_awarded += awarded
            obj_max += max_score
        else:
            subj_awarded += awarded
            subj_max += max_score

        error_type = result_item.get("error_type")
        if error_type in KNOWLEDGE_ERRORS:
            knowledge_errors += 1
        elif error_type == "procedure_error":
            procedure_errors += 1
        elif error_type in ("careless", "expression"):
            other_errors += 1

        item = {
            "qid": qid,
            "type": qtype,
            "type_label": TYPE_LABELS.get(qtype, qtype.replace("custom:", "") if qtype else ""),
            "stem": q.get("stem", ""),
            "kp_ids": kp_ids,
            "kp_titles": [kp_titles.get(kp, kp) for kp in kp_ids],
            "options": options or [],
            "response": response,
            "response_text": response_text,
            "reference": reference,
            "reference_text": display_answer(reference),
            "reference_keys": answer_keys(reference),
            "response_keys": answer_keys(response),
            "awarded": awarded,
            "max_score": max_score,
            "provenance": result_item.get("provenance"),
            "executed": result_item.get("executed"),
            "rubric": result_item.get("rubric", []),
            "diagnosis": result_item.get("diagnosis", ""),
            "fix": result_item.get("fix", ""),
            "feedback": result_item.get("feedback", ""),
            "attachments": attachments,
            "transcript": result_item.get("transcript", ""),
            "review_slides": result_item.get("review_slides") or q.get("source_slides") or [],
        }
        if include_correct or not fully_correct:
            items.append(item)

    return {
        "quiz_id": result.get("quiz_id") or quiz.get("quiz_id"),
        "title": quiz.get("title") or quiz.get("quiz_id", ""),
        "mode": quiz.get("mode", "practice"),
        "graded_at": result.get("graded_at", ""),
        "score": result.get("score", {"awarded": 0, "max": 0}),
        "summary": {
            "objective_awarded": obj_awarded,
            "objective_max": obj_max,
            "subjective_awarded": subj_awarded,
            "subjective_max": subj_max,
            "knowledge_errors": knowledge_errors,
            "procedure_errors": procedure_errors,
            "other_errors": other_errors,
            "total_count": total_count,
            "correct_count": correct_count,
            "wrong_count": total_count - correct_count,
            "wrong_only": not include_correct,
        },
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成批改复习页")
    parser.add_argument("--quiz", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--submission", type=Path)
    parser.add_argument("--knowledge", type=Path)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--include-correct",
        action="store_true",
        help="结果页也展示答对的题目；默认只显示未满分题",
    )
    args = parser.parse_args()

    quiz = load_json(args.quiz)
    result = load_json(args.result)
    submission = load_json(args.submission, optional=True) if args.submission else None
    knowledge = load_json(args.knowledge, optional=True) if args.knowledge else None

    review = build_review(
        quiz, result, submission, knowledge,
        include_correct=args.include_correct,
    )
    document = args.template.read_text(encoding="utf-8")
    document = document.replace("__TITLE__", html.escape(review["title"]))
    document = replace_block(document, "review-data", embed_json(review))
    document = inject_mathjax(document)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(document, encoding="utf-8")
    print(f"[ok] 已生成 {args.out}")
    print(f"[ok] 得分: {review['score']['awarded']} / {review['score']['max']}")
    print(f"[ok] 结果页题目: {len(review['items'])}（错题 {review['summary']['wrong_count']} / 共 {review['summary']['total_count']}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
