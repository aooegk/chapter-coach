#!/usr/bin/env python3
"""把 quiz.json 与提交配置注入单文件试卷模板。

用法:
    python build_exam.py quiz.json --template ../assets/exam-template.html \
        --config config.json --out .ppt-tutor/sessions/<quiz_id>/exam.html

模板中两个占位块会被整体替换:
    <script type="application/json" id="quiz-data">...</script>
    <script type="application/json" id="submit-config">...</script>

注入时把 < > & 转成 \\uXXXX，避免 </script> 或 HTML 片段截断脚本块。
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import re
import sys
from pathlib import Path

QUIZ_BLOCK = "quiz-data"
CFG_BLOCK = "submit-config"


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
    replaced, count = pattern.subn(
        lambda m: m.group(1) + payload + m.group(3), document
    )
    if count != 1:
        raise SystemExit(f"[error] 找不到或找到多个占位块: {elem_id}")
    return replaced


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise SystemExit(f"[error] 文件不存在: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[error] JSON 解析失败: {path}: {exc}")


def strip_answers(quiz: dict) -> dict:
    """考试模式下从试卷中移除所有答案与评分信息。"""
    cleaned = copy.deepcopy(quiz)
    for item in cleaned.get("questions", []):
        for key in ("answer", "accepted_answers", "rubric", "explanation"):
            item.pop(key, None)
        ctx = item.get("sql_context")
        if isinstance(ctx, dict):
            ctx.pop("expected_rows", None)
    return cleaned


def inject_mathjax(document: str) -> str:
    """把 MathJax TeX→SVG 内联进 HTML，保证离线且按完整 LaTeX 规则渲染。"""
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


def main() -> int:
    parser = argparse.ArgumentParser(description="构建单文件试卷 HTML")
    parser.add_argument("quiz", type=Path, help="quiz.json")
    parser.add_argument("--template", type=Path, required=True, help="exam-template.html")
    parser.add_argument("--out", type=Path, required=True, help="输出 exam.html")
    parser.add_argument("--config", type=Path, help="提交配置 JSON（可选）")
    parser.add_argument("--title", help="试卷标题，默认取 quiz.title 或 quiz_id")
    parser.add_argument("--mode", choices=["practice", "exam"], help="覆盖 quiz.mode")
    parser.add_argument("--channel", choices=["post", "download"], help="提交通道")
    parser.add_argument("--endpoint", help="localhost 接收器地址，如 http://127.0.0.1:8765/submit")
    parser.add_argument("--token", help="接收器一次性 token")
    parser.add_argument("--filename", help="提交文件名，默认 quiz-<quiz_id>.json")
    parser.add_argument("--duration-min", type=int, help="限时（分钟）")
    parser.add_argument(
        "--include-answers",
        choices=["auto", "never", "always"],
        default="auto",
        help="是否把答案与 rubric 注入 HTML。auto: practice 注入，exam 剥离",
    )
    args = parser.parse_args()

    quiz = load_json(args.quiz)
    if not isinstance(quiz, dict):
        raise SystemExit("[error] quiz.json 顶层必须是对象")
    quiz_id = quiz.get("quiz_id")
    if not quiz_id:
        raise SystemExit("[error] quiz.json 缺少 quiz_id")

    if args.mode:
        quiz["mode"] = args.mode
    quiz.setdefault("mode", "practice")

    include_answers = (
        args.include_answers == "always"
        or (args.include_answers == "auto" and quiz.get("mode") == "practice")
    )
    embedded_quiz = quiz if include_answers else strip_answers(quiz)

    cfg: dict = {}
    if args.config:
        cfg.update(load_json(args.config))
    if args.channel:
        cfg["channel"] = args.channel
    if args.endpoint:
        cfg["endpoint"] = args.endpoint
    if args.token:
        cfg["token"] = args.token
    cfg.setdefault("channel", "download")
    cfg.setdefault("filename", f"quiz-{quiz_id}.json")
    if args.filename:
        cfg["filename"] = args.filename
    if args.duration_min:
        quiz.setdefault("config", {})["duration_min"] = args.duration_min
    if cfg["channel"] == "post" and not cfg.get("endpoint"):
        raise SystemExit("[error] channel=post 时必须提供 --endpoint")

    title = args.title or quiz.get("title") or quiz_id
    template = args.template.read_text(encoding="utf-8")
    if "__TITLE__" not in template:
        print("[warn] 模板中未找到 __TITLE__ 占位符", file=sys.stderr)

    document = template.replace("__TITLE__", html.escape(str(title)))
    document = replace_block(document, QUIZ_BLOCK, embed_json(embedded_quiz))
    document = replace_block(document, CFG_BLOCK, embed_json(cfg))
    document = inject_mathjax(document)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(document, encoding="utf-8")
    print(f"[ok] 已生成 {args.out}")
    print(f"[ok] 提交通道: {cfg['channel']}  文件名: {cfg['filename']}")
    print(f"[ok] 答案注入: {'是' if include_answers else '否'}（mode={quiz.get('mode')}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
