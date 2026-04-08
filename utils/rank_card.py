import io
from PIL import Image, ImageDraw
from config import TEAL, get_font
from utils.image_utils import fetch_avatar, make_circle_avatar


async def create_rank_card(member, level, xp, needed_xp, rank):
    width, height = 800, 220
    img = Image.new("RGBA", (width, height), (35, 39, 42))
    draw = ImageDraw.Draw(img)
    teal = TEAL

    # 右侧斜切装饰块
    draw.polygon([(532, 0), (800, 0), (800, height), (684, height)], fill=teal)

    # 头像
    av_size = 115
    av_x, av_y = 18, (height - av_size) // 2
    av_img = await fetch_avatar(member)
    if av_img:
        circle = make_circle_avatar(av_img, av_size)
        img.paste(circle, (av_x, av_y), circle)
    else:
        draw.ellipse((av_x, av_y, av_x + av_size, av_y + av_size), fill=(80, 85, 100))

    # 字体
    font_name = get_font(48, True)   # 用户名 48号粗体
    font_info = get_font(28, True)   # 信息 28号粗体

    nickname = member.display_name[:18] + "..." if len(member.display_name) > 18 else member.display_name
    draw.text((152, 30), f"@{nickname}", fill=(255, 255, 255), font=font_name)
    draw.line([(150, 82), (699, 82)], fill=teal, width=2)
    draw.text((152, 95), f"Level: {level}", fill=(210, 215, 218), font=font_info)
    draw.text((310, 95), f"XP: {xp} / {needed_xp}", fill=(210, 215, 218), font=font_info)
    draw.text((490, 95), f"Rank: {rank}", fill=(210, 215, 218), font=font_info)

    # 进度条
    bar_y = 150
    bar_x, bar_w, bar_h, r = 11, 628, 34, 17
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=r, fill=(255, 255, 255))
    progress = int((xp / needed_xp) * bar_w) if needed_xp > 0 else 0
    if progress > 0:
        draw.rounded_rectangle([bar_x, bar_y, bar_x + max(progress, r * 2), bar_y + bar_h], radius=r, fill=teal)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
