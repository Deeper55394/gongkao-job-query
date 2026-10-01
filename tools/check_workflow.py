#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_workflow.py —— 校验 GitHub Actions 工作流（越早发现语法错误越好）
================================================================================
为什么需要它？
    `.github/workflows/update.yml` 一旦有 YAML 语法错误或引用了不存在的文件，
    GitHub 上只会给一个含糊的失败提示，排查很费时间。本脚本在本地就能查出来。

检查内容
    1. YAML 能否解析；
    2. 触发器（schedule / workflow_dispatch）与 cron 表达式格式；
    3. 每个 job 是否有 runs-on、是否每个 step 都有 name 且 uses/run 二选一；
    4. 有 `git push` 的 job 是否具备 contents: write 权限（否则机器人无法提交）；
    5. 工作流里引用的本地文件是否真的存在（如 scraper.py、tools/build_standalone.py）。

用法
    python tools/check_workflow.py
    python tools/check_workflow.py .github/workflows/update.yml
"""

from __future__ import annotations

import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import yaml
except ImportError:  # pragma: no cover
    print("[错误] 缺少 pyyaml，请执行：pip install -r requirements.txt")
    sys.exit(2)


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


def main() -> int:
    init_console()
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE_DIR, ".github", "workflows", "update.yml")
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    if not os.path.exists(path):
        print("[错误] 找不到工作流文件：%s" % path)
        return 1

    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()

    problems, notes = [], []

    # ---- 1. YAML 解析 ----
    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        print("[错误] YAML 语法错误：%s" % exc)
        return 1
    print("✓ YAML 语法正确：%s" % os.path.relpath(path, BASE_DIR))

    # ---- 2. 触发器 ----
    # 注意：YAML 里 `on:` 会被解析成布尔键 True
    triggers = doc.get(True, doc.get("on"))
    if triggers is None:
        problems.append("缺少 on: 触发器")
    else:
        tnames = list(triggers.keys()) if isinstance(triggers, dict) else [str(triggers)]
        print("  触发器：%s" % ", ".join(str(t) for t in tnames))
        if isinstance(triggers, dict) and "schedule" in triggers:
            for item in triggers["schedule"]:
                cron = str(item.get("cron", "")).strip()
                if len(cron.split()) != 5:
                    problems.append("cron 表达式应为 5 段：%r" % cron)
                else:
                    notes.append("定时任务 cron = %s（UTC，北京时间需 +8 小时）" % cron)
        if isinstance(triggers, dict) and "workflow_dispatch" in triggers:
            inputs = (triggers["workflow_dispatch"] or {}).get("inputs") or {}
            notes.append("手动触发参数：%s" % (", ".join(inputs.keys()) if inputs else "无"))

    # ---- 3. 权限 ----
    perms = doc.get("permissions") or {}
    contents = perms.get("contents") if isinstance(perms, dict) else None
    print("  顶层权限：%s" % perms)

    # ---- 4. 每个 job / step ----
    jobs = doc.get("jobs") or {}
    if not jobs:
        problems.append("没有定义任何 job")
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            problems.append("job %s 结构异常" % job_name)
            continue
        if "runs-on" not in job:
            problems.append("job %s 缺少 runs-on" % job_name)
        steps = job.get("steps") or []
        if not steps:
            problems.append("job %s 没有任何 step" % job_name)
        for idx, st in enumerate(steps, 1):
            if not isinstance(st, dict):
                problems.append("job %s 第 %d 个 step 结构异常" % (job_name, idx))
                continue
            if not st.get("name"):
                problems.append("job %s 第 %d 个 step 缺少 name" % (job_name, idx))
            if not st.get("uses") and not st.get("run"):
                problems.append("job %s 第 %d 个 step 既没有 uses 也没有 run" % (job_name, idx))
        print("  job %-12s step 数：%d" % (job_name, len(steps)))
        # 有 git push 的 job 必须有写权限
        body = yaml.safe_dump(job, allow_unicode=True)
        if "git push" in body and contents != "write" and (job.get("permissions") or {}).get("contents") != "write":
            problems.append("job %s 里有 git push，但没有 contents: write 权限" % job_name)

    # ---- 5. 引用的本地文件是否存在 ----
    referenced = set(re.findall(r"[\w\u4e00-\u9fff./\\-]+\.(?:py|txt|json|html|js|md)", raw))
    missing = []
    for ref in sorted(referenced):
        # 跳过绝对路径（如 /tmp/pages.json）、动作名、以及运行时生成的文件
        if ref.startswith(("/", "~", "$", "C:", "c:")) or ref.startswith("actions/"):
            continue
        if ref in ("data.json", "index.html"):
            continue
        cand = os.path.join(BASE_DIR, ref.replace("\\", "/"))
        if not os.path.exists(cand):
            missing.append(ref)
    if missing:
        notes.append("工作流里提到但仓库中暂不存在的文件（确认是否由流程生成）：%s" % ", ".join(missing))

    for n in notes:
        print("  · %s" % n)
    if problems:
        print("\n发现 %d 个问题：" % len(problems))
        for p in problems:
            print("  ✗ %s" % p)
        return 1
    print("\n结论：工作流检查通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
