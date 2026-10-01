#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md2html.py —— 把说明文档（Markdown）转成"双击即可阅读"的单文件 HTML
================================================================================
为什么需要它？
    Windows 默认不会漂亮地显示 .md 文件（记事本只能看到一堆 # 和 |）。
    本脚本把 Markdown 渲染成一个自带样式、带目录、可打印为 PDF 的单文件 HTML。

支持的 Markdown 语法（够本项目文档用，刻意保持简单可靠）
    标题 # ~ ####、段落、**加粗**、`行内代码`、[链接](url)
    无序列表 - / *（支持两级缩进）、有序列表 1. 、列表项续行
    表格 | a | b |、围栏代码 ```lang、引用 >、分隔线 ---

用法
    python tools/md2html.py 使用教程.md                    # 生成 使用教程.html
    python tools/md2html.py 使用教程.md -o 教程.html
    python tools/md2html.py --check 使用教程.md             # 只做结构自检，不写文件
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


# --------------------------------------------------------------------------- #
# 行内元素
# --------------------------------------------------------------------------- #
def inline(text: str) -> str:
    """转义 HTML 后处理行内语法：`code`、**bold**、[text](url)"""
    s = html.escape(text, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    return s


RE_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
RE_UL = re.compile(r"^[-*]\s+(.*)$")
RE_OL = re.compile(r"^\d+[.)]\s+(.*)$")
RE_HR = re.compile(r"^-{3,}$")
RE_TABLE_SEP = re.compile(r"^\|[\s:\-|]+\|$")
RE_CODE_FENCE = re.compile(r"^```")


def is_list_item(s: str) -> bool:
    return bool(RE_UL.match(s) or RE_OL.match(s))


def is_block_start(s: str) -> bool:
    """判断该行是否是一个新块的开始（用于段落收尾）"""
    return bool(RE_HEADING.match(s) or RE_UL.match(s) or RE_OL.match(s)
                or RE_HR.match(s) or s.startswith(">") or s.startswith("|")
                or RE_CODE_FENCE.match(s))


def split_row(s: str) -> list:
    s = s.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


# --------------------------------------------------------------------------- #
# 块级元素
# --------------------------------------------------------------------------- #
def render_list(lines: list, i: int, n: int) -> tuple:
    """渲染列表（支持两级缩进与列表项续行），返回 (html, 新下标)"""
    items = []          # [level, ordered, [文本行...]]
    while i < n:
        raw = lines[i]
        s = raw.strip()
        if not s:
            if i + 1 < n and is_list_item(lines[i + 1].strip()):
                i += 1
                continue
            break
        if is_list_item(s):
            indent = len(raw) - len(raw.lstrip(" "))
            level = 1 if indent >= 2 else 0
            ordered = bool(RE_OL.match(s))
            text = RE_OL.sub(r"\1", RE_UL.sub(r"\1", s))
            if items and items[-1][1] != ordered and level == 0:
                break                      # 有序/无序切换，视为两个列表
            items.append([level, ordered, [text]])
            i += 1
        elif raw.startswith("  ") and items:
            items[-1][2].append(s)          # 续行
            i += 1
        else:
            break

    out, stack = [], []                     # stack: [('ul'|'ol', level)]
    for level, ordered, texts in items:
        tag = "ol" if ordered else "ul"
        body = inline(" ".join(texts))
        if not stack:
            out.append("<%s>" % tag)
            stack.append([tag, level])
            out.append("<li>%s" % body)
        elif level > stack[-1][1]:
            out.append("<%s>" % tag)        # 嵌套
            stack.append([tag, level])
            out.append("<li>%s" % body)
        elif level == stack[-1][1]:
            out.append("</li>\n<li>%s" % body)
        else:
            while len(stack) > 1 and level < stack[-1][1]:
                out.append("</li></%s>" % stack[-1][0])
                stack.pop()
            out.append("</li>\n<li>%s" % body)
    while stack:
        out.append("</li></%s>" % stack[-1][0])
        stack.pop()
    return "\n".join(out), i


def render_table(lines: list, i: int, n: int) -> tuple:
    header = split_row(lines[i])
    i += 2                                   # 跳过分隔行
    rows = []
    while i < n and lines[i].strip().startswith("|"):
        rows.append(split_row(lines[i]))
        i += 1
    out = ['<div class="table-wrap"><table>', "<thead><tr>"]
    out += ["<th>%s</th>" % inline(c) for c in header]
    out.append("</tr></thead><tbody>")
    for r in rows:
        out.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in r) + "</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out), i


def render_quote(lines: list, i: int, n: int) -> tuple:
    buf = []
    while i < n and lines[i].strip().startswith(">"):
        buf.append(lines[i].strip()[1:].strip())
        i += 1
    paras, cur = [], []
    for b in buf:
        if b:
            cur.append(b)
        elif cur:
            paras.append(" ".join(cur))
            cur = []
    if cur:
        paras.append(" ".join(cur))
    body = "".join("<p>%s</p>" % inline(p) for p in paras)
    return '<blockquote>%s</blockquote>' % body, i


