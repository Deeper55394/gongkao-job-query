#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_standalone.py —— 把 data.json 内嵌进 index.html（生成"双击即用"的离线版）
================================================================================
为什么需要它？
    浏览器在 file:// 协议下禁止 fetch 本地 data.json，导致双击打开时页面读不到数据。
    本脚本把 data.json 的内容写入 index.html 里的
        <script id="embedded-data" type="application/json"> ... </script>
    这样双击 index.html 就能直接看到数据；而一旦有可读取的 data.json
    （本地服务 / GitHub Pages / 手动上传），页面仍然以 data.json 为准。

用法
    python tools/build_standalone.py            # 用 data.json 更新 index.html 的内置数据
    python tools/build_standalone.py --check    # 只检查是否已同步（CI 用，未同步则退出码 1）
    python tools/build_standalone.py --out 单文件版.html   # 另外再输出一个独立副本
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(BASE_DIR, "index.html")
DATA = os.path.join(BASE_DIR, "data.json")

# 匹配 index.html 中承载内置数据的 script 标签
PATTERN = re.compile(
    r'(<script id="embedded-data" type="application/json">)(.*?)(</script>)',
    re.S,
)


def init_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (getattr(stream, "encoding", "") or "").lower()
            if enc in ("", "ascii", "ansi_x3.4-1968", "us-ascii"):
                stream.reconfigure(encoding="utf-8", errors="replace")
            else:
                stream.reconfigure(errors="replace")
        except Exception:
            pass


def compact_json(path: str) -> str:
    """
    读取 data.json 并压缩成一行 JSON（保证体积小、且不会出现 </script> 之类的破坏性字符）。
    为防止内容里出现 '</script>'，把 '<' 转义为 \\u003c（JSON 合法且解析结果完全一致）。
    """
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c")


def main() -> int:
    init_console()
    ap = argparse.ArgumentParser(description="把 data.json 内嵌进 index.html，生成双击即用的离线版")
    ap.add_argument("--check", action="store_true", help="只检查是否已同步，不写文件")
    ap.add_argument("--out", default=None, help="额外输出一份独立的单文件 HTML（可单独发给别人）")
    args = ap.parse_args()

    if not os.path.exists(DATA):
        print("[跳过] 未找到 data.json，index.html 保持原样（页面会提示手动上传数据）。")
        return 0
    if not os.path.exists(INDEX):
        print("[错误] 未找到 index.html")
        return 1

    with open(INDEX, "r", encoding="utf-8") as fh:
        html = fh.read()

    embedded = compact_json(DATA)
    m = PATTERN.search(html)
    if not m:
        print('[错误] index.html 中未找到 <script id="embedded-data" ...> 标记，无法内嵌数据。')
        return 1

    current = m.group(2).strip()
    if args.check:
        if current == embedded:
            print("[通过] index.html 内置数据与 data.json 一致（双击即用的离线版是最新的）。")
            return 0
        print("[未同步] index.html 内置数据与 data.json 不一致，请执行：python tools/build_standalone.py")
        return 1

    if current == embedded:
        print("[无变化] index.html 内置数据已是最新，无需重写。")
    else:
        html = html[:m.start(2)] + embedded + html[m.end(2):]
        with open(INDEX, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(html)
        print("[完成] 已把 data.json 内嵌进 index.html（%d 字节），双击即可离线使用。" % len(embedded))

    # 记录内嵌数据的时间戳，便于页面/人工核对
    try:
        meta = json.loads(embedded.replace("\\u003c", "<")).get("meta", {})
        print("       数据更新时间：%s  记录数：%s" % (meta.get("last_update_text", "未知"), meta.get("record_count", "未知")))
    except Exception:
        pass

    if args.out:
        out_path = args.out if os.path.isabs(args.out) else os.path.join(BASE_DIR, args.out)
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(html)
        print("[完成] 已输出独立单文件：%s" % out_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
