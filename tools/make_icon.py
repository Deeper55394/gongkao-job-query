#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_icon.py —— 生成工具图标（.ico）与预览图
================================================================================
桌面快捷方式需要一个图标。本脚本用 Pillow 画一个"蓝色渐变圆角方块 + 放大镜 + 对勾"的图标：
    · 放大镜 = 查询/筛选职位
    · 对勾   = 匹配成功
不依赖任何外部素材，随时可重新生成或改配色。

用法
    python tools/make_icon.py                 # 生成 icon.ico + icon_preview.png
    python tools/make_icon.py --color 0f9d58  # 换个主色（十六进制）
"""

from __future__ import annotations

import argparse
import os
import sys

from PIL import Image, ImageDraw

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
SS = 4                      # 超采样倍数（先画大图再缩小，边缘更平滑）


def hex2rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(c1: tuple, c2: tuple, t: float) -> tuple:
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))


def draw_icon(size: int = 256, color: str = "1a56db") -> Image.Image:
    """画一张 size×size 的图标（内部按 SS 倍超采样绘制后缩小）"""
    S = size * SS
    main = hex2rgb(color)
    dark = mix(main, (10, 20, 60), 0.55)          # 渐变的下端更深
    light = mix(main, (255, 255, 255), 0.25)      # 渐变的上端更亮

    # 1) 竖向渐变
    grad = Image.new("RGB", (1, S))
    for y in range(S):
        grad.putpixel((0, y), mix(light, dark, y / max(S - 1, 1)))
    img = grad.resize((S, S), Image.BILINEAR).convert("RGBA")

    # 2) 圆角遮罩
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255)
    img.putalpha(mask)

    d = ImageDraw.Draw(img)
    k = S / 256.0                                  # 以 256 为基准的缩放系数

    def sc(*vals):
        """把 256 基准的逻辑坐标换算成当前画布坐标（线宽不经过这里，单独乘 k）"""
        return [v * k for v in vals]

    # 3) 放大镜镜片（白色圆环）：圆心 (108,104)，半径 62，环粗 14
    d.ellipse(sc(46, 42, 170, 166), outline=(255, 255, 255, 255), width=int(14 * k))
    # 4) 镜片内的对勾（细一些，避免小尺寸糊成一团）
    d.line(sc(72, 104, 94, 126), fill=(255, 255, 255, 255), width=int(12 * k))
    d.line(sc(94, 126, 138, 80), fill=(255, 255, 255, 255), width=int(12 * k))
    for cx, cy in ((72, 104), (94, 126), (138, 80)):       # 圆头线帽（半径用逻辑值，交给 sc 换算）
        r = 6.0
        d.ellipse(sc(cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255))
    # 5) 放大镜手柄：从镜片边缘 45° 方向往外，粗 20
    d.line(sc(152, 148, 196, 192), fill=(255, 255, 255, 255), width=int(20 * k))
    for cx, cy in ((152, 148), (196, 192)):
        r = 10.0
        d.ellipse(sc(cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255))

    return img.resize((size, size), Image.LANCZOS)


def make_preview(ico_path: str, out_path: str) -> None:
    """把 .ico 里各个尺寸按 3 倍放大拼成预览图，便于肉眼检查小尺寸是否清晰"""
    ico = Image.open(ico_path)
    # Pillow 不同版本 sizes() 可能返回 (w,h) 元组或纯数字，这里统一成元组
    raw_sizes = sorted(ico.ico.sizes())
    sizes = [s if isinstance(s, (tuple, list)) else (s, s) for s in raw_sizes]
    zoom = 3
    pad, gap = 14, 18
    cells = []
    for s in sizes:
        ico.size = s
        frame = ico.copy().convert("RGBA").resize((s[0] * zoom, s[1] * zoom), Image.NEAREST)
        cells.append((s, frame))
    w = pad * 2 + sum(f.width for _, f in cells) + gap * (len(cells) - 1)
    h = pad * 2 + max(f.height for _, f in cells) + 18
    canvas = Image.new("RGB", (w, h), (245, 247, 250))
    x = pad
    d = ImageDraw.Draw(canvas)
    for s, f in cells:
        canvas.paste(f, (x, pad), f)
        d.text((x + 2, pad + f.height + 2), "%dx%d" % (s[0], s[1]), fill=(107, 114, 128))
        x += f.width + gap
    canvas.save(out_path)
    print("[完成] 预览图：%s（尺寸：%s）"
          % (out_path, " ".join("%dx%d" % (s[0], s[1]) for s in sizes)))


def main() -> int:
    ap = argparse.ArgumentParser(description="生成工具图标")
    ap.add_argument("--color", default="1a56db", help="主色（十六进制，默认 1a56db 主题蓝）")
    ap.add_argument("--out", default=os.path.join(BASE_DIR, "icon.ico"), help="输出的 .ico 路径")
    ap.add_argument("--preview", default=os.path.join(BASE_DIR, "icon_preview.png"), help="预览图路径")
    args = ap.parse_args()

    base = draw_icon(256, args.color)
    base.save(args.out, format="ICO", sizes=ICO_SIZES)
    print("[完成] 图标：%s（%.1f KB，含 %s）"
          % (args.out, os.path.getsize(args.out) / 1024,
             "/".join("%d" % s[0] for s in ICO_SIZES)))
    base.save(args.preview.replace("_preview", "_256"), format="PNG")
    try:
        make_preview(args.out, args.preview)
    except Exception as exc:
        print("[提示] 预览图生成失败（不影响 ico）：%s" % exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
