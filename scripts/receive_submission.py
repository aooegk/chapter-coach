#!/usr/bin/env python3
"""一次性 localhost 接收器：提供 exam.html 并接收提交，写 submission.json 后退出。

用法:
    python receive_submission.py --dir .ppt-tutor/sessions/<quiz_id> \
        --port 8765 --token <random> --open --timeout 900

行为:
- GET /            返回目录下的 exam.html
- GET /<file>      只允许读取该目录内的文件
- POST /submit?token=...  写入 submission.json，打印路径，然后关闭服务
- 超时未收到提交则自动关闭并以退出码 2 结束

只用标准库，不依赖第三方包。
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import secrets
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SESSION_DIR: Path
TOKEN: str
MAX_BODY = 50 * 1024 * 1024
MEDIA_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
DONE = threading.Event()


class Handler(BaseHTTPRequestHandler):
    server_version = "PptTutorReceiver/1.0"

    def log_message(self, fmt: str, *args) -> None:  # 安静一点
        print(f"[http] {self.address_string()} {fmt % args}")

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        rel = parsed.path.lstrip("/") or "exam.html"
        target = (SESSION_DIR / rel).resolve()
        try:
            target.relative_to(SESSION_DIR.resolve())
        except ValueError:
            self._json(403, {"ok": False, "error": "forbidden"})
            return
        if not target.is_file():
            self._json(404, {"ok": False, "error": "not found"})
            return
        data = target.read_bytes()
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if mime.startswith("text/") or target.suffix.lower() in {".html", ".json", ".js", ".css", ".md"}:
            mime += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") != "/submit":
            self._json(404, {"ok": False, "error": "unknown endpoint"})
            return
        token = (parse_qs(parsed.query).get("token") or [""])[0]
        if token != TOKEN:
            self._json(403, {"ok": False, "error": "bad token"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._json(400, {"ok": False, "error": "bad content length"})
            return
        raw = self.rfile.read(length)
        try:
            submission = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._json(400, {"ok": False, "error": f"invalid json: {exc}"})
            return
        if not isinstance(submission, dict) or "quiz_id" not in submission or "answers" not in submission:
            self._json(400, {"ok": False, "error": "not a submission object"})
            return
        try:
            media = store_attachments(submission)
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return

        out = SESSION_DIR / "submission.json"
        tmp = SESSION_DIR / ".submission.json.tmp"
        tmp.write_text(json.dumps(submission, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(out)
        print(f"[ok] SUBMISSION_WRITTEN {out}")
        if media:
            print(f"[ok] MEDIA_WRITTEN {len(media)} file(s): {', '.join(media)}")
        self._json(200, {"ok": True, "path": str(out), "media": media})
        DONE.set()


def store_attachments(submission: dict) -> list[str]:
    """把 answers[].attachments[].data_base64 解码到 media/，并替换为 path。"""
    media_dir = SESSION_DIR / "media"
    written = []
    for answer in submission.get("answers", []):
        if not isinstance(answer, dict):
            continue
        qid = str(answer.get("qid") or "q")
        for index, att in enumerate(answer.get("attachments") or []):
            if not isinstance(att, dict):
                raise ValueError("invalid attachment object")
            payload = att.pop("data_base64", None)
            if not payload:
                continue
            media_type = att.get("media_type", "image/jpeg")
            ext = MEDIA_EXT.get(media_type)
            if not ext:
                raise ValueError(f"unsupported media type: {media_type}")
            try:
                data = base64.b64decode(payload, validate=True)
            except Exception as exc:
                raise ValueError(f"invalid base64: {exc}")
            if len(data) > 12 * 1024 * 1024:
                raise ValueError("image too large (max 12MB)")
            media_dir.mkdir(parents=True, exist_ok=True)
            safe_qid = re.sub(r"[^A-Za-z0-9_-]", "", qid) or "q"
            name = f"{safe_qid}-{index + 1}.{ext}"
            (media_dir / name).write_bytes(data)
            att["path"] = f"media/{name}"
            att["size"] = len(data)
            written.append(att["path"])
    return written


def main() -> int:
    global SESSION_DIR, TOKEN, MAX_BODY
    parser = argparse.ArgumentParser(description="一次性提交接收器")
    parser.add_argument("--dir", type=Path, required=True, help="会话目录，含 exam.html")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="0 表示自动分配")
    parser.add_argument("--token", default="", help="缺省自动生成")
    parser.add_argument("--timeout", type=int, default=900, help="秒；0 表示不超时")
    parser.add_argument("--max-body-mb", type=int, default=50, help="提交体上限（MB），含图片")
    parser.add_argument("--open", action="store_true", help="启动后打开浏览器")
    args = parser.parse_args()

    SESSION_DIR = args.dir.resolve()
    MAX_BODY = max(1, args.max_body_mb) * 1024 * 1024
    if not (SESSION_DIR / "exam.html").is_file():
        raise SystemExit(f"[error] 目录中没有 exam.html: {SESSION_DIR}")
    TOKEN = args.token or secrets.token_urlsafe(16)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    port = server.server_address[1]
    url = f"http://{args.host}:{port}/exam.html?token={TOKEN}"
    print(f"[ok] 接收器已启动: {url}")
    print(f"[ok] 提交后写入: {SESSION_DIR / 'submission.json'}")

    if args.timeout > 0:
        def watchdog() -> None:
            finished = DONE.wait(args.timeout)
            if not finished:
                print(f"[warn] {args.timeout}s 内未收到提交，关闭接收器")
            server.shutdown()
        threading.Thread(target=watchdog, daemon=True).start()

    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[warn] 手动中断")
    finally:
        server.server_close()

    return 0 if DONE.is_set() else 2


if __name__ == "__main__":
    raise SystemExit(main())
