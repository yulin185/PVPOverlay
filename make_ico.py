import os
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "资源")
src = Image.open(os.path.join(RES, "logo.png")).convert("RGBA")
w, h = src.size
R = 234          # 圆角半径
SS = 4           # 超采样倍数，保证边缘平滑

big = Image.new("L", (w*SS, h*SS), 0)
d = ImageDraw.Draw(big)
d.rounded_rectangle([0, 0, w*SS - 1, h*SS - 1], radius=R*SS, fill=255)
mask = big.resize((w, h), Image.LANCZOS)

out = src.copy()
out.putalpha(mask)
out.save(os.path.join(RES, "logo_t.png"))
print("已生成透明 logo")

# 多尺寸 ico
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
out.save(os.path.join(RES, "logo.ico"), format="ICO", sizes=sizes)
out.resize((256, 256), Image.LANCZOS).save(os.path.join(RES, "logo_256.png"))
print("已生成 ico 和 256 png")

# 检查四角现在是否透明
chk = Image.open(os.path.join(RES, "logo_t.png"))
print("四角 alpha:", [chk.getpixel(p)[3] for p in [(0,0),(w-1,0),(0,h-1),(w-1,h-1)]])
