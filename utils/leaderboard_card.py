import io
from PIL import Image, ImageDraw
from config import TEAL, RANK_COLORS, RANK_BG, RANK_BAR, get_font, get_optimal_font
from utils.image_utils import fetch_avatar


async def create_leaderboard_card(guild, top_users, mode="xp"):
    row_h = 90
    av_w = 82
    img_w = 740
    header = 70
    img_h = header + row_h * len(top_users) + 20

    bg = (26, 29, 36)
    teal = TEAL

    img = Image.new("RGBA", (img_w, img_h), bg)
    draw = ImageDraw.Draw(img)

    # 背景斜纹
    for i in range(-img_h, img_w + img_h, 28):
        draw.line([(i, 0), (i + img_h, img_h)], fill=(30, 33, 41), width=1)

    # 顶部标题栏
    draw.rectangle([0, 0, img_w, header], fill=(32, 36, 45))
    draw.rectangle([0, header - 3, img_w, header], fill=teal)

    # 标题（自适应）
    title = "🏆  打字排行榜  —  XP" if mode == "xp" else "🎙️  语音排行榜  —  Voice XP"
    title_font, title_size = get_optimal_font(title, img_w - 100, initial_size=28, bold=True)
    tw = title_font.getbbox(title)[2] - title_font.getbbox(title)[0]
    draw.text(((img_w - tw) // 2, 20), title, fill=(220, 228, 240), font=title_font)

    # 表头字体
    header_font = get_font(18, bold=True)
    draw.text((50, header - 20), "排名", fill=(150, 155, 160), font=header_font)
    draw.text((130, header - 20), "用户", fill=(150, 155, 160), font=header_font)
    draw.text((img_w - 180, header - 20), "等级", fill=(150, 155, 160), font=header_font)
    draw.text((img_w - 100, header - 20), "经验", fill=(150, 155, 160), font=header_font)

    for i, user in enumerate(top_users):
        rank = i + 1
        y_top = header + i * row_h
        level = user["level"]
        xp_val = user["xp"] if mode == "xp" else user["voice_xp"]
        needed = user["needed_xp"]

        rank_col = RANK_COLORS.get(rank, (140, 150, 170))
        row_bg = RANK_BG.get(rank, (30, 34, 42))
        bar_col = RANK_BAR.get(rank, teal)

        # 行背景
        draw.rectangle([0, y_top, img_w, y_top + row_h], fill=row_bg)

        # 前3名左侧彩色竖条
        if rank <= 3:
            draw.rectangle([0, y_top, 5, y_top + row_h], fill=rank_col)

        # 头像区域
        av_bg = {1: (70, 60, 15), 2: (50, 58, 72), 3: (62, 42, 18)}.get(rank, (42, 48, 60))
        draw.rounded_rectangle([8, y_top + 8, 8 + av_w - 8, y_top + row_h - 8], radius=8, fill=av_bg)
        border_col = rank_col if rank <= 3 else (55, 62, 78)
        draw.rounded_rectangle([7, y_top + 7, 7 + av_w - 6, y_top + row_h - 7],
                               radius=9, outline=border_col, width=2)

        member = user.get("member")
        if member:
            av_img = await fetch_avatar(member, size=128)
            if av_img:
                av_size = av_w - 16
                av = av_img.resize((av_size, av_size), Image.Resampling.LANCZOS)
                mask = Image.new("L", (av_size, av_size), 0)
                ImageDraw.Draw(mask).rounded_rectangle([0, 0, av_size, av_size], radius=6, fill=255)
                av_circle = Image.new("RGBA", (av_size, av_size))
                av_circle.paste(av, (0, 0), av)
                av_circle.putalpha(mask)
                img.paste(av_circle, (12, y_top + 12), av_circle)
            else:
                # 无头像时显示首字母
                letter_font = get_font(24, bold=True)
                letter = member.display_name[0].upper()
                lb = letter_font.getbbox(letter)
                lw2, lh = lb[2] - lb[0], lb[3] - lb[1]
                draw.text((8 + (av_w - 8) // 2 - lw2 // 2, y_top + row_h // 2 - lh // 2),
                          letter, fill=rank_col if rank <= 3 else (150, 160, 175), font=letter_font)

        text_x = 8 + av_w + 4
        text_y = y_top + 18

        # 排名数字
        rank_font = get_font(26, bold=True)
        rank_str = f"#{rank}"
        draw.text((text_x, text_y), rank_str, fill=rank_col, font=rank_font)
        rw = rank_font.getbbox(rank_str)[2] - rank_font.getbbox(rank_str)[0]

        # 分隔点
        dot_font = get_font(18, bold=False)
        dot_x = text_x + rw + 10
        draw.text((dot_x, text_y + 3), "•", fill=(75, 85, 105), font=dot_font)

        # 用户名（自适应）
        name = user.get("name") or (member.display_name if member else "???")
        name_str = f"@{name[:16]}"
        name_font, name_size = get_optimal_font(name_str, 200, initial_size=24, bold=True)
        name_x = dot_x + 16
        draw.text((name_x, text_y + 2), name_str, fill=(220, 228, 240), font=name_font)
        
        try:
            nw2 = name_font.getbbox(name_str)[2] - name_font.getbbox(name_str)[0]
        except:
            nw2 = len(name_str) * name_size // 2

        # 等级
        lvl_font = get_font(22, bold=True)
        lvl_x = name_x + nw2 + 10
        draw.text((lvl_x, text_y + 3), "•", fill=(75, 85, 105), font=dot_font)
        draw.text((lvl_x + 16, text_y + 3), f"LV.{level}", fill=rank_col if rank <= 3 else (160, 175, 195), font=lvl_font)

        # 经验数值
        xp_font = get_font(18, bold=False)
        xp_str = f"{xp_val:,} XP" if mode == "xp" else f"{xp_val:,} VP"
        xw = xp_font.getbbox(xp_str)[2] - xp_font.getbbox(xp_str)[0]
        draw.text((img_w - xw - 16, text_y + 5), xp_str, fill=(95, 110, 135), font=xp_font)

        # 进度条
        bar_x = text_x
        bar_y2 = y_top + row_h - 18
        bar_w = img_w - text_x - 16
        draw.rounded_rectangle([bar_x, bar_y2, bar_x + bar_w, bar_y2 + 6], radius=3, fill=(38, 44, 56))
        if needed > 0:
            prog = max(int((user["xp"] / needed) * bar_w), 8)
            draw.rounded_rectangle([bar_x, bar_y2, bar_x + prog, bar_y2 + 6], radius=3, fill=bar_col)

        # 行分隔线
        if rank < len(top_users):
            draw.line([(av_w + 16, y_top + row_h - 1), (img_w - 16, y_top + row_h - 1)],
                      fill=(38, 43, 54), width=1)

    # 底部青蓝条
    draw.rectangle([0, img_h - 4, img_w, img_h], fill=teal)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
