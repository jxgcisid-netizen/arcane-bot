import io
import math
import random
from PIL import Image, ImageDraw
from config import TEAL, TEAL_DIM, get_font
from utils.image_utils import fetch_avatar, make_circle_avatar


async def create_welcome_card(member, member_count):
    width, height = 800, 440
    img = Image.new("RGBA", (width, height), (30, 33, 40))
    draw = ImageDraw.Draw(img)
    teal = TEAL
    teal_dim = TEAL_DIM

    # 背景渐变
    for y in range(height):
        t = y / height
        draw.line([(0, y), (width, y)], fill=(int(30 + t * 10), int(33 + t * 8), int(40 + t * 20)))

    # 光晕效果
    for radius in range(180, 0, -2):
        a = int(35 * (1 - radius / 180))
        draw.ellipse((-60 - radius, -60 - radius, -60 + radius, -60 + radius), fill=(*teal, a))
    for radius in range(200, 0, -2):
        a = int(40 * (1 - radius / 200))
        draw.ellipse((width - 80 - radius, height - 80 - radius, width - 80 + radius, height - 80 + radius), fill=(*teal, a))

    # 斜线纹理
    for i in range(-height, width + height, 22):
        draw.line([(i, 0), (i + height, height)], fill=(40, 44, 52), width=1)

    # 边框
    draw.rectangle([0, 0, width, 5], fill=teal)
    draw.rectangle([0, height - 5, width, height], fill=teal)
    draw.rectangle([0, 0, 5, height], fill=teal)
    draw.rectangle([width - 5, 0, width, height], fill=teal)

    # 四角角标
    c2, lw = 25, 3
    for px, py, dx, dy in [(18, 18, 1, 1), (width - 18, 18, -1, 1), (18, height - 18, 1, -1), (width - 18, height - 18, -1, -1)]:
        draw.line([(px, py), (px + dx * c2, py)], fill=teal, width=lw)
        draw.line([(px, py), (px, py + dy * c2)], fill=teal, width=lw)

    # 星星粒子
    random.seed(42)
    for _ in range(28):
        sx, sy, sr = random.randint(50, width - 50), random.randint(50, height - 50), random.randint(1, 3)
        draw.ellipse((sx - sr, sy - sr, sx + sr, sy + sr), fill=(*teal, random.randint(60, 160)))

    # 头像圆
    av_cx, av_cy, av_r = width // 2, 170, 98
    for ring in range(30, 0, -2):
        a = int(80 * (1 - ring / 30))
        draw.ellipse((av_cx - av_r - ring - 8, av_cy - av_r - ring - 8,
                      av_cx + av_r + ring + 8, av_cy + av_r + ring + 8), fill=(*teal, a))
    for angle in range(0, 360, 15):
        rad, rad2 = math.radians(angle), math.radians(angle + 8)
        rx = av_r + 18
        draw.line([(av_cx + rx * math.cos(rad), av_cy + rx * math.sin(rad)),
                   (av_cx + rx * math.cos(rad2), av_cy + rx * math.sin(rad2))], fill=teal_dim, width=2)
    draw.ellipse((av_cx - av_r - 9, av_cy - av_r - 9, av_cx + av_r + 9, av_cy + av_r + 9), fill=teal)
    draw.ellipse((av_cx - av_r - 3, av_cy - av_r - 3, av_cx + av_r + 3, av_cy + av_r + 3), fill=(30, 33, 40))
    draw.ellipse((av_cx - av_r, av_cy - av_r, av_cx + av_r, av_cy + av_r), fill=(60, 70, 85))

    av_img = await fetch_avatar(member)
    if av_img:
        circle = make_circle_avatar(av_img, av_r * 2)
        img.paste(circle, (av_cx - av_r, av_cy - av_r), circle)

    # 欢迎标题
    font_label = get_font(22, True)
    label = "✦  WELCOME TO THE SERVER  ✦"
    lbw = font_label.getbbox(label)[2] - font_label.getbbox(label)[0]
    draw.text(((width - lbw) // 2, 295), label, fill=teal, font=font_label)

    # 分隔线
    draw.line([(80, 310), (width // 2 - lbw // 2 - 15, 310)], fill=teal_dim, width=1)
    draw.line([(width // 2 + lbw // 2 + 15, 310), (width - 80, 310)], fill=teal_dim, width=1)

    # 欢迎语
    font_name = get_font(52, True)
    name_text = f"Welcome, {member.display_name}!"
    nw = font_name.getbbox(name_text)[2] - font_name.getbbox(name_text)[0]
    draw.text(((width - nw) // 2 + 2, 325), name_text, fill=(20, 60, 60), font=font_name)
    draw.text(((width - nw) // 2, 323), name_text, fill=(255, 255, 255), font=font_name)

    # 成员数量
    font_member = get_font(28, True)
    mt = f"Member #{member_count}"
    mw = font_member.getbbox(mt)[2] - font_member.getbbox(mt)[0]
    draw.text(((width - mw) // 2, 385), mt, fill=(160, 175, 190), font=font_member)

    # 底部装饰点
    for i, dx in enumerate([-30, -15, 0, 15, 30]):
        col = teal if i == 2 else teal_dim
        r2 = 5 if i == 2 else 3
        draw.ellipse((width // 2 + dx - r2, 415 - r2, width // 2 + dx + r2, 415 + r2), fill=col)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
