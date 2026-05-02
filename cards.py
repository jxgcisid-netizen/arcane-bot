import io
import math
import random
from PIL import Image, ImageDraw
from main import TEAL, TEAL_DIM, RED, RED_DIM, GOLD, SILVER, BRONZE, RANK_COLORS, RANK_BG, RANK_BAR, get_font
from utils import fetch_avatar, make_circle_avatar


async def create_welcome_card(member, member_count):
    w, h = 800, 440
    img = Image.new("RGBA", (w, h), (30, 33, 40))
    draw = ImageDraw.Draw(img)
    teal, tdim = TEAL, TEAL_DIM

    for y in range(h):
        t = y / h
        draw.line([(0, y), (w, y)], fill=(int(30 + t * 10), int(33 + t * 8), int(40 + t * 20)))

    for r in range(180, 0, -2):
        a = int(35 * (1 - r / 180))
        draw.ellipse((-60 - r, -60 - r, -60 + r, -60 + r), fill=(*teal, a))
    for r in range(200, 0, -2):
        a = int(40 * (1 - r / 200))
        draw.ellipse((w - 80 - r, h - 80 - r, w - 80 + r, h - 80 + r), fill=(*teal, a))

    for i in range(-h, w + h, 22):
        draw.line([(i, 0), (i + h, h)], fill=(40, 44, 52), width=1)

    draw.rectangle([0, 0, w, 5], fill=teal)
    draw.rectangle([0, h - 5, w, h], fill=teal)
    draw.rectangle([0, 0, 5, h], fill=teal)
    draw.rectangle([w - 5, 0, w, h], fill=teal)

    c2, lw = 25, 3
    for px, py, dx, dy in [(18, 18, 1, 1), (w - 18, 18, -1, 1), (18, h - 18, 1, -1), (w - 18, h - 18, -1, -1)]:
        draw.line([(px, py), (px + dx * c2, py)], fill=teal, width=lw)
        draw.line([(px, py), (px, py + dy * c2)], fill=teal, width=lw)

    random.seed(42)
    for _ in range(28):
        sx, sy, sr = random.randint(50, w - 50), random.randint(50, h - 50), random.randint(1, 3)
        draw.ellipse((sx - sr, sy - sr, sx + sr, sy + sr), fill=(*teal, random.randint(60, 160)))

    acx, acy, ar = w // 2, 170, 98
    for ring in range(30, 0, -2):
        a = int(80 * (1 - ring / 30))
        draw.ellipse((acx - ar - ring - 8, acy - ar - ring - 8, acx + ar + ring + 8, acy + ar + ring + 8), fill=(*teal, a))
    for angle in range(0, 360, 15):
        rad, rad2 = math.radians(angle), math.radians(angle + 8)
        rx = ar + 18
        draw.line([(acx + rx * math.cos(rad), acy + rx * math.sin(rad)), (acx + rx * math.cos(rad2), acy + rx * math.sin(rad2))], fill=tdim, width=2)
    draw.ellipse((acx - ar - 9, acy - ar - 9, acx + ar + 9, acy + ar + 9), fill=teal)
    draw.ellipse((acx - ar - 3, acy - ar - 3, acx + ar + 3, acy + ar + 3), fill=(30, 33, 40))
    draw.ellipse((acx - ar, acy - ar, acx + ar, acy + ar), fill=(60, 70, 85))

    av_img = await fetch_avatar(member)
    if av_img:
        circle = make_circle_avatar(av_img, ar * 2)
        img.paste(circle, (acx - ar, acy - ar), circle)

    font_label = get_font(21, True)
    label = "✦  WELCOME TO THE SERVER  ✦"
    lbw = font_label.getbbox(label)[2] - font_label.getbbox(label)[0]
    draw.text(((w - lbw) // 2, 295), label, fill=teal, font=font_label)

    draw.line([(80, 310), (w // 2 - lbw // 2 - 15, 310)], fill=tdim, width=1)
    draw.line([(w // 2 + lbw // 2 + 15, 310), (w - 80, 310)], fill=tdim, width=1)

    font_name = get_font(50, True)
    name_text = f"Welcome, {member.display_name}!"
    nw = font_name.getbbox(name_text)[2] - font_name.getbbox(name_text)[0]
    draw.text(((w - nw) // 2 + 2, 325), name_text, fill=(20, 60, 60), font=font_name)
    draw.text(((w - nw) // 2, 323), name_text, fill=(255, 255, 255), font=font_name)

    font_member = get_font(26, True)
    mt = f"Member #{member_count}"
    mw = font_member.getbbox(mt)[2] - font_member.getbbox(mt)[0]
    draw.text(((w - mw) // 2, 385), mt, fill=(160, 175, 190), font=font_member)

    for i, dx in enumerate([-30, -15, 0, 15, 30]):
        col = teal if i == 2 else tdim
        r2 = 5 if i == 2 else 3
        draw.ellipse((w // 2 + dx - r2, 415 - r2, w // 2 + dx + r2, 415 + r2), fill=col)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def create_goodbye_card(member, member_count):
    w, h = 800, 440
    img = Image.new("RGBA", (w, h), (30, 25, 25))
    draw = ImageDraw.Draw(img)
    red, rdim = RED, RED_DIM

    for y in range(h):
        t = y / h
        draw.line([(0, y), (w, y)], fill=(int(30 + t * 15), int(25 + t * 5), int(25 + t * 5)))

    for r in range(180, 0, -2):
        a = int(35 * (1 - r / 180))
        draw.ellipse((-60 - r, -60 - r, -60 + r, -60 + r), fill=(*red, a))
    for r in range(200, 0, -2):
        a = int(40 * (1 - r / 200))
        draw.ellipse((w - 80 - r, h - 80 - r, w - 80 + r, h - 80 + r), fill=(*red, a))

    for i in range(-h, w + h, 22):
        draw.line([(i, 0), (i + h, h)], fill=(40, 32, 32), width=1)

    draw.rectangle([0, 0, w, 5], fill=red)
    draw.rectangle([0, h - 5, w, h], fill=red)
    draw.rectangle([0, 0, 5, h], fill=red)
    draw.rectangle([w - 5, 0, w, h], fill=red)

    c2, lw = 25, 3
    for px, py, dx, dy in [(18, 18, 1, 1), (w - 18, 18, -1, 1), (18, h - 18, 1, -1), (w - 18, h - 18, -1, -1)]:
        draw.line([(px, py), (px + dx * c2, py)], fill=red, width=lw)
        draw.line([(px, py), (px, py + dy * c2)], fill=red, width=lw)

    random.seed(99)
    for _ in range(28):
        sx, sy, sr = random.randint(50, w - 50), random.randint(50, h - 50), random.randint(1, 3)
        draw.ellipse((sx - sr, sy - sr, sx + sr, sy + sr), fill=(*red, random.randint(60, 150)))

    acx, acy, ar = w // 2, 170, 98
    for ring in range(30, 0, -2):
        a = int(80 * (1 - ring / 30))
        draw.ellipse((acx - ar - ring - 8, acy - ar - ring - 8, acx + ar + ring + 8, acy + ar + ring + 8), fill=(*red, a))
    for angle in range(0, 360, 15):
        rad, rad2 = math.radians(angle), math.radians(angle + 8)
        rx = ar + 18
        draw.line([(acx + rx * math.cos(rad), acy + rx * math.sin(rad)), (acx + rx * math.cos(rad2), acy + rx * math.sin(rad2))], fill=rdim, width=2)
    draw.ellipse((acx - ar - 9, acy - ar - 9, acx + ar + 9, acy + ar + 9), fill=red)
    draw.ellipse((acx - ar - 3, acy - ar - 3, acx + ar + 3, acy + ar + 3), fill=(30, 25, 25))
    draw.ellipse((acx - ar, acy - ar, acx + ar, acy + ar), fill=(70, 55, 55))

    av_img = await fetch_avatar(member)
    if av_img:
        circle = make_circle_avatar(av_img, ar * 2)
        img.paste(circle, (acx - ar, acy - ar), circle)

    font_label = get_font(21, True)
    label = "✦  GOODBYE  ✦"
    lbw = font_label.getbbox(label)[2] - font_label.getbbox(label)[0]
    draw.text(((w - lbw) // 2, 295), label, fill=red, font=font_label)

    draw.line([(80, 310), (w // 2 - lbw // 2 - 15, 310)], fill=rdim, width=1)
    draw.line([(w // 2 + lbw // 2 + 15, 310), (w - 80, 310)], fill=rdim, width=1)

    font_name = get_font(50, True)
    name_text = f"Goodbye, {member.display_name}..."
    nw = font_name.getbbox(name_text)[2] - font_name.getbbox(name_text)[0]
    draw.text(((w - nw) // 2 + 2, 325), name_text, fill=(80, 20, 20), font=font_name)
    draw.text(((w - nw) // 2, 323), name_text, fill=(255, 255, 255), font=font_name)

    font_member = get_font(26, True)
    mt = f"Members remaining: {member_count}"
    mw = font_member.getbbox(mt)[2] - font_member.getbbox(mt)[0]
    draw.text(((w - mw) // 2, 385), mt, fill=(180, 140, 140), font=font_member)

    for i, dx in enumerate([-30, -15, 0, 15, 30]):
        col = red if i == 2 else rdim
        r2 = 5 if i == 2 else 3
        draw.ellipse((w // 2 + dx - r2, 415 - r2, w // 2 + dx + r2, 415 + r2), fill=col)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def create_rank_card(member, level, xp, needed_xp, rank):
    w, h = 900, 220
    img = Image.new("RGBA", (w, h), (35, 39, 42))
    draw = ImageDraw.Draw(img)
    teal = TEAL

    # 右侧装饰三角 — 调窄了一点（从 432 右移到 480，三角形变瘦）
    draw.polygon([(480, 0), (w-100, 0), (w-100, h), (580, h)], fill=teal)

    av_img = await fetch_avatar(member)
    av_size = 115
    if av_img:
        circle = make_circle_avatar(av_img, av_size)
        img.paste(circle, (18, 15), circle)
    else:
        draw.ellipse((18, 15, 18 + av_size, 15 + av_size), fill=(80, 85, 100))

    # 字体调大：名称从 36 调到 42，信息从 20 调到 24
    font_name = get_font(42, True)
    font_info = get_font(24, True)
    
    draw.text((152, 25), f"@{member.display_name}", fill=(255, 255, 255), font=font_name)
    draw.line([(150, 80), (w-101, 80)], fill=teal, width=2)
    draw.text((152, 95), f"Level: {level}", fill=(210, 215, 218), font=font_info)
    draw.text((330, 95), f"XP: {xp} / {needed_xp}", fill=(210, 215, 218), font=font_info)
    draw.text((550, 95), f"Rank: {rank}", fill=(210, 215, 218), font=font_info)

    # 进度条位置微调
    bar_y, bar_x, bar_w, bar_h, r = 150, 11, w-172, 34, 17
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=r, fill=(255, 255, 255))
    if needed_xp > 0:
        progress = int((xp / needed_xp) * bar_w)
        if progress > 0:
            draw.rounded_rectangle([bar_x, bar_y, bar_x + max(progress, r * 2), bar_y + bar_h], radius=r, fill=teal)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

async def create_leaderboard_card(guild, top_users, mode="xp"):
    row_h, av_w, img_w, header = 90, 82, 740, 70
    img_h = header + row_h * len(top_users) + 20
    bg = (26, 29, 36)
    teal = TEAL

    img = Image.new("RGBA", (img_w, img_h), bg)
    draw = ImageDraw.Draw(img)

    for i in range(-img_h, img_w + img_h, 28):
        draw.line([(i, 0), (i + img_h, img_h)], fill=(30, 33, 41), width=1)

    draw.rectangle([0, 0, img_w, header], fill=(32, 36, 45))
    draw.rectangle([0, header - 3, img_w, header], fill=teal)

    title = "🏆  打字排行榜  —  XP" if mode == "xp" else "🎙️  语音排行榜  —  Voice XP"
    font_title = get_font(28, True)
    tw = font_title.getbbox(title)[2] - font_title.getbbox(title)[0]
    draw.text(((img_w - tw) // 2, 20), title, fill=(220, 228, 240), font=font_title)

    font_header = get_font(18, True)
    draw.text((50, header - 20), "排名", fill=(150, 155, 160), font=font_header)
    draw.text((130, header - 20), "用户", fill=(150, 155, 160), font=font_header)
    draw.text((img_w - 180, header - 20), "等级", fill=(150, 155, 160), font=font_header)
    draw.text((img_w - 100, header - 20), "经验", fill=(150, 155, 160), font=font_header)

    for i, user in enumerate(top_users):
        rank = i + 1
        y_top = header + i * row_h
        level = user["level"]
        xp_val = user["xp"] if mode == "xp" else user["voice_xp"]
        needed = user["needed_xp"]

        rank_col = RANK_COLORS.get(rank, (140, 150, 170))
        row_bg = RANK_BG.get(rank, (30, 34, 42))
        bar_col = RANK_BAR.get(rank, teal)

        draw.rectangle([0, y_top, img_w, y_top + row_h], fill=row_bg)
        if rank <= 3:
            draw.rectangle([0, y_top, 5, y_top + row_h], fill=rank_col)

        av_bg = {1: (70, 60, 15), 2: (50, 58, 72), 3: (62, 42, 18)}.get(rank, (42, 48, 60))
        draw.rounded_rectangle([8, y_top + 8, 8 + av_w - 8, y_top + row_h - 8], radius=8, fill=av_bg)
        border_col = rank_col if rank <= 3 else (55, 62, 78)
        draw.rounded_rectangle([7, y_top + 7, 7 + av_w - 6, y_top + row_h - 7], radius=9, outline=border_col, width=2)

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
                font_letter = get_font(24, True)
                letter = member.display_name[0].upper()
                lb = font_letter.getbbox(letter)
                lw2, lh = lb[2] - lb[0], lb[3] - lb[1]
                draw.text((8 + (av_w - 8) // 2 - lw2 // 2, y_top + row_h // 2 - lh // 2), letter,
                          fill=rank_col if rank <= 3 else (150, 160, 175), font=font_letter)

        text_x = 8 + av_w + 4
        text_y = y_top + 18

        font_rank = get_font(26, True)
        rank_str = f"#{rank}"
        draw.text((text_x, text_y), rank_str, fill=rank_col, font=font_rank)
        rw = font_rank.getbbox(rank_str)[2] - font_rank.getbbox(rank_str)[0]

        font_dot = get_font(18, False)
        dot_x = text_x + rw + 10
        draw.text((dot_x, text_y + 3), "•", fill=(75, 85, 105), font=font_dot)

        name = user.get("name") or (member.display_name if member else "???")
        name_str = f"@{name[:16]}"
        font_name = get_font(24, True)
        name_x = dot_x + 16
        draw.text((name_x, text_y + 2), name_str, fill=(220, 228, 240), font=font_name)
        nw2 = font_name.getbbox(name_str)[2] - font_name.getbbox(name_str)[0]

        font_lvl = get_font(22, True)
        lvl_x = name_x + nw2 + 10
        draw.text((lvl_x, text_y + 3), "•", fill=(75, 85, 105), font=font_dot)
        draw.text((lvl_x + 16, text_y + 3), f"LV.{level}", fill=rank_col if rank <= 3 else (160, 175, 195), font=font_lvl)

        font_xp = get_font(18, False)
        xp_str = f"{xp_val:,} XP" if mode == "xp" else f"{xp_val:,} VP"
        xw = font_xp.getbbox(xp_str)[2] - font_xp.getbbox(xp_str)[0]
        draw.text((img_w - xw - 16, text_y + 5), xp_str, fill=(95, 110, 135), font=font_xp)

        bar_x = text_x
        bar_y2 = y_top + row_h - 18
        bar_w = img_w - text_x - 16
        draw.rounded_rectangle([bar_x, bar_y2, bar_x + bar_w, bar_y2 + 6], radius=3, fill=(38, 44, 56))
        if needed > 0:
            prog = max(int((user["xp"] / needed) * bar_w), 8)
            draw.rounded_rectangle([bar_x, bar_y2, bar_x + prog, bar_y2 + 6], radius=3, fill=bar_col)

        if rank < len(top_users):
            draw.line([(av_w + 16, y_top + row_h - 1), (img_w - 16, y_top + row_h - 1)], fill=(38, 43, 54), width=1)

    draw.rectangle([0, img_h - 4, img_w, img_h], fill=teal)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
