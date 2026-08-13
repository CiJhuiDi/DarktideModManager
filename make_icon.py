# -*- coding: utf-8 -*-
"""生成应用图标 app.ico：深色圆角底 + 绿色电源开关（mod 开关管理语义）"""
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 圆角矩形底（垂直渐变：深蓝黑 -> 近黑）
for y in range(S):
    t = y / S
    r = int(20 + 8 * t)
    g = int(24 + 9 * t)
    b = int(32 + 8 * t)
    d.line([(0, y), (S, y)], fill=(r, g, b, 255))

# 用圆角矩形 mask 裁切底部为圆角
mask = Image.new("L", (S, S), 0)
dm = ImageDraw.Draw(mask)
dm.rounded_rectangle([0, 0, S - 1, S - 1], radius=56, fill=255)
img.putalpha(mask)

# 内圈微光（深青色圆环，增强层次）
d = ImageDraw.Draw(img)
d.ellipse([52, 52, 204, 204], outline=(64, 110, 140, 90), width=3)

# 电源符号：弧线（缺口朝上）+ 中央竖线
GREEN = (62, 207, 142, 255)
d.arc([60, 60, 196, 196], start=130, end=410, fill=GREEN, width=17)
d.rectangle([119.5, 46, 136.5, 112], fill=GREEN)

# 保存多尺寸 ico
img.save(r"D:\DeepseekWorkspace\darktide-mod-manager\app.ico",
         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("app.ico written")