def convert(md: str) -> tuple:
    """返回 (正文 HTML, 目录项列表)"""
    lines = md.split("\n")
    n = len(lines)
    out, toc, i = [], [], 0
    sec = 0

    while i < n:
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue

        if RE_CODE_FENCE.match(s):
            lang = s[3:].strip()
            i += 1
            buf = []
            while i < n and not RE_CODE_FENCE.match(lines[i].strip()):
                buf.append(lines[i])
                i += 1
            i += 1
            attr = ' data-lang="%s"' % html.escape(lang) if lang else ""
            out.append('<pre class="code"%s><code>%s</code></pre>' % (attr, html.escape("\n".join(buf))))
            continue

        m = RE_HEADING.match(s)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 1:
                out.append("<h1>%s</h1>" % inline(text))
            else:
                sec += 1
                anchor = "sec-%d" % sec
                out.append('<h%d id="%s">%s</h%d>' % (level, anchor, inline(text), level))
                if level in (2, 3):
                    toc.append((level, text, anchor))
            i += 1
            continue

        if RE_HR.match(s):
            out.append("<hr />")
            i += 1
            continue

        if s.startswith("|") and i + 1 < n and RE_TABLE_SEP.match(lines[i + 1].strip()):
            block, i = render_table(lines, i, n)
            out.append(block)
            continue

        if s.startswith(">"):
            block, i = render_quote(lines, i, n)
            out.append(block)
            continue

        if is_list_item(s):
            block, i = render_list(lines, i, n)
            out.append(block)
            continue

        # 普通段落
        buf = [s]
        i += 1
        while i < n and lines[i].strip() and not is_block_start(lines[i].strip()):
            buf.append(lines[i].strip())
            i += 1
        out.append("<p>%s</p>" % inline(" ".join(buf)))

    return "\n".join(out), toc


TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>__TITLE__</title>
<style>
  :root{--c-main:#1a56db;--c-text:#1f2937;--c-sub:#6b7280;--c-line:#e3e8ef;--c-bg:#f5f7fa;--c-code:#0f172a}
  *{box-sizing:border-box}
  body{margin:0;background:var(--c-bg);color:var(--c-text);
    font:15px/1.85 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
  header.top{background:linear-gradient(135deg,#1a56db,#1e3a8a);color:#fff;padding:20px 18px}
  header.top .t{font-size:20px;font-weight:700}
  header.top .s{font-size:12.5px;opacity:.9;margin-top:4px}
  .wrap{max-width:900px;margin:0 auto;padding:0 14px 60px}
  main{background:#fff;border:1px solid var(--c-line);border-radius:12px;
    box-shadow:0 1px 3px rgba(16,24,40,.06);padding:22px 24px;margin-top:14px}
  nav.toc{background:#fff;border:1px solid var(--c-line);border-radius:12px;padding:14px 18px;margin-top:14px;font-size:14px}
  nav.toc b{display:block;margin-bottom:6px;color:var(--c-main)}
  nav.toc a{color:var(--c-text);text-decoration:none;display:block;padding:2px 0}
  nav.toc a:hover{color:var(--c-main);text-decoration:underline}
  nav.toc a.lv3{padding-left:18px;font-size:13.5px;color:var(--c-sub)}
  h1{font-size:22px;margin:6px 0 16px;padding-bottom:10px;border-bottom:2px solid var(--c-main)}
  h2{font-size:19px;margin:30px 0 10px;padding-left:10px;border-left:4px solid var(--c-main)}
  h3{font-size:16.5px;margin:22px 0 8px;color:#1e3a8a}
  h4{font-size:15px;margin:18px 0 6px}
  p{margin:10px 0}
  a{color:var(--c-main);word-break:break-all}
  ul,ol{margin:10px 0;padding-left:24px}
  li{margin:5px 0}
  li>ul,li>ol{margin:5px 0}
  code{background:#eef2f7;color:#b91c1c;padding:1.5px 5px;border-radius:4px;font-size:13px;
    font-family:Consolas,Monaco,"Courier New",monospace}
  pre.code{background:var(--c-code);color:#e2e8f0;padding:14px 16px;border-radius:10px;overflow:auto;font-size:13px;line-height:1.7}
  pre.code code{background:none;color:inherit;padding:0}
  blockquote{margin:14px 0;padding:12px 16px;background:#fffbeb;border-left:4px solid #fcd34d;border-radius:0 8px 8px 0;color:#7c4a03}
  blockquote p{margin:6px 0}
  hr{border:0;border-top:1px dashed #cbd5e1;margin:26px 0}
  .table-wrap{overflow:auto;margin:14px 0}
  table{border-collapse:collapse;width:100%;font-size:13.5px}
  th,td{border:1px solid var(--c-line);padding:8px 10px;text-align:left;vertical-align:top}
  th{background:#f1f5f9;white-space:nowrap}
  tbody tr:nth-child(even){background:#fafbfc}
  footer{text-align:center;color:var(--c-sub);font-size:12px;margin-top:20px;line-height:1.9}
  .top-link{position:fixed;right:16px;bottom:16px;background:var(--c-main);color:#fff;border-radius:999px;
    padding:8px 14px;font-size:13px;text-decoration:none;box-shadow:0 4px 12px rgba(26,86,219,.35)}
  @media print{
    header.top{background:#1a56db !important;-webkit-print-color-adjust:exact}
    nav.toc,.top-link{display:none}
    main{border:0;box-shadow:none;padding:0;margin:0}
    body{background:#fff}
    h2{page-break-after:avoid}
    table,pre.code,blockquote{page-break-inside:avoid}
  }
  @media (max-width:600px){
    main{padding:16px 14px}
    h1{font-size:19px}h2{font-size:17px}
  }
</style>
</head>
<body>
<header class="top">
  <div class="t">__TITLE__</div>
  <div class="s">本科 · 生物科学（师范） · 江苏 ｜ 国考 + 江苏省考职位筛选工具</div>
</header>
<div class="wrap">
__TOC__
<main>
__BODY__
</main>
<footer>
  公考职位查询工具 · 使用教程 ｜ 数据来自官方公开职位表，报名条件以官方公告与招录单位答复为准<br />
  按 Ctrl + P 可打印或另存为 PDF
</footer>
</div>
<a class="top-link" href="#">↑ 回到顶部</a>
</body>
</html>
"""


def build_toc(toc: list) -> str:
    if not toc:
        return ""
    items = ['<b>目录</b>']
    for level, text, anchor in toc:
        cls = ' class="lv3"' if level == 3 else ""
        items.append('<a href="#%s"%s>%s</a>' % (anchor, cls, html.escape(text, quote=False)))
    return '<nav class="toc">%s</nav>' % "\n".join(items)


def main() -> int:
    init_console()
    ap = argparse.ArgumentParser(description="把 Markdown 文档转成单文件 HTML")
    ap.add_argument("src", help="Markdown 源文件（如 使用教程.md）")
    ap.add_argument("-o", "--out", default=None, help="输出 HTML（默认与源文件同名）")
    ap.add_argument("--title", default=None, help="页面标题（默认取第一个一级标题）")
    ap.add_argument("--check", action="store_true", help="只做结构自检，不写文件")
    args = ap.parse_args()

    src = args.src if os.path.isabs(args.src) else os.path.join(os.getcwd(), args.src)
    if not os.path.exists(src):
        print("[错误] 找不到文件：%s" % src)
        return 1
    with open(src, "r", encoding="utf-8") as fh:
        md = fh.read()

    m = re.search(r"^#\s+(.+)$", md, re.M)
    title = args.title or (m.group(1).strip() if m else os.path.basename(src))
    body, toc = convert(md)
    page = TEMPLATE.replace("__TITLE__", html.escape(title, quote=False)) \
                   .replace("__TOC__", build_toc(toc)) \
                   .replace("__BODY__", body)

    # ---- 结构自检 ----
    problems = []
    if page.count("<h2") != md.count("\n## ") + (1 if md.startswith("## ") else 0):
        problems.append("h2 数量与 Markdown 不一致")
    dangling = [a for _, _, a in toc if ('id="%s"' % a) not in page]
    if dangling:
        problems.append("目录锚点失效：%s" % dangling)
    leftover = [l for l in re.sub(r"<pre class=\"code\".*?</pre>", "", body, flags=re.S).split("\n")
                if re.match(r"^\s*(#{1,4}\s|\|\s*[-:]|\*\*|\d+\.\s)", l)]
    if leftover:
        problems.append("疑似未转换的 Markdown 残留：%s" % leftover[:3])

    print("[自检] 标题 %d 个 · 目录项 %d 个 · 表格 %d 个 · 代码块 %d 个 · 列表 %d 个"
          % (page.count("<h"), len(toc), page.count("<table>"), page.count("<pre class=\"code\""),
             page.count("<ul>") + page.count("<ol>")))
    if problems:
        print("[自检] 发现问题：%s" % "；".join(problems))
    else:
        print("[自检] 结构检查通过")

    if args.check:
        return 1 if problems else 0

    out = args.out or os.path.splitext(src)[0] + ".html"
    if not os.path.isabs(out):
        out = os.path.join(os.getcwd(), out)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(page)
    print("[完成] 已生成 %s（%.1f KB），双击即可阅读" % (out, os.path.getsize(out) / 1024))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
