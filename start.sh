#!/usr/bin/env bash
# ============================================================
#  start.sh —— macOS / Linux 一键启动本地服务
#  用法： bash start.sh            （默认 127.0.0.1:8765）
#        bash start.sh --port 9000
#        bash start.sh --lan       （手机同 WiFi 访问）
# ============================================================
set -e
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "[提示] 未检测到 Python，改为直接打开 index.html（离线模式，使用内置数据）。"
  if command -v open >/dev/null 2>&1; then open index.html; else xdg-open index.html 2>/dev/null || true; fi
  exit 0
fi

exec "$PY" tools/serve.py "$@"
