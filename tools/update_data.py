#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_data.py —— 「把官方职位表拖进来就能更新数据」的交互式引导脚本
================================================================================
由 更新数据.bat 调用（把 .xlsx/.xls 文件拖到 .bat 上即可），也可以在命令行直接运行：

    python tools/update_data.py "2026江苏省考职位表.xlsx"
    python tools/update_data.py 省考职位表.xlsx 国考职位表.xlsx

它会依次完成：
    1. 检查/安装依赖（pandas、openpyxl）
    2. 询问考试类型、年度、官方公告页网址（回车即用默认值，年度留空=自动识别）
    3. 调用 scraper.py 解析清洗，生成 data.json
    4. 调用 build_standalone.py 把新数据同步进 index.html（双击即用）
"""

from __future__ import annotations

import importlib
import os
import re
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def guess_defaults(files: list) -> tuple:
    """
    根据文件名猜测默认值，减少手输：
      · 考试类型：文件名含"国考/中央/国家公务员" -> 国考，否则 江苏省考
      · 年度：文件名里的 20xx
    """
    joined = " ".join(os.path.basename(f) for f in files)
    exam = "国考" if re.search(r"国考|中央|国家公务员|国家机关", joined) else "江苏省考"
    m = re.search(r"(20\d{2})", joined)
    return exam, (m.group(1) if m else "")


def init_console() -> None:
    """避免 Windows GBK 控制台因中文报 UnicodeEncodeError"""
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (getattr(stream, "encoding", "") or "").lower()
            if enc in ("", "ascii", "ansi_x3.4-1968", "us-ascii"):
                stream.reconfigure(encoding="utf-8", errors="replace")
            else:
                stream.reconfigure(errors="replace")
        except Exception:
            pass


def clean_answer(s: str) -> str:
    """
    清洗用户输入：去掉首尾空白以及 BOM / 零宽字符。
    某些终端或管道会把 UTF-8 BOM(\ufeff) 带进 stdin，若不处理会被当成有效输入，
    导致"考试类型"变成一串不可见字符（真实踩过的坑）。
    """
    return s.strip().strip("\ufeff\u200b\u200e\u200f\ufffd").strip()


def ask(prompt: str, default: str = "") -> str:
    """带默认值的交互输入（读不到输入时直接返回默认值，便于自动化测试）"""
    tip = "%s（回车=%s）: " % (prompt, default) if default else "%s（可留空）: " % prompt
    try:
        val = clean_answer(input(tip))
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return val or default


def ensure_dependencies() -> bool:
    """确保 pandas / openpyxl 可用（缺失时自动 pip 安装）"""
    missing = []
    for mod, pkg in (("pandas", "pandas"), ("openpyxl", "openpyxl")):
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return True

    print("\n检测到缺少依赖：%s，正在自动安装（需要联网，约 1-3 分钟）……" % "、".join(missing))
    req = os.path.join(BASE_DIR, "requirements.txt")
    cmd = [sys.executable, "-m", "pip", "install", "-q"]
    cmd += ["-r", req] if os.path.exists(req) else missing
    try:
        rc = subprocess.run(cmd, cwd=BASE_DIR).returncode
    except Exception as exc:
        print("[错误] 自动安装失败：%s" % exc)
        return False
    if rc != 0:
        print("[错误] 依赖安装失败（退出码 %s），请手动执行：pip install -r requirements.txt" % rc)
        return False

    importlib.invalidate_caches()
    for mod in ("pandas", "openpyxl"):
        try:
            importlib.import_module(mod)
        except ImportError:
            print("[错误] 仍无法导入 %s，请手动安装后重试。" % mod)
            return False
    print("依赖安装完成。\n")
    return True


def run_step(title: str, args: list) -> int:
    print("\n" + "-" * 64)
    print(title)
    print("-" * 64)
    return subprocess.run([sys.executable] + args, cwd=BASE_DIR).returncode


def main() -> int:
    init_console()
    print("=" * 64)
    print("公考职位查询工具 —— 用官方职位表更新数据")
    print("=" * 64)

    files = [f for f in sys.argv[1:] if f.strip()]
    if not files:
        print("用法：把从官网下载的职位表 Excel 文件拖到「更新数据.bat」上；")
        print("      或在命令行执行： python tools/update_data.py 职位表.xlsx")
        try:
            input("\n按回车键退出…")
        except (EOFError, KeyboardInterrupt):
            pass
        return 1

    # 校验文件
    ok_files, bad_files = [], []
    for f in files:
        path = f if os.path.isabs(f) else os.path.join(os.getcwd(), f)
        path = os.path.normpath(path)
        (ok_files if os.path.exists(path) else bad_files).append(path)
    if bad_files:
        print("\n[错误] 以下文件不存在：")
        for b in bad_files:
            print("   " + b)
    if not ok_files:
        try:
            input("\n按回车键退出…")
        except (EOFError, KeyboardInterrupt):
            pass
        return 1

    print("\n待解析文件（%d 个）：" % len(ok_files))
    for f in ok_files:
        print("   " + f)

    if not ensure_dependencies():
        try:
            input("\n按回车键退出…")
        except (EOFError, KeyboardInterrupt):
            pass
        return 1

    print("\n请填写来源信息（直接回车即使用默认值）：")
    exam_default, year_default = guess_defaults(ok_files)
    exam = ask("考试类型（可填 国考 / 江苏省考）", exam_default)
    # 防御：考试类型应当是中文名称，否则退回默认值（避免把不可见字符写进 data.json）
    if not re.search(r"[\u4e00-\u9fff]", exam):
        print("  [提示] 考试类型“%s”看起来不是有效名称，已改用默认值：%s" % (exam, exam_default))
        exam = exam_default
    year = ask("年度（留空=自动识别）", year_default)
    if year and not re.fullmatch(r"20\d{2}", year):
        print("  [提示] 年度“%s”格式不正确（应为 4 位年份），已改为自动识别。" % year)
        year = ""
    src = ask("官方公告页网址", "")

    args = ["scraper.py", "--local"] + ok_files + ["--exam-type", exam]
    if year:
        args += ["--year", year]
    if src:
        args += ["--source-url", src]

    if run_step("第 1 步 / 2：解析并清洗职位表，生成 data.json", args) != 0:
        print("\n[失败] 解析未成功，请查看上面的错误提示。")
        print("       常见原因：该文件不是职位表 / 表头缺少「职位名称、招录机关、专业」等列。")
        try:
            input("\n按回车键退出…")
        except (EOFError, KeyboardInterrupt):
            pass
        return 1

    if run_step("第 2 步 / 2：同步进 index.html（保证双击打开也能看到新数据）",
                ["tools/build_standalone.py"]) != 0:
        print("\n[提示] data.json 已更新，但同步进 index.html 失败，可手动执行："
              "python tools/build_standalone.py")

    print("\n" + "=" * 64)
    print("完成！data.json 与 index.html 均已更新。")
    print("  查看方式：双击 index.html，或双击 启动.bat")
    print("=" * 64)
    try:
        input("\n按回车键退出…")
    except (EOFError, KeyboardInterrupt):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
