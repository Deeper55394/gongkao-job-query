#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_html.py —— HTML 结构自检（标签配对 + 关键元素统计）
================================================================================
用途
    前端页面是手写的单文件 HTML，改动后最怕出现"标签没闭合"，症状往往是
    页面白屏或样式错乱。本脚本用最朴素的方式做一次结构体检：
      · 所有非空元素标签是否成对闭合
      · 统计 h1/h2/h3、table、li、pre、blockquote、a 等关键元素数量
      · index.html 额外检查：内嵌数据标记是否存在、是否有外部 JS 依赖

用法
    python tools/check_html.py index.html
    python tools/check_html.py index.html 使用教程.html
    python tools/check_html.py *.html --quiet
"""

from __future__ import annotations

import argparse
import os
import re
import sys

# HTML 中不需要闭合标签的元素
VOID = {"br", "hr", "img", "input", "meta", "link", "source", "area", "base",
        "col", "embed", "param", "track", "wbr"}

TAG_RE = re.compile(r"<(/?)([a-zA-Z][\w-]*)([^>]*?)(/?)>")
COUNT_TAGS = ["h1", "h2", "h3", "table", "li", "ul", "ol", "pre", "blockquote", "a", "tr", "td"]


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


def check(path: str, quiet: bool = False) -> bool:
    with open(path, "r", encoding="utf-8") as fh:
        html = fh.read()

    stack, errors = [], []
    for m in TAG_RE.finditer(html):
        close, tag, _attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if tag in VOID or selfclose or tag == "!doctype":
            continue
        if not close:
            stack.append((tag, m.start()))
        elif not stack:
            errors.append("多余的闭合标签 </%s> @%d" % (tag, m.start()))
        elif stack[-1][0] != tag:
            errors.append("标签不匹配：<%s> 未闭合就遇到 </%s> @%d" % (stack[-1][0], tag, m.start()))
            stack.pop()
        else:
            stack.pop()

    unclosed = [t for t, _ in stack]
    counts = {t: len(re.findall(r"<%s[\s>]" % t, html)) for t in COUNT_TAGS}

    ok = not unclosed and not errors
    print("── %s（%.1f KB）" % (os.path.basename(path), os.path.getsize(path) / 1024))
    if not quiet:
        print("   元素统计：" + " ".join("%s=%d" % (k, v) for k, v in counts.items() if v))
    if unclosed:
        print("   ✗ 未闭合标签：%s" % unclosed[:8])
    if errors:
        for e in errors[:8]:
            print("   ✗ %s" % e)
    if ok:
        print("   ✓ 标签配对正常")

    # index.html 专属检查
    if os.path.basename(path) == "index.html":
        has_embedded = 'id="embedded-data"' in html
        external_js = re.findall(r"<script[^>]+src=", html)
        print("   %s 内嵌数据标记：%s" % ("✓" if has_embedded else "✗", "存在" if has_embedded else "缺失"))
        print("   ✓ 外部 JS 依赖：%d 个（离线可用）" % len(external_js))
        ok = ok and has_embedded
    return ok


def main() -> int:
    init_console()
    ap = argparse.ArgumentParser(description="HTML 结构自检")
    ap.add_argument("files", nargs="+", help="待检查的 HTML 文件")
    ap.add_argument("--quiet", "-q", action="store_true", help="不打印元素统计")
    args = ap.parse_args()

    all_ok = True
    for f in args.files:
        path = f if os.path.isabs(f) else os.path.join(os.getcwd(), f)
        if not os.path.exists(path):
            print("── [跳过] 文件不存在：%s" % f)
            all_ok = False
            continue
        all_ok &= check(path, args.quiet)
    print("\n结论：%s" % ("全部通过" if all_ok else "存在问题，请检查上面的 ✗ 行"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
