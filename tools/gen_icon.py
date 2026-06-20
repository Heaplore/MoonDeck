"""生成月坞 (MoonDeck) 图标

设计元素：
- 月亮 (半圆弧)
- 三张叠加的卡片
- 蓝紫色渐变背景
"""
from PIL import Image, ImageDraw, ImageFont
import math
import os

def create_icon(size: int) -> Image.Image:
    """生成指定尺寸的图标"""
    # 创建画布
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 缩放因子
    s = size / 256.0
    
    # === 背景：圆形渐变 (深蓝→紫色) ===
    for y in range(size):
        for x in range(size):
            # 计算到中心的距离
            cx, cy = size // 2, size // 2
            dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2) / (size * 0.45)
            if dist < 1.0:
                # 渐变：中心深蓝 → 边缘紫色
                t = dist
                r = int(30 + (100 - 30) * t)
                g = int(50 + (40 - 50) * t)
                b = int(120 + (160 - 120) * t)
                a = int(255 * (1 - dist * 0.3))
                img.putpixel((x, y), (r, g, b, a))
    
    # === 月亮 (金色/白色半圆) ===
    moon_cx = int(size * 0.6)
    moon_cy = int(size * 0.35)
    moon_r = int(size * 0.18)
    
    # 画满月
    moon_color = (255, 223, 100, 240)  # 金色
    draw.ellipse(
        [moon_cx - moon_r, moon_cy - moon_r, moon_cx + moon_r, moon_cy + moon_r],
        fill=moon_color
    )
    
    # 用背景色遮一半，做成月牙
    offset_x = int(moon_r * 0.4)
    offset_y = int(moon_r * 0.2)
    draw.ellipse(
        [moon_cx - moon_r + offset_x, moon_cy - moon_r - offset_y,
         moon_cx + moon_r + offset_x, moon_cy + moon_r - offset_y],
        fill=(30, 50, 120, 200)
    )
    
    # === 三张卡片 (错落叠加) ===
    card_colors = [
        (100, 140, 220, 200),  # 浅蓝
        (130, 100, 200, 200),  # 紫色
        (160, 120, 240, 200),  # 亮紫
    ]
    
    card_positions = [
        (size * 0.18, size * 0.55, size * 0.45, size * 0.75),  # 底层
        (size * 0.28, size * 0.48, size * 0.55, size * 0.68),  # 中层
        (size * 0.38, size * 0.41, size * 0.65, size * 0.61),  # 顶层
    ]
    
    for i, (x1, y1, x2, y2) in enumerate(card_positions):
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        r = int(size * 0.03)  # 圆角
        color = card_colors[i]
        
        # 画圆角矩形
        draw.rounded_rectangle([x1, y1, x2, y2], radius=r, fill=color)
        
        # 卡片上的装饰线 (模拟内容)
        if i == 2:  # 顶层卡片加几条线
            line_y = y1 + int((y2 - y1) * 0.3)
            for j in range(3):
                ly = line_y + j * int(size * 0.05)
                lx1 = x1 + int(size * 0.04)
                lx2 = x2 - int(size * 0.04)
                draw.line([lx1, ly, lx2, ly], fill=(255, 255, 255, 100), width=max(1, int(size * 0.008)))
    
    # === 小星星装饰 ===
    star_positions = [
        (size * 0.15, size * 0.2, 2),
        (size * 0.8, size * 0.15, 1.5),
        (size * 0.25, size * 0.75, 1),
        (size * 0.85, size * 0.7, 1.5),
    ]
    for sx, sy, sr in star_positions:
        sx, sy, sr = int(sx), int(sy), int(sr * s)
        draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(255, 255, 255, 180))
    
    return img


def main():
    output_dir = r"C:\Users\Administrator\.easyclaw\workspace\tools\desktop-canvas\assets"
    os.makedirs(output_dir, exist_ok=True)
    
    # 生成多个尺寸
    sizes = [16, 32, 48, 64, 128, 256]
    images = []
    
    for size in sizes:
        img = create_icon(size)
        images.append(img)
        
        # 保存 PNG
        png_path = os.path.join(output_dir, f"moondeck_{size}.png")
        img.save(png_path)
        print(f"Generated: {png_path} ({size}x{size})")
    
    # 生成 ICO 文件 (Windows 图标)
    ico_path = os.path.join(output_dir, "moondeck.ico")
    # Pillow ICO 保存: 使用 save 的 sizes 参数
    # 先保存最大的作为基础
    images_for_ico = []
    for size in sizes:
        img = create_icon(size)
        images_for_ico.append(img)
    
    # 使用 Pillow ICO 保存方式
    images_for_ico[-1].save(
        ico_path,
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=images_for_ico[:-1]
    )
    print(f"\nGenerated ICO: {ico_path}")
    
    # 生成 256x256 PNG (用于 PyInstaller)
    main_png = os.path.join(output_dir, "moondeck.png")
    images[-1].save(main_png)
    print(f"Generated main PNG: {main_png}")


if __name__ == "__main__":
    main()
