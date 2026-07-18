"""
ADPS 双轴矩阵图片水印工具 · v2 (footer 版)
==========================================
在源图底部扩一条 footer 条，把 ADPS logo + "by Jia Huang · 黄佳" 水印
放在 footer 内。不覆盖任何内容格。视觉与 adps-logo.svg 一致。

用法：
    python3 add_watermark.py <input.png> <output.png>

或从其它脚本导入：
    from add_watermark import add_watermark
    add_watermark("in.png", "out.png")
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import sys

# 配色：与 adps-logo.svg 一致
NAVY = (15, 58, 95)          # #0f3a5f
GOLD = (196, 145, 54)        # #c49136
INK_LIGHT = (248, 250, 252)  # #f8fafc
INK_DARK = (15, 23, 42)      # #0f172a
INK_MUTED = (100, 116, 139)  # #64748b

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]
FONT_PATH = next((c for c in FONT_CANDIDATES if Path(c).exists()), None)
if FONT_PATH is None:
    raise SystemExit("No CJK font found. Install fonts-noto-cjk or fonts-wqy-microhei.")


def _f(size):
    return ImageFont.truetype(FONT_PATH, size)


def detect_bg_color(img: Image.Image):
    """从图片四角采样，判定底色（深色 / 浅色）。返回 (bg_rgb, is_dark)。"""
    W, H = img.size
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    # 取四角 10×10 块的平均
    corners = [(0, 0), (W - 10, 0), (0, H - 10), (W - 10, H - 10)]
    r_sum, g_sum, b_sum, cnt = 0, 0, 0, 0
    for cx, cy in corners:
        crop = img.crop((cx, cy, cx + 10, cy + 10))
        for px in crop.getdata():
            r_sum += px[0]
            g_sum += px[1]
            b_sum += px[2]
            cnt += 1
    r, g, b = r_sum // cnt, g_sum // cnt, b_sum // cnt
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (r, g, b), luminance < 128


def build_footer_watermark(width: int, is_dark_bg: bool, scale: float = 1.0):
    """
    构建一个水平 footer 水印条。宽度 = width，高度自动。
    is_dark_bg=True 时使用透明底 + 白字。False 时透明底 + 深色字。
    """
    icon = int(56 * scale)
    pad = int(14 * scale)
    text_gap = int(14 * scale)

    # 计算文字尺寸
    f_adps = _f(int(30 * scale))
    f_sub = _f(int(12 * scale))
    f_by = _f(int(16 * scale))

    # 元素排布：[icon] [ADPS wordmark stack]     [by Jia Huang · 黄佳]
    # 但按用户要求：ADPS logo 在上，"by Jia Huang" 在下，我们纵向压两行
    # 布局改成：[icon + ADPS 单行]  换行  [by Jia Huang · 黄佳 居中]

    # Line 1 宽度：icon + gap + "ADPS" text width
    tmp = Image.new("RGBA", (10, 10))
    d = ImageDraw.Draw(tmp)
    adps_bbox = d.textbbox((0, 0), "ADPS", font=f_adps)
    adps_w = adps_bbox[2] - adps_bbox[0]
    sub_bbox = d.textbbox((0, 0), "Agent Design Patterns Society", font=f_sub)
    sub_w = sub_bbox[2] - sub_bbox[0]
    by_bbox = d.textbbox((0, 0), "by Jia Huang · 黄佳", font=f_by)
    by_w = by_bbox[2] - by_bbox[0]

    text_col_w = max(adps_w, sub_w, by_w)
    line1_w = icon + text_gap + text_col_w
    footer_h = icon + pad * 2 + int(22 * scale)  # icon + by-line

    footer = Image.new("RGBA", (width, footer_h), (0, 0, 0, 0))
    fd = ImageDraw.Draw(footer)

    # 居中起点
    start_x = (width - line1_w) // 2
    y0 = pad

    # 1. Navy 圆角方块 icon
    fd.rounded_rectangle(
        [(start_x, y0), (start_x + icon, y0 + icon)],
        radius=int(6 * scale),
        fill=NAVY,
    )

    # 2. dot grid
    dot_r = max(1, int(0.9 * scale))
    dot_spacing = int(6.4 * scale)
    dot_start = int(7 * scale)
    dot_fill = (INK_LIGHT[0], INK_LIGHT[1], INK_LIGHT[2], 107)
    for row in range(7):
        for col in range(6):
            cx = start_x + dot_start + col * dot_spacing
            cy = y0 + dot_start + row * dot_spacing
            if cx <= start_x + icon - 3 and cy <= y0 + icon - 3:
                fd.ellipse(
                    [(cx - dot_r, cy - dot_r), (cx + dot_r, cy + dot_r)],
                    fill=dot_fill,
                )

    # 3. gold "A" mark
    gold_w = max(2, int(3.0 * scale))
    def _s(v):  # scale within icon (SVG coords 0-64)
        return int(v * (icon / 64.0))
    a_left = (start_x + _s(13), y0 + _s(49))
    a_top = (start_x + _s(31.5), y0 + _s(13))
    a_right = (start_x + _s(50), y0 + _s(49))
    a_cross_l = (start_x + _s(21.5), y0 + _s(34.5))
    a_cross_r = (start_x + _s(41.5), y0 + _s(34.5))
    fd.line([a_left, a_top], fill=GOLD, width=gold_w)
    fd.line([a_top, a_right], fill=GOLD, width=gold_w)
    fd.line([a_cross_l, a_cross_r], fill=GOLD, width=gold_w)

    # 三个白小方点
    sq = max(2, int(3.0 * scale))
    for cx, cy in [a_left, a_top, a_right]:
        fd.rectangle(
            [(cx - sq // 2, cy - sq // 2), (cx + sq // 2, cy + sq // 2)],
            fill=INK_LIGHT,
        )

    # 4. 右侧文字栈
    text_x = start_x + icon + text_gap
    text_color_primary = INK_LIGHT if is_dark_bg else NAVY
    text_color_sub = (203, 213, 225) if is_dark_bg else INK_MUTED
    fd.text((text_x, y0 + int(2 * scale)), "ADPS", font=f_adps, fill=text_color_primary)
    fd.text(
        (text_x, y0 + int(38 * scale)),
        "Agent Design Patterns Society",
        font=f_sub,
        fill=text_color_sub,
    )

    # 5. "by Jia Huang · 黄佳" 居中在 footer 底部
    by_x = (width - by_w) // 2
    by_y = y0 + icon + int(6 * scale)
    fd.text((by_x, by_y), "by Jia Huang · 黄佳", font=f_by, fill=text_color_primary)

    return footer, footer_h


def add_watermark(src_path: str, dst_path: str):
    """
    在源图底部扩一条 footer 条,把水印放里面。
    """
    src = Image.open(src_path).convert("RGBA")
    W, H = src.size

    bg_rgb, is_dark = detect_bg_color(src)
    bg_rgba = bg_rgb + (255,)

    # scale 按图宽自动
    if W >= 2200:
        scale = 1.4
    elif W >= 1600:
        scale = 1.15
    elif W >= 1200:
        scale = 1.0
    elif W >= 900:
        scale = 0.85
    else:
        scale = 0.7

    footer, footer_h = build_footer_watermark(W, is_dark, scale=scale)

    # 新画布 = 原图 + footer 高度
    new_h = H + footer_h
    out = Image.new("RGBA", (W, new_h), bg_rgba)
    out.paste(src, (0, 0), src)

    # footer 直接覆盖到底部
    out.paste(footer, (0, H), footer)

    # 存
    out.save(dst_path, "PNG", optimize=True)
    print(f"Watermarked: {dst_path} ({W}x{H} → {W}x{new_h}, bg={'dark' if is_dark else 'light'} rgb={bg_rgb}, scale={scale})")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python3 add_watermark.py <input.png> <output.png>")
        sys.exit(1)

    add_watermark(sys.argv[1], sys.argv[2])
