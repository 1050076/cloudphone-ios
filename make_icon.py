# 生成 iOS AppIcon 图标：深色渐变背景 + 云+手机图形
from PIL import Image, ImageDraw
import math, os

SIZE = 1024

def rounded_rect_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m

# 背景深蓝渐变
img = Image.new("RGBA", (SIZE, SIZE))
top = (28, 34, 70)
bottom = (10, 14, 40)
px = img.load()
for y in range(SIZE):
    t = y / (SIZE - 1)
    r = int(top[0] + (bottom[0] - top[0]) * t)
    g = int(top[1] + (bottom[1] - top[1]) * t)
    b = int(top[2] + (bottom[2] - top[2]) * t)
    for x in range(SIZE):
        px[x, y] = (r, g, b, 255)

d = ImageDraw.Draw(img)

# 手机机身（圆角矩形），居中
pw, ph = 400, 700
cx, cy = SIZE // 2, SIZE // 2
px0, py0 = cx - pw // 2, cy - ph // 2
px1, py1 = cx + pw // 2, cy + ph // 2
d.rounded_rectangle([px0, py0, px1, py1], radius=70, fill=(255, 255, 255, 235))

# 屏幕区域（蓝色调）
d.rounded_rectangle([px0 + 26, py0 + 60, px1 - 26, py1 - 60], radius=40, fill=(70, 110, 230, 255))

# 听筒
d.rounded_rectangle([cx - 50, py0 + 24, cx + 50, py0 + 40], radius=8, fill=(150, 155, 170, 255))
# Home 指示条
d.rounded_rectangle([cx - 60, py1 - 40, cx + 60, py1 - 28], radius=6, fill=(150, 155, 170, 255))

# 云朵在屏幕里（三圆+矩形近似）
def cloud(draw, ox, oy, s, color):
    # s = 缩放系数（相对 100 基准）
    draw.ellipse([ox - 55 * s, oy - 10 * s, ox + 5 * s, oy + 45 * s], fill=color)
    draw.ellipse([ox - 25 * s, oy - 35 * s, ox + 35 * s, oy + 20 * s], fill=color)
    draw.ellipse([ox + 5 * s, oy - 5 * s, ox + 60 * s, oy + 45 * s], fill=color)
    draw.rectangle([ox - 55 * s, oy + 15 * s, ox + 60 * s, oy + 45 * s], fill=color)

cloud(d, cx, cy - 40, 1.3, (255, 255, 255, 255))
# 屏幕上的信号波纹点
for i, r in enumerate((60, 100)):
    d.arc([cx - r, cy + 60 - r // 2, cx + r, cy + 60 + r // 2], start=20, end=160, fill=(255, 255, 255, 200 - i * 60), width=10)

# iOS 会自己裁圆角，但备一个圆角版本好看（AppIcon 用方图即可，这里输出方形）
out_dir = r"E:\Android\app\cloudphone-ios\Assets.xcassets/AppIcon.appiconset"
os.makedirs(out_dir, exist_ok=True)
img.resize((1024, 1024)).save(os.path.join(out_dir, "icon-1024.png"))
img.convert("RGB").resize((512, 512)).save(os.path.join(out_dir, "icon-512.png"))
print("saved", os.listdir(out_dir))
