#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_new_cycle.py —— 新年度职位表"探针"
================================================================================
干什么
    轻量地检查官方渠道**是否已经发布比当前数据更新的年度职位表**，用来：
      · 手动一键确认（双击 检查新职位表.bat）
      · 定时任务里当"哨兵"，一发布就能在日志里看到明确提示
      · 配合 --auto-update，一发现就自动跑完整更新（抓取 → data.json → 内嵌 → 提交）

为什么需要它
    江苏省考职位表放在省人社厅"岗位信息"栏目，栏目 id 每轮会变；
    国考专题页是 JS 动态加载、旧归档页会失效。与其被动等每日任务慢慢摸，
    不如用已知规律直接"点名"检查。

用法
    python tools/probe_new_cycle.py                 # 只检查并报告（发现新年度退出码 5）
    python tools/probe_new_cycle.py --auto-update    # 发现就自动跑更新（含 git 提交推送）
    python tools/probe_new_cycle.py --year 2027      # 指定要检查的年度
    python tools/probe_new_cycle.py --json           # 以 JSON 输出（供程序调用）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scraper  # noqa: E402  复用它的礼貌会话 / 附件判断 / 年份识别

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JSON = os.path.join(BASE_DIR, "data.json")

# 江苏省考"岗位信息"栏目（职位表所在处）+ 专题专栏列表（每轮专题 id 会变，靠它跟到新专题）
JS_ENTRY = "http://jshrss.jiangsu.gov.cn/col/col92919/index.html"
JS_TOPIC_LIST = "http://jshrss.jiangsu.gov.cn/col/col79436/index.html"
JS_TOPIC_2026 = "http://jshrss.jiangsu.gov.cn/col/col92911/index.html"

# 国考：专题首页（年度不同 URL 不同）+ 下载应用页（JS 动态列表，仅作可达性探测）
GK_ENTRY = "http://bm.scs.gov.cn/kl{year}/"
GK_DOWNLOADS = "http://bm.scs.gov.cn/pp/gkweb/core/web/ui/business/download/gkdownloads.html"


def init_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (getattr(stream, "encoding", "") or "").lower()
            if enc in ("", "ascii", "ansi-x3.4-1968", "us-ascii"):
                stream.reconfigure(encoding="utf-8", errors="replace")
            else:
                stream.reconfigure(errors="replace")
        except Exception:
            pass


