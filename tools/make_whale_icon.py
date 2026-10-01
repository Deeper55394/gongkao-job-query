# -*- coding: utf-8 -*-
"""生成"蓝色大肥鱼"（DeepSeek 蓝鲸）图标。用捆绑 Python（含 Pillow）运行。

来源：官方 app 图标 https://fe-static.deepseek.com/chat/icon-180.png （180x180 RGBA）
用法：<bundled python> tools/make_whale_icon.py

⚠ 踩过的坑（务必保留这个实现）：
  用 Pillow 的 `img.save("x.ico", format="ICO", sizes=[...])` 生成出来的 ico，
  **所有帧都是 PNG 压缩格式**。而 Windows 只承认 256×256 那一帧用 PNG，
  16/24/32/48 等小尺寸帧必须是 **BMP(DIB)**，否则资源管理器渲染不出小图标、
  桌面直接显示空白（表现为"换了图标但没变化"）。
  所以这里手工写 ICO：小尺寸写 32 位 BMP，仅 256 写 PNG。
"""
import io
import os
import struct
import sys

from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "tools", "whale-source.png")
OUTS = [os.path.join(HERE, "whale.ico"), os.path.join(HERE, "icon.ico")]
SIZES = [16, 24, 32, 48, 64, 128, 256]


def build_square(im: Image.Image, margin_ratio: float = 0.08) -> Image.Image:
    """裁掉四周空白并居中放到正方形白底画布上"""
    im = im.convert("RGBA")
    rgb = im.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if not (r > 244 and g > 244 and b > 244):
                minx = min(minx, x)
                miny = min(miny, y)
                maxx = max(maxx, x)
                maxy = max(maxy, y)
    cropped = im.crop((minx, miny, maxx + 1, maxy + 1)) if maxx >= 0 else im
    side = max(cropped.size)
    pad = int(side * margin_ratio)
    canvas_side = side + pad * 2
    canvas = Image.new("RGBA", (canvas_side, canvas_side), (255, 255, 255, 255))
    canvas.paste(cropped, ((canvas_side - cropped.width) // 2,
                           (canvas_side - cropped.height) // 2), cropped)
    print("  裁剪后 %s → 画布 %s" % (cropped.size, canvas.size))
    return canvas


def frame_bytes(img: Image.Image, size: int) -> bytes:
    """把某一尺寸渲染成 ICO 里的图像数据：256→PNG，其余→32 位 BMP(DIB)"""
    im = img.resize((size, size), Image.LANCZOS).convert("RGBA")
    if size >= 256:
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()

    px = im.load()
    # XOR 位图：自下而上、BGRA
    xor = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            r, g, b, a = px[x, y]
            xor += bytes((b, g, r, a))
    # AND 掩码：每行按 4 字节对齐；透明度由 alpha 负责，这里全 0
    row_bytes = ((size + 31) // 32) * 4
    and_mask = bytes(row_bytes * size)
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                         len(xor) + len(and_mask), 0, 0, 0, 0)
    return header + bytes(xor) + and_mask


def write_ico(img: Image.Image, path: str) -> None:
    frames = [(s, frame_bytes(img, s)) for s in SIZES]
    offset = 6 + 16 * len(frames)
    entries, blobs = [], []
    for size, data in frames:
        dim = 0 if size >= 256 else size
        entries.append(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset))
        blobs.append(data)
        offset += len(data)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<HHH", 0, 1, len(frames)))
        for e in entries:
            fh.write(e)
        for b in blobs:
            fh.write(b)


def main() -> int:
    if not os.path.exists(SRC):
        print("[错误] 找不到素材：%s" % SRC)
        return 1
    src = Image.open(SRC)
    print("素材：%s %s" % (os.path.basename(SRC), src.size))
    canvas = build_square(src)
    for out in OUTS:
        write_ico(canvas, out)
        print("已生成：%s (%d 字节)" % (out, os.path.getsize(out)))
    # 自检：确认小尺寸帧是 BMP、256 帧是 PNG
    data = open(OUTS[0], "rb").read()
    _, _, n = struct.unpack("<HHH", data[:6])
    kinds = []
    for i in range(n):
        off = 6 + i * 16
        w, h, _, _, _, _, size, img_off = struct.unpack("<BBBBHHII", data[off:off + 16])
        w = w or 256
        is_png = data[img_off:img_off + 8] == b"\x89PNG\r\n\x1a\n"
        kinds.append("%dx%d:%s" % (w, w, "PNG" if is_png else "BMP"))
    print("帧格式：" + "  ".join(kinds))
    bad = [k for k in kinds if k.endswith(":PNG") and not k.startswith("256")]
    if bad:
        print("[警告] 仍有小尺寸 PNG 帧（Windows 可能不显示）：%s" % bad)
        return 2
    print("[OK] 小尺寸全部为 BMP，Windows 可正常显示")
    return 0


if __name__ == "__main__":
    sys.exit(main())
