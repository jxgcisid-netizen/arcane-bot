import io
from PIL import Image, ImageDraw
from config import TEAL, get_font
from utils.image_utils import fetch_avatar, make_circle_avatar


async def create_rank_card(member, level, xp, needed_xp, rank):
    width, height = 800, 200
    img = Image.new("RGBA", (width, height), (35, 39, 42))
    draw = ImageDraw.Draw(img)

    # 右侧斜切装饰块
    draw.polygon([(532, 0), (800, 0), (800, 200), (684, 200)], fill=TEAL)

    # 头像
    av_size = 115
    av_x = 18
    av_y = 15
    av_img = await fetch_avatar(member)
    if av_img:
        circle = make_circle_avatar(av_img, av_size)
        img.paste(circle, (av_x, av_y), circle)
    else:
        draw.ellipse((av_x, av_y, av_x + av_size, av_y + av_size), fill=(80, 85, 100))

    font_name = get_font("bold", 38)
    font_info = get_font("regular", 26)

    nickname = member.display_name[:18] + "..." if len(member.display_name) > 18 else member.display_name
    draw.text((152, 30), f"@{nickname}", fill=(255, 255, 255), font=font_name)
    draw.line([(150, 82), (699, 82)], fill=TEAL, width=2)
    draw.text((152, 90), f"Level: {level}", fill=(210, 215, 218), font=font_info)
    draw.text((310, 90), f"XP: {xp} / {needed_xp}", fill=(210, 215, 218), font=font_info)
    draw.text((490, 90), f"Rank: {rank}", fill=(210, 215, 218), font=font_info)

    # 进度条
    bar_x, bar_y, bar_w, bar_h, r = 11, 150, 628, 34, 17
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=r, fill=(255, 255, 255))
    progress = int((xp / needed_xp) * bar_w) if needed_xp > 0 else 0
    draw.rounded_rectangle([bar_x, bar_y, bar_x + max(progress, r * 2), bar_y + bar_h], radius=r, fill=TEAL)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