def current_cycle() -> Dict[str, int]:
    """当前 data.json 里各考试类型的最新年度"""
    cycles: Dict[str, int] = {}
    if not os.path.exists(DATA_JSON):
        return cycles
    try:
        with open(DATA_JSON, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        for job in (payload.get("jobs") if isinstance(payload, dict) else payload) or []:
            et = scraper.clean_text(job.get("考试类型")) or "未知"
            try:
                y = int(scraper.clean_text(job.get("年度")) or 0)
            except ValueError:
                y = 0
            if y > cycles.get(et, 0):
                cycles[et] = y
    except Exception:
        pass
    return cycles


def probe_jiangsu(sess: scraper.PoliteSession, want_year: int) -> List[Tuple[str, str, str]]:
    """
    在江苏人社厅找"年度 >= want_year 的职位表"文章。
    返回 [(文章标题, 文章URL, 命中年度)]
    """
    hits: List[Tuple[str, str, str]] = []
    for entry in (JS_ENTRY, JS_TOPIC_LIST, JS_TOPIC_2026):
        html = sess.get_text(entry)
        if not html:
            continue
        for abs_url, title in scraper.extract_links(html, entry):
            # 江苏的文章锚文本形如"江苏省2026年度考试录用公务员各地职位表2025-10-31"
            if "职位表" not in title:
                continue
            m = re.search(r"(20\d{2})\s*年度", title) or re.search(r"(20\d{2})", title)
            year = int(m.group(1)) if m else 0
            if year >= want_year:
                hits.append((title.strip(), abs_url, str(year)))
    # 去重
    seen, uniq = set(), []
    for t, u, y in hits:
        if u not in seen:
            seen.add(u)
            uniq.append((t, u, y))
    return uniq


def classify_page(sess: scraper.PoliteSession, url: str) -> Tuple[str, str]:
    """
    判断一个页面是"静态可抓"还是"JS 空壳"，返回 (类别, 说明)。

    为什么要这个：国考专题站已改成纯 JS 应用（页面只有 2~4KB、0 个链接），
    静态爬虫拿不到；而往年它是静态页。发布当天只要知道它属于哪类，
    就能立刻决定"零依赖直接抓"还是"必须上浏览器渲染（Playwright）"。
    """
    html = sess.get_text(url)
    if not html:
        return "error", "打不开"
    page_title = scraper.extract_page_title(html)
    links = scraper.extract_links(html, url)
    file_links = []
    for abs_url, title in links:
        if re.search(r"\.(xlsx?|xlsm|zip|pdf|docx?)(\?|$)", abs_url, re.I):
            file_links.append((title, abs_url))
        elif scraper.is_excel_attachment(abs_url, title, page_title):
            file_links.append((title, abs_url))
    if file_links:
        return "static", "静态页，且有 %d 个文件链接（可零依赖直接抓）" % len(file_links)
    if len(links) == 0:
        return "js_shell", "JS 空壳（%d 字节、0 个链接 → 静态爬虫拿不到，需要浏览器渲染）" % len(html)
    return "static_no_file", "静态页（%d 个链接）但暂未发现文件链接" % len(links)


def probe_guokao(sess: scraper.PoliteSession, want_year: int) -> Tuple[List[Tuple[str, str, str]], List[str]]:
    """
    国考：探测 kl{year} 专题页与「相关下载」应用页，并判定它们的可抓性。
    返回 (命中列表, 备注列表)。
    """
    hits: List[Tuple[str, str, str]] = []
    notes: List[str] = []
    url = GK_ENTRY.format(year=want_year)
    kind, why = classify_page(sess, url)
    html = sess.get_text(url) if kind != "error" else None
    title = scraper.extract_page_title(html) if html else ""
    if kind == "error":
        notes.append("国考 kl%d 专题页打不开（很可能还没上线）" % want_year)
    elif str(want_year) in title and "年度" in title:
        hits.append(("国考专题页已上线：" + title, url, str(want_year)))
        if html:
            for abs_url, link_title in scraper.extract_links(html, url):
                if scraper.is_excel_attachment(abs_url, link_title, title):
                    hits.append((link_title or abs_url, abs_url, str(want_year)))
        notes.append("国考 kl%d 专题页：%s" % (want_year, why))
    else:
        notes.append("国考 kl%d 专题页存在但标题是「%s」（尚未换成本年度）；%s"
                     % (want_year, title[:40] or "空", why))

    dk, dw = classify_page(sess, GK_DOWNLOADS)
    notes.append("国考「相关下载」应用页：%s" % dw)
    if dk == "static":
        hits.append(("国考「相关下载」页是静态页，可直接解析", GK_DOWNLOADS, str(want_year)))
    return hits, notes


def main() -> int:
    init_console()
    ap = argparse.ArgumentParser(description="检查官方是否发布了更新年度的职位表")
    ap.add_argument("--year", type=int, default=0, help="要检查的年度（默认=当前数据年度+1）")
    ap.add_argument("--auto-update", action="store_true", help="发现新年度就自动跑完整更新")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--delay", type=float, default=2.0, help="同域名请求间隔秒数")
    args = ap.parse_args()

    cycles = current_cycle()
    want_year = args.year or (max(cycles.values()) + 1 if cycles else datetime.now().year)
    print("当前数据年度：%s" % ("、".join("%s %d" % (k, v) for k, v in cycles.items()) or "（无 data.json）"))
    print("本次检查目标：>= %d 年度\n" % want_year)

    all_hosts = sorted({h for s in scraper.SOURCES for h in s.allowed_hosts} |
                       {"jshrss.jiangsu.gov.cn", "bm.scs.gov.cn", "www.scs.gov.cn"})
    sess = scraper.PoliteSession(delay=args.delay, allowed_hosts=all_hosts)

    result: Dict[str, object] = {"want_year": want_year, "current": cycles, "found": [], "notes": []}
    found: List[Tuple[str, str, str]] = []
    notes: List[str] = []
    try:
        found += probe_jiangsu(sess, want_year)
    except Exception as exc:
        notes.append("江苏省考探测异常：%s" % exc)
    try:
        gk_hits, gk_notes = probe_guokao(sess, want_year)
        found += gk_hits
        notes += gk_notes
    except Exception as exc:
        notes.append("国考探测异常：%s" % exc)

    if found:
        print("🎉 发现新年度相关页面/附件 %d 条：" % len(found))
        for title, url, year in found:
            print("   [%s] %s\n        %s" % (year, title[:70], url))
            result["found"].append({"year": year, "title": title, "url": url})  # type: ignore
    else:
        print("尚未发现 %d 年度的职位表（很可能还没到发布期：国考通常 10 月中下旬、江苏省考通常 10-11 月）。" % want_year)
        print("建议：过几天再跑一次，或直接等每天 10:00 的自动任务。")
    for n in notes:
        print("   · %s" % n)
        result["notes"].append(n)  # type: ignore

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if found and args.auto_update:
        print("\n=== --auto-update：开始跑完整更新 ===")
        code = subprocess.run([sys.executable, os.path.join(BASE_DIR, "scraper.py"),
                               "--time-budget", "900"], cwd=BASE_DIR).returncode
        if code not in (0, 2):
            print("scraper 退出码 %s，停止" % code)
            return code
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "tools", "build_standalone.py")], cwd=BASE_DIR)
        git = "git"
        for cmd in (["add", "-A"], ["commit", "-m", "chore(data): 新年度职位表自动更新"]):
            subprocess.run([git] + cmd, cwd=BASE_DIR)
        subprocess.run([git, "push"], cwd=BASE_DIR)
        print("已更新并推送（若 push 需要登录，请在窗口里完成）")
        return 0

    return 5 if found else 0


if __name__ == "__main__":
    sys.exit(main())
