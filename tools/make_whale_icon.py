# -*- coding: utf-8 -*-
"""生成"蓝色大肥鱼"（DeepSeek 蓝鲸）图标。用捆绑 Python（含 Pillow）运行。

来源：官方 app 图标 https://fe-static.deepseek.com/chat/icon-180.png （180x180 RGBA）
用法：<bundled python> tools/make_whale_icon.py
"""
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "tools", "whale-source.png")
OUT = os.path.join(HERE, "whale.ico")
SIZES = [16, 24, 32, 48, 64, 128, 256]


def main() -> int:
    if not os.path.exists(SRC):
        print("[错误] 找不到素材：%s" % SRC)
        return 1
    im = Image.open(SRC).convert("RGBA")
    print("素材：%s %s" % (os.path.basename(SRC), im.size))

    # 1) 裁掉四周空白（以"非接近白色"为准），让鲸鱼占满图标
    rgb = im.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if not (r > 244 and g > 244 and b > 244):
                if x < minx:
                    minx = x
                if y < miny:
                    miny = y
                if x > maxx:
                    maxx = x
                if y > maxy:
                    maxy = y
    if maxx < 0:
        print("[警告] 素材几乎是纯白，跳过裁剪")
        box = (0, 0, w, h)
    else:
        box = (minx, miny, maxx + 1, maxy + 1)
    cropped = im.crop(box)
    print("裁剪后：%s" % (cropped.size,))

    # 2) 放到正方形画布中央，留 8% 边距（白底，与官方 app 图标观感一致）
    side = max(cropped.size)
    pad = int(side * 0.08)
    canvas_side = side + pad * 2
    canvas = Image.new("RGBA", (canvas_side, canvas_side), (255, 255, 255, 255))
    canvas.paste(cropped, ((canvas_side - cropped.width) // 2,
                           (canvas_side - cropped.height) // 2), cropped)

    # 3) 生成多尺寸 .ico
    frames = [canvas.resize((s, s), Image.LANCZOS) for s in SIZES]
    frames[-1].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    print("已生成：%s (%d 字节，含 %s)" % (OUT, os.path.getsize(OUT), ",".join(str(s) for s in SIZES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
