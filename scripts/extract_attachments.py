#!/usr/bin/env python3
"""把 submission.json 中的 base64 图片解码到 media/，并把附件改写为相对路径。

用于下载/剪贴板通道：浏览器提交的文件里带 data_base64，Agent 先用本脚本落盘，
再读图批改。localhost 接收器会自动完成同样的处理。

用法:
    python extract_attachments.py --submission sessions/<quiz_id>/submission.json
    python extract_attachments.py --submission ... --out sessions/<quiz_id>
"""

from __future__ import annotations

import argparse
import base64
import json
import re
from pathlib import Path

MEDIA_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def main() -> int:
    parser = argparse.ArgumentParser(description="解码 submission 中的图片附件")
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="输出目录，默认 submission 所在目录")
    args = parser.parse_args()

    try:
        submission = json.loads(args.submission.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise SystemExit(f"[error] 文件不存在: {args.submission}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[error] JSON 解析失败: {args.submission}: {exc}")

    out_dir = args.out or args.submission.parent
    media_dir = out_dir / "media"
    written = []

    for answer in submission.get("answers", []):
        if not isinstance(answer, dict):
            continue
        qid = str(answer.get("qid") or "q")
        for index, att in enumerate(answer.get("attachments") or []):
            if not isinstance(att, dict):
                continue
            payload = att.pop("data_base64", None)
            if not payload:
                continue
            media_type = att.get("media_type", "image/jpeg")
            ext = MEDIA_EXT.get(media_type)
            if not ext:
                print(f"[warn] 跳过不支持的媒体类型: {media_type} ({qid})")
                continue
            try:
                data = base64.b64decode(payload, validate=True)
            except Exception as exc:
                print(f"[warn] base64 解码失败: {qid} #{index + 1}: {exc}")
                continue
            media_dir.mkdir(parents=True, exist_ok=True)
            safe_qid = re.sub(r"[^A-Za-z0-9_-]", "", qid) or "q"
            name = f"{safe_qid}-{index + 1}.{ext}"
            (media_dir / name).write_bytes(data)
            att["path"] = f"media/{name}"
            att["size"] = len(data)
            written.append(att["path"])

    tmp = args.submission.with_suffix(args.submission.suffix + ".tmp")
    tmp.write_text(json.dumps(submission, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(args.submission)

    print(f"[ok] 已解码 {len(written)} 张图片到 {media_dir}")
    for path in written:
        print(f"  - {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
