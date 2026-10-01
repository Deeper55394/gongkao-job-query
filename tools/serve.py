#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
serve.py —— 一键启动本地服务，让页面能自动读取同目录 data.json
================================================================================
为什么需要它？
    直接双击 index.html 时，浏览器会因 file:// 安全策略禁止读取 data.json
    （页面虽有"内置数据"兜底，但不会自动更新）。用本脚本起一个本地静态服务，
    页面就能自动读取 data.json，效果与 GitHub Pages 完全一致。

用法
    python tools/serve.py                  # 默认 127.0.0.1:8765，自动打开浏览器
    python tools/serve.py --port 9000
    python tools/serve.py --lan            # 手机同局域网访问（绑定 0.0.0.0，会打印手机可访问的网址）
    python tools/serve.py --no-browser     # 不自动打开浏览器（服务器/脚本调用）
    python tools/serve.py --verbose        # 打印每条访问日志

停止：按 Ctrl+C
"""

from __future__ import annotations

import argparse
import http.server
import os
import socket
import sys
import threading
import webbrowser

# 项目根目录（index.html / data.json 所在目录）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


class Handler(http.server.SimpleHTTPRequestHandler):
    """只服务本项目目录的静态文件；禁用缓存，保证 data.json 每次都是最新的"""

    verbose = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):     # noqa: A003
        if self.verbose:
            sys.stderr.write("  %s - %s\n" % (self.address_string(), fmt % args))
        else:
            # 静默模式：只提示异常请求，控制台保持干净
            try:
                code = str(args[1])
            except Exception:
                code = ""
            if code and not code.startswith("2") and not code.startswith("3"):
                sys.stderr.write("  [%s] %s\n" % (code, args[0] if args else ""))


def pick_port(host: str, port: int, tries: int = 20) -> int:
    """从 port 开始找一个可用端口"""
    for p in range(port, port + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    raise SystemExit("错误：%d~%d 端口都被占用，请用 --port 指定其他端口。" % (port, port + tries - 1))


def lan_ip() -> str:
    """获取本机在局域网中的 IPv4 地址（用于手机访问）"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("223.5.5.5", 80))       # 不会真的发包，仅用于取本机出口 IP
            return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def main() -> int:
    init_console()
    ap = argparse.ArgumentParser(description="公考职位查询工具 · 本地服务")
    ap.add_argument("--port", type=int, default=8765, help="端口，默认 8765（被占用时自动顺延）")
    ap.add_argument("--lan", action="store_true", help="绑定 0.0.0.0，允许手机等局域网设备访问")
    ap.add_argument("--no-browser", action="store_true", help="不要自动打开浏览器")
    ap.add_argument("--verbose", "-v", action="store_true", help="打印访问日志")
    args = ap.parse_args()

    Handler.verbose = args.verbose
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    port = pick_port("127.0.0.1", args.port)

    has_data = os.path.exists(os.path.join(BASE_DIR, "data.json"))
    url = "http://127.0.0.1:%d/" % port

    print("=" * 68)
    print("公考职位查询工具 · 本地服务已启动")
    print("  项目目录：%s" % BASE_DIR)
    print("  本机访问：%s" % url)
    if args.lan:
        print("  手机访问：http://%s:%d/   （手机需与本机在同一 WiFi）" % (lan_ip(), port))
    print("  data.json：%s" % ("已找到，页面会自动读取最新数据" if has_data else "未找到（页面将使用内置数据）"))
    print("  停止服务：Ctrl + C")
    print("=" * 68)

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    httpd = http.server.ThreadingHTTPServer((host, port), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止本地服务，页面可以继续用（双击打开时使用内置数据）。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
