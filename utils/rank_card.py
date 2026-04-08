import io
from PIL import Image, ImageDraw
from config import TEAL, get_font, get_optimal_font
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

    # 用户名（自适应字体）
    nickname = member.display_name[:18] + "..." if len(member.display_name) > 18 else member.display_name
    display_name = f"@{nickname}"
    name_font, name_size = get_optimal_font(display_name, 500, initial_size=48, bold=True)
    
    # 测量用户名高度
    try:
        bbox = name_font.getbbox(display_name)
        name_height = bbox[3] - bbox[1]
    except:
        name_height = name_size
    
    name_y = 35
    draw.text((152, name_y), display_name, fill=(255, 255, 255), font=name_font)
    
    # 分隔线（在用户名下方）
    line_y = name_y + name_height + 10
    draw.line([(150, line_y), (699, line_y)], fill=teal, width=2)

    # 信息文字（固定大字号）
    info_font = get_font(28, bold=True)
    info_y = line_y + 15
    
    draw.text((152, info_y), f"Level: {level}", fill=(210, 215, 218), font=info_font)
    draw.text((310, info_y), f"XP: {xp} / {needed_xp}", fill=(210, 215, 218), font=info_font)
    draw.text((490, info_y), f"Rank: #{rank}", fill=(210, 215, 218), font=info_font)

    # 进度条
    bar_y = info_y + 40
    bar_x, bar_w, bar_h, r = 11, 628, 34, 17
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=r, fill=(255, 255, 255))
    progress = int((xp / needed_xp) * bar_w) if needed_xp > 0 else 0
    if progress > 0:
        draw.rounded_rectangle([bar_x, bar_y, bar_x + max(progress, r * 2), bar_y + bar_h], radius=r, fill=teal)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
