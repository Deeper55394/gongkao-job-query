#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_package.py —— 打包分发：生成 ZIP 压缩包 + 独立单文件 HTML
================================================================================
用途
    1. 生成 `公考职位查询工具.zip`：解压后双击 `启动.bat` / `index.html` 即可用，
       也可以直接推到 GitHub 仓库启用自动更新；
    2. 生成 `公考职位查询_单文件版.html`：自带数据的一个 HTML，
       发给任何人都能双击打开（适合微信/邮件分享）。

用法
    python tools/make_package.py                    # 输出到项目上级目录
    python tools/make_package.py --out D:\分享
    python tools/make_package.py --no-zip --no-single
"""

from __future__ import annotations

import argparse
import os
import sys
import zipfile
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_standalone  # noqa: E402  复用"内嵌数据"的逻辑

# 打包时排除的目录 / 文件
SKIP_DIRS = {"downloads", "__pycache__", ".git", ".tooling", ".idea", ".vscode", "node_modules"}
SKIP_EXT = {".pyc", ".tmp", ".log"}
ZIP_ROOT = "公考职位查询工具"          # 压缩包内的顶层目录名


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


def ensure_txt_bom() -> None:
    """
    给根目录下的 .txt 补上 UTF-8 BOM。
    Windows 记事本（尤其旧版本）遇到无 BOM 的 UTF-8 中文文本会显示乱码，
    而任何编辑器保存一次都可能把 BOM 丢掉，所以打包前统一兜底。
    """
    for fn in os.listdir(BASE_DIR):
        if not fn.lower().endswith(".txt"):
            continue
        path = os.path.join(BASE_DIR, fn)
        with open(path, "rb") as fh:
            raw = fh.read()
        if raw.startswith(b"\xef\xbb\xbf"):
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        with open(path, "wb") as fh:
            fh.write(b"\xef\xbb\xbf" + text.encode("utf-8"))
        print("[修正] 已为 %s 补上 UTF-8 BOM（Windows 记事本显示中文用）" % fn)


def collect_files(github_mode: bool = False) -> list:
    """
    收集需要打包的文件，返回 [(绝对路径, 包内相对路径)]

    github_mode=True 时额外排除仅供开发预览的图片，让仓库更干净。
    """
    dev_only = {"icon_preview.png", "icon_256.png"}
    items = []
    for dirpath, dirnames, filenames in os.walk(BASE_DIR):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in SKIP_EXT:
                continue
            if fn.startswith("data.json.bak") or fn.endswith(".zip"):
                continue
            if github_mode and fn in dev_only:
                continue
            full = os.path.join(dirpath, fn)
            items.append((full, os.path.relpath(full, BASE_DIR)))
    return sorted(items, key=lambda x: x[1])


def make_single_file(out_path: str) -> bool:
    """用 index.html（已内嵌数据）+ 最新 data.json 生成独立单文件 HTML"""
    if not os.path.exists(os.path.join(BASE_DIR, "data.json")):
        print("[跳过] 未找到 data.json，无法生成单文件版。")
        return False
    rc = None
    # 直接调用 build_standalone 的内部逻辑，避免污染 sys.argv
    try:
        with open(os.path.join(BASE_DIR, "index.html"), "r", encoding="utf-8") as fh:
            html = fh.read()
        embedded = build_standalone.compact_json(os.path.join(BASE_DIR, "data.json"))
        m = build_standalone.PATTERN.search(html)
        if not m:
            print("[错误] index.html 中未找到内嵌数据标记。")
            return False
        html = html[:m.start(2)] + embedded + html[m.end(2):]
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(html)
        print("[完成] 独立单文件版：%s（%.1f KB）"
              % (out_path, os.path.getsize(out_path) / 1024))
        return True
    except Exception as exc:
        print("[错误] 生成单文件版失败：%s" % exc)
        return False


def make_zip(out_path: str, github_mode: bool = False) -> bool:
    """
    github_mode=False：包内带一层「公考职位查询工具」目录，适合解压后使用；
    github_mode=True ：文件全部放在包根目录，适合直接推给 GitHub 仓库
                       （GitHub Pages 要求 index.html 在仓库根目录）。
    """
    items = collect_files(github_mode)
    prefix = "" if github_mode else ZIP_ROOT
    try:
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for full, rel in items:
                arc = os.path.join(prefix, rel).replace("\\", "/") if prefix else rel.replace("\\", "/")
                # 用 UTF-8 文件名（zipfile 会自动设置 UTF-8 标志位，Windows 资源管理器可正确显示中文）
                zf.write(full, arc)
        print("[完成] 压缩包：%s（%d 个文件，%.1f KB）"
              % (out_path, len(items), os.path.getsize(out_path) / 1024))
        return True
    except Exception as exc:
        print("[错误] 打包失败：%s" % exc)
        return False


def verify_zip(path: str, expected_count: int) -> bool:
    """
    打包后自检（输出保持 ASCII 安全，便于在任意终端查看）：
      · 条目数量是否与预期一致
      · 含中文名的条目是否设置了 UTF-8 标志位（否则 Windows 解压会乱码）
      · 是否有意外空文件、CRC 是否全部通过
    """
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            no_flag = [i.filename for i in infos if not i.filename.isascii() and not (i.flag_bits & 0x800)]
            empty = [i.filename for i in infos
                     if i.file_size == 0 and os.path.basename(i.filename) != ".nojekyll"]
            broken = zf.testzip()
        print("[自检] entries=%d (expect %d) | non-ascii-without-utf8-flag=%d | empty=%d | crc=%s"
              % (len(infos), expected_count, len(no_flag), len(empty),
                 "OK" if broken is None else ("BROKEN " + str(broken))))
        return len(infos) == expected_count and not no_flag and not empty and broken is None
    except Exception as exc:
        print("[自检] 压缩包校验失败：%s" % exc)
        return False


def main() -> int:
    init_console()
    ap = argparse.ArgumentParser(description="打包公考职位查询工具（ZIP + 单文件 HTML）")
    ap.add_argument("--out", default=os.path.dirname(BASE_DIR), help="输出目录（默认项目上级目录）")
    ap.add_argument("--no-zip", action="store_true", help="不生成 ZIP")
    ap.add_argument("--no-single", action="store_true", help="不生成单文件 HTML")
    ap.add_argument("--no-github", action="store_true", help="不生成 GitHub 部署包")
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    ensure_txt_bom()

    stamp = datetime.now().strftime("%Y%m%d")
    ok = True
    if not args.no_single:
        single = os.path.join(out_dir, "公考职位查询_单文件版_%s.html" % stamp)
        ok &= make_single_file(single)
    if not args.no_zip:
        zip_path = os.path.join(out_dir, "公考职位查询工具_%s.zip" % stamp)
        ok &= make_zip(zip_path)
        ok &= verify_zip(zip_path, len(collect_files()))
    if not args.no_github:
        gh_path = os.path.join(out_dir, "GitHub部署包_%s.zip" % stamp)
        ok &= make_zip(gh_path, github_mode=True)
        ok &= verify_zip(gh_path, len(collect_files(github_mode=True)))

    print("\n输出目录：%s" % out_dir)
    print("分发方式：ZIP 解压后双击 index.html 或 启动.bat；单文件版 HTML 可直接发给他人。")
    print("GitHub 部署：解压 GitHub部署包_日期.zip，里面的文件要放在仓库**根目录**（index.html 与 data.json 同级）。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
