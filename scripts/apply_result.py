#!/usr/bin/env python3
"""把批改结果落到状态、attempts、报告与错题本。

只做确定性的记账，不做主观评分。输入 result.json 必须是 Agent 已完成批改的结果。

用法:
    python apply_result.py \
        --result   sessions/<quiz_id>/result.json \
        --quiz     sessions/<quiz_id>/quiz.json \
        --knowledge knowledge/ch03.json \
        --submission sessions/<quiz_id>/submission.json \
        --state    state.json \
        --session  sessions/<quiz_id> \
        --course-id db-2026 \
        --today 2026-10-17

行为:
- 按 KP 聚合更新 mastery/attempts/correct/streak/sessions_correct/next_due
- 同一 quiz_id 只应用一次（state.applied_quizzes 去重）
- attempts/<quiz_id>.jsonl 幂等重写，不产生重复行
- 重建 wrongbook.md（读取所有 attempts 行）
- 生成 report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

KNOWLEDGE_ERRORS = {"concept_confusion", "missing_knowledge", "procedure_error", "incomplete"}
INTERVAL_DAYS = {0: 1, 1: 2, 2: 4, 3: 7, 4: 15, 5: 30}
OBJECTIVE = {"single_choice", "multi_select", "true_false", "fill_blank"}
TYPE_LABELS = {
    "single_choice": "单选", "multi_select": "多选", "true_false": "判断",
    "fill_blank": "填空", "short_answer": "简答", "design": "设计",
    "sql": "SQL", "code": "代码",
    "proof": "证明", "calculation": "计算", "solution": "解答",
    "programming": "编程", "drawing": "作图", "translation": "翻译",
    "essay": "论述", "case_analysis": "案例分析",
}


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise SystemExit(f"[error] 文件不存在: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[error] JSON 解析失败: {path}: {exc}")


def write_json_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def kp_default(title: str) -> dict:
    return {
        "title": title,
        "mastery": 2,
        "attempts": 0,
        "correct": 0,
        "streak": 0,
        "sessions_correct": 0,
        "error_types": {},
    }


def init_state(knowledge: dict, course_id: str) -> dict:
    knowledge_map = {}
    for kp in knowledge.get("knowledge_points", []):
        knowledge_map[kp["id"]] = kp_default(kp.get("title", ""))
    return {
        "schema_version": "1.0",
        "course_id": course_id,
        "mastery_rule": "v1",
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "applied_quizzes": [],
        "knowledge": knowledge_map,
        "config_defaults": {},
    }


def response_map(submission: dict | None) -> dict:
    if not submission:
        return {}
    return {a.get("qid"): a.get("response") for a in submission.get("answers", [])}


def display_response(value) -> str:
    if value is None:
        return "（未作答）"
    if isinstance(value, list):
        return "、".join(str(v) for v in value)
    return str(value)


def display_answer(qtype: str, value) -> str:
    if qtype == "true_false":
        if value is True or str(value).strip().lower() == "true":
            return "正确"
        if value is False or str(value).strip().lower() == "false":
            return "错误"
    return display_response(value)


def apply_result(state: dict, result: dict, quiz: dict, today: date) -> list[str]:
    quiz_id = result.get("quiz_id")
    applied = state.setdefault("applied_quizzes", [])
    if quiz_id in applied:
        return [f"[warn] quiz {quiz_id} 已应用过，跳过掌握度更新"]

    questions = {q["id"]: q for q in quiz.get("questions", [])}
    by_kp: dict[str, list[dict]] = defaultdict(list)
    for item in result.get("items", []):
        q = questions.get(item.get("qid"), {})
        for kp in item.get("kp_ids") or q.get("kp_ids") or []:
            by_kp[kp].append(item)

    for kp, items in by_kp.items():
        ks = state["knowledge"].setdefault(kp, kp_default(""))
        ks["attempts"] += len(items)
        fully_correct = all(
            float(i.get("awarded", 0)) >= float(i.get("max_score", 0)) - 1e-9
            for i in items
        )
        if fully_correct:
            ks["correct"] += len(items)
            ks["streak"] += 1
            ks["sessions_correct"] += 1
            ks["mastery"] = min(5, ks["mastery"] + 1)
        else:
            ks["streak"] = 0
            errors = [
                i.get("error_type")
                for i in items
                if i.get("error_type") in KNOWLEDGE_ERRORS
            ]
            if errors:
                ks["mastery"] = max(0, ks["mastery"] - 1)
            for err in errors:
                ks["error_types"][err] = ks["error_types"].get(err, 0) + 1
        ks["last_seen"] = today.isoformat()
        ks["next_due"] = (today + timedelta(days=INTERVAL_DAYS[ks["mastery"]])).isoformat()

    applied.append(quiz_id)
    state["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    return []


def attempt_lines(result: dict, quiz: dict, submission: dict | None, today: date) -> list[dict]:
    questions = {q["id"]: q for q in quiz.get("questions", [])}
    answer_objs = {a.get("qid"): a for a in (submission or {}).get("answers", [])}
    lines = []
    for item in result.get("items", []):
        q = questions.get(item.get("qid"), {})
        answer_obj = answer_objs.get(item.get("qid")) or {}
        attachments = [
            att.get("path") for att in (answer_obj.get("attachments") or [])
            if isinstance(att, dict) and att.get("path")
        ]
        lines.append({
            "quiz_id": result.get("quiz_id"),
            "date": today.isoformat(),
            "qid": item.get("qid"),
            "type": q.get("type"),
            "kp_ids": item.get("kp_ids") or q.get("kp_ids") or [],
            "stem": (q.get("stem") or "")[:200],
            "response": answer_obj.get("response"),
            "attachments": attachments,
            "transcript": item.get("transcript", ""),
            "awarded": item.get("awarded"),
            "max_score": item.get("max_score"),
            "error_type": item.get("error_type", "none"),
            "diagnosis": item.get("diagnosis", ""),
            "fix": item.get("fix", ""),
            "feedback": item.get("feedback", ""),
            "review_slides": item.get("review_slides") or q.get("source_slides") or [],
        })
    return lines


def rewrite_attempts(session_root: Path, quiz_id: str, lines: list[dict]) -> None:
    attempts_dir = session_root.parent.parent / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)
    path = attempts_dir / f"{quiz_id}.jsonl"
    existing = []
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if row.get("quiz_id") != quiz_id:
                existing.append(row)
    with path.open("w", encoding="utf-8") as fh:
        for row in existing + lines:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def all_attempts(session_root: Path) -> list[dict]:
    attempts_dir = session_root.parent.parent / "attempts"
    rows = []
    if not attempts_dir.exists():
        return rows
    for path in sorted(attempts_dir.glob("*.jsonl")):
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                rows.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return rows


def build_report(result: dict, quiz: dict, submission: dict | None,
                 knowledge: dict, state: dict) -> str:
    questions = {q["id"]: q for q in quiz.get("questions", [])}
    answer_objs = {a.get("qid"): a for a in (submission or {}).get("answers", [])}
    kp_titles = {kp["id"]: kp["title"] for kp in knowledge.get("knowledge_points", [])}

    total_awarded = float(result["score"]["awarded"])
    total_max = float(result["score"]["max"])
    pct = (total_awarded / total_max * 100) if total_max else 0

    obj_awarded = obj_max = subj_awarded = subj_max = 0
    knowledge_errors = []
    procedure_errors = []
    other_errors = []
    for item in result.get("items", []):
        q = questions.get(item.get("qid"), {})
        is_obj = q.get("type") in OBJECTIVE
        if is_obj:
            obj_awarded += float(item.get("awarded", 0))
            obj_max += float(item.get("max_score", 0))
        else:
            subj_awarded += float(item.get("awarded", 0))
            subj_max += float(item.get("max_score", 0))
        et = item.get("error_type")
        if et in ("concept_confusion", "missing_knowledge", "incomplete"):
            knowledge_errors.append(item.get("qid"))
        elif et == "procedure_error":
            procedure_errors.append(item.get("qid"))
        elif et in ("careless", "expression"):
            other_errors.append(item.get("qid"))

    lines = [
        f"# {quiz.get('title') or quiz.get('quiz_id')} 报告",
        "",
        f"- 试卷：{result.get('quiz_id')}",
        f"- 模式：{quiz.get('mode', 'practice')}",
        f"- 作答通道：{submission.get('channel') if submission else '未提供'}",
    ]
    if submission and submission.get("duration_sec") is not None:
        sec = int(submission["duration_sec"])
        lines.append(f"- 用时：{sec // 60} 分 {sec % 60} 秒")
    lines += [
        f"- 批改时间：{result.get('graded_at', '')}",
        f"- 得分：**{total_awarded:g} / {total_max:g}（{pct:.1f}%）**",
        "",
        "## 总体",
        "",
        "| 类别 | 得分 |",
        "| --- | --- |",
        f"| 客观题 | {obj_awarded:g} / {obj_max:g} |",
        f"| 主观题 | {subj_awarded:g} / {subj_max:g} |",
        "",
        f"- 知识类错误：{len(knowledge_errors)} 题" + (f"（{'、'.join(knowledge_errors)}）" if knowledge_errors else ""),
        f"- 过程/语法错误：{len(procedure_errors)} 题" + (f"（{'、'.join(procedure_errors)}）" if procedure_errors else ""),
        f"- 表达/笔误：{len(other_errors)} 题" + (f"（{'、'.join(other_errors)}）" if other_errors else ""),
        "",
        "## 逐题",
        "",
    ]

    for item in result.get("items", []):
        q = questions.get(item.get("qid"), {})
        qid = item.get("qid")
        awarded = float(item.get("awarded", 0))
        max_score = float(item.get("max_score", 0))
        mark = "✓" if awarded >= max_score - 1e-9 else ("△" if awarded > 0 else "✗")
        lines.append(f"### {qid} {TYPE_LABELS.get(q.get('type'), q.get('type', ''))}（{awarded:g}/{max_score:g}）{mark}")
        lines.append("")
        kps = item.get("kp_ids") or q.get("kp_ids") or []
        lines.append("- 考点：" + "、".join(f"{kp} {kp_titles.get(kp, '')}".strip() for kp in kps))
        answer_obj = answer_objs.get(qid) or {}
        attachment_paths = [
            att.get("path") for att in (answer_obj.get("attachments") or [])
            if isinstance(att, dict) and att.get("path")
        ]
        if attachment_paths:
            lines.append("- 你的答案：见作答图片 " + "、".join(attachment_paths))
            if item.get("transcript"):
                lines.append(f"- 识别结果：{item['transcript']}")
        else:
            lines.append(f"- 你的答案：{display_answer(q.get('type'), answer_obj.get('response'))}")
        if q.get("type") in OBJECTIVE:
            ref = q.get("answer")
            if isinstance(ref, list):
                ref = "、".join(str(v) for v in ref)
            lines.append(f"- 参考答案：{display_answer(q.get('type'), ref)}")
        if item.get("executed") is False:
            lines.append("- 执行验证：未通过（SQL 未能成功执行）")
        if item.get("rubric"):
            lines.append("- 评分要点：")
            for point in item["rubric"]:
                icon = "x" if point.get("hit") else " "
                evidence = point.get("evidence") or ""
                lines.append(f"  - [{icon}] {point.get('point')}（{point.get('weight')} 分）"
                             + (f" — {evidence}" if evidence else ""))
        if awarded < max_score - 1e-9:
            if item.get("diagnosis"):
                lines.append(f"- 错在哪里：{item['diagnosis']}")
            if item.get("fix"):
                lines.append(f"- 怎么改：{item['fix']}")
            if item.get("feedback") and not item.get("diagnosis") and not item.get("fix"):
                lines.append(f"- 反馈：{item['feedback']}")
        elif item.get("feedback"):
            lines.append(f"- 反馈：{item['feedback']}")
        slides = item.get("review_slides") or q.get("source_slides") or []
        if slides:
            lines.append(f"- 回看：PPT 第 {'、'.join(str(s) for s in slides)} 页")
        lines.append("")

    lines += ["## 掌握度变化", "", "| KP | 知识点 | 掌握度 | 下次复习 |", "| --- | --- | --- | --- |"]
    for kp in knowledge.get("knowledge_points", []):
        ks = state["knowledge"].get(kp["id"], {})
        mastery = ks.get("mastery", "—")
        due = ks.get("next_due", "—")
        lines.append(f"| {kp['id']} | {kp.get('title', '')} | {mastery} | {due} |")

    weak = [
        (kp["id"], kp.get("title", ""), state["knowledge"].get(kp["id"], {}).get("mastery", 2))
        for kp in knowledge.get("knowledge_points", [])
        if state["knowledge"].get(kp["id"], {}).get("mastery", 2) <= 1
    ]
    lines += ["", "## 下一步", ""]
    if weak:
        for i, (kp_id, title, mastery) in enumerate(sorted(weak, key=lambda x: x[2]), start=1):
            lines.append(f"{i}. 优先重看 {kp_id} {title}（mastery={mastery}）")
        next_index = len(weak) + 1
        lines.append(f"{next_index}. 用本卷错题对应的 PPT 页码做一次针对性回看，再安排 5 题小测。")
    else:
        lines.append("1. 本轮没有掌握度 ≤ 1 的知识点。")
        lines.append("2. 按 next_due 正常复习即可；本轮没有错题需要重做。")
    lines.append("")
    return "\n".join(lines)


def build_wrongbook(rows: list[dict], knowledge: dict) -> str:
    kp_titles = {kp["id"]: kp["title"] for kp in knowledge.get("knowledge_points", [])}
    wrong = [r for r in rows if float(r.get("awarded", 0)) < float(r.get("max_score", 0)) - 1e-9]
    by_kp: dict[str, list[dict]] = defaultdict(list)
    for row in wrong:
        for kp in row.get("kp_ids") or ["unassigned"]:
            by_kp[kp].append(row)

    lines = ["# 错题本", "", f"> 由 attempts/*.jsonl 重建，共 {len(wrong)} 条", ""]
    for kp in sorted(by_kp):
        items = sorted(by_kp[kp], key=lambda r: (r.get("date", ""), r.get("qid", "")), reverse=True)
        lines.append(f"## {kp} {kp_titles.get(kp, '')}".rstrip())
        lines.append("")
        for row in items:
            lines.append(
                f"### {row.get('date', '')} {row.get('quiz_id', '')} "
                f"{row.get('qid', '')}（{row.get('awarded')}/{row.get('max_score')}）"
            )
            lines.append("")
            lines.append(f"- 题目：{row.get('stem', '')}")
            if row.get("attachments"):
                lines.append("- 你的答案：见作答图片 " + "、".join(row["attachments"]))
                if row.get("transcript"):
                    lines.append(f"- 识别结果：{row['transcript']}")
            else:
                lines.append(f"- 你的答案：{display_response(row.get('response'))}")
            if row.get("diagnosis"):
                lines.append(f"- 错在哪里：{row['diagnosis']}")
            if row.get("fix"):
                lines.append(f"- 怎么改：{row['fix']}")
            if row.get("feedback") and not row.get("diagnosis") and not row.get("fix"):
                lines.append(f"- 问题：{row['feedback']}")
            slides = row.get("review_slides") or []
            if slides:
                lines.append(f"- 回看：PPT 第 {'、'.join(str(s) for s in slides)} 页")
            lines.append(f"- 错因：{row.get('error_type', 'none')}")
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="应用批改结果并生成报告")
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--quiz", type=Path, required=True)
    parser.add_argument("--knowledge", type=Path, required=True)
    parser.add_argument("--submission", type=Path)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--session", type=Path, required=True, help="sessions/<quiz_id> 目录")
    parser.add_argument("--course-id", default="default")
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--reset", action="store_true", help="从 knowledge 重建状态（用于重新批改）")
    args = parser.parse_args()

    result = load_json(args.result)
    quiz = load_json(args.quiz)
    knowledge = load_json(args.knowledge)
    submission = load_json(args.submission) if args.submission else None
    today = date.fromisoformat(args.today)

    if args.reset or not args.state.exists():
        state = init_state(knowledge, args.course_id)
    else:
        state = load_json(args.state)
    for kp in knowledge.get("knowledge_points", []):
        state["knowledge"].setdefault(kp["id"], kp_default(kp.get("title", "")))

    notes = apply_result(state, result, quiz, today)

    lines = attempt_lines(result, quiz, submission, today)
    rewrite_attempts(args.session, result["quiz_id"], lines)

    write_json_atomic(args.state, state)

    report = build_report(result, quiz, submission, knowledge, state)
    (args.session / "report.md").write_text(report, encoding="utf-8")

    wrongbook = build_wrongbook(all_attempts(args.session), knowledge)
    (args.session.parent.parent / "wrongbook.md").write_text(wrongbook, encoding="utf-8")

    for note in notes:
        print(note)
    print(f"[ok] 状态: {args.state}")
    print(f"[ok] 报告: {args.session / 'report.md'}")
    print(f"[ok] 错题本: {args.session.parent.parent / 'wrongbook.md'}")
    print(f"[ok] 得分: {result['score']['awarded']} / {result['score']['max']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
