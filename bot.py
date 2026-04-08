import discord
from discord.ext import commands
from discord import app_commands
import os
import aiohttp
import asyncio
from datetime import datetime
import sqlite3
import threading
from PIL import Image, ImageDraw, ImageFont
import io
import math
import random

# ==================== 配置 ====================
TOKEN = os.getenv("DISCORD_TOKEN")
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ==================== 数据库 ====================
db_lock = threading.Lock()

def get_conn():
    conn = sqlite3.connect("/app/data/bot_data.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            guild_id TEXT, user_id TEXT, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, voice_xp INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS level_roles (
            guild_id TEXT, level INTEGER, role_id TEXT,
            PRIMARY KEY (guild_id, level)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS reaction_roles (
            guild_id TEXT, message_id TEXT, emoji TEXT, role_id TEXT,
            PRIMARY KEY (guild_id, message_id, emoji)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS counters (
            guild_id TEXT, counter_type TEXT, channel_id TEXT, message_template TEXT, current_value INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, counter_type)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS welcome_settings (
            guild_id TEXT PRIMARY KEY, channel_id TEXT, message TEXT, color TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id TEXT PRIMARY KEY, xp_rate REAL DEFAULT 1.0, voice_xp_rate REAL DEFAULT 1.0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS log_settings (
            guild_id TEXT PRIMARY KEY, message_log_channel TEXT, voice_log_channel TEXT, mod_log_channel TEXT
        )''')
        conn.commit()

init_db()

# ==================== 数据库辅助函数 ====================
def db_get_user(guild_id, user_id):
    with db_lock:
        with get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE guild_id=? AND user_id=?", (str(guild_id), str(user_id)))
            row = c.fetchone()
            if not row:
                c.execute("INSERT INTO users (guild_id, user_id) VALUES (?, ?)", (str(guild_id), str(user_id)))
                conn.commit()
                return {"xp": 0, "level": 1, "voice_xp": 0}
            return {"xp": row["xp"], "level": row["level"], "voice_xp": row["voice_xp"]}

def db_update_user(guild_id, user_id, data):
    with db_lock:
        with get_conn() as conn:
            conn.execute(
                "UPDATE users SET xp=?, level=?, voice_xp=? WHERE guild_id=? AND user_id=?",
                (data["xp"], data["level"], data["voice_xp"], str(guild_id), str(user_id))
            )
            conn.commit()

def db_get_guild_settings(guild_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM guild_settings WHERE guild_id=?", (str(guild_id),)).fetchone()
        if not row:
            return {"xp_rate": 1.0, "voice_xp_rate": 1.0}
        return {"xp_rate": row["xp_rate"], "voice_xp_rate": row["voice_xp_rate"]}

def get_total_xp(level, current_xp):
    """计算总经验值（包含之前所有等级的累积）"""
    if level <= 1:
        return current_xp
    return int(125 * (level - 1) * level / 2) + current_xp

def db_get_rank(guild_id, user_id):
    """获取用户排名（基于总经验）"""
    with get_conn() as conn:
        user_row = conn.execute(
            "SELECT level, xp FROM users WHERE guild_id=? AND user_id=?",
            (str(guild_id), str(user_id))
        ).fetchone()
        if not user_row:
            return 0
        total_xp = get_total_xp(user_row["level"], user_row["xp"])
        rank = conn.execute(
            """SELECT COUNT(*) + 1 as rank FROM users 
            WHERE guild_id=? AND (125 * (level - 1) * level / 2 + xp) > ?""",
            (str(guild_id), total_xp)
        ).fetchone()["rank"]
        return rank

def db_get_leaderboard(guild_id, limit=10):
    """获取排行榜数据（基于总经验排序）"""
    with get_conn() as conn:
        return conn.execute(
            """SELECT user_id, level, xp, 
            (125 * (level - 1) * level / 2 + xp) as total_xp 
            FROM users WHERE guild_id=? 
            ORDER BY total_xp DESC LIMIT ?""",
            (str(guild_id), limit)
        ).fetchall()

def db_get_level_role(guild_id, level):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT role_id FROM level_roles WHERE guild_id=? AND level=?",
            (str(guild_id), level)
        ).fetchone()
        return row["role_id"] if row else None

def db_get_log_channel(guild_id, channel_type):
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {channel_type} FROM log_settings WHERE guild_id=?",
            (str(guild_id),)
        ).fetchone()
        return row[channel_type] if row else None

def db_get_welcome_channel(guild_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT channel_id FROM welcome_settings WHERE guild_id=?",
            (str(guild_id),)
        ).fetchone()
        return row["channel_id"] if row else None

# ==================== 等级计算 ====================
def xp_needed(level):
    return level * 125

def process_level_up(user_data):
    levels_gained = 0
    while user_data["xp"] >= xp_needed(user_data["level"]):
        user_data["xp"] -= xp_needed(user_data["level"])
        user_data["level"] += 1
        levels_gained += 1
    return user_data, levels_gained

# ==================== 头像下载（支持并发） ====================
async def fetch_avatar(member, size=256):
    """下载并返回圆形裁剪的头像 Image，失败返回 None"""
    try:
        url = member.display_avatar.url.replace("?size=1024", f"?size={size}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    av = Image.open(io.BytesIO(data)).convert("RGBA")
                    return av
    except Exception:
        pass
    return None

async def fetch_member_with_fallback(guild, user_id):
    """获取成员信息，如果已离开则返回虚拟对象"""
    try:
        member = await guild.fetch_member(int(user_id))
        return member, False
    except discord.NotFound:
        try:
            user = await bot.fetch_user(int(user_id))
            class DummyMember:
                def __init__(self, user):
                    self.id = user.id
                    self.display_name = user.name + " (已离开)"
                    self.name = user.name
                    self.display_avatar = user.display_avatar
                    self.color = discord.Color.light_gray()
                def __getattr__(self, name):
                    return None
            return DummyMember(user), True
        except:
            return None, True

def make_circle_avatar(av_img, size):
    av = av_img.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    circle = Image.new("RGBA", (size, size))
    circle.paste(av, (0, 0), av)
    circle.putalpha(mask)
    return circle

# ==================== Rank 卡片（优化版） ====================
async def create_rank_card(member, level, xp, needed_xp, rank):
    width, height = 800, 200
    img = Image.new("RGBA", (width, height), (35, 39, 42))
    draw = ImageDraw.Draw(img)
    teal = (65, 183, 183)
    
    # 右侧斜切装饰块
    draw.polygon([(532, 0), (800, 0), (800, 200), (684, 200)], fill=teal)
    
    # 头像（往上抬：从原来的垂直居中改为 y=15）
    av_size = 115
    av_x = 18
    av_y = 15  # 原来是 (height - av_size) // 2 ≈ 42，现在改到 15
    av_img = await fetch_avatar(member)
    if av_img:
        circle = make_circle_avatar(av_img, av_size)
        img.paste(circle, (av_x, av_y), circle)
    else:
        draw.ellipse((av_x, av_y, av_x+av_size, av_y+av_size), fill=(80, 85, 100))
    
    # 字体（加大字号）
    try:
        font_name = ImageFont.truetype(FONT_BOLD, 38)      # 用户名不变
        font_level = ImageFont.truetype(FONT_BOLD, 32)     # Level 字号加大
        font_xp = ImageFont.truetype(FONT_BOLD, 32)        # XP 字号加大
        font_rank = ImageFont.truetype(FONT_BOLD, 32)      # Rank 字号加大
    except:
        font_name = font_level = font_xp = font_rank = ImageFont.load_default()
    
    # 用户名（Y 位置相应调整，因为头像上移了）
    nickname = member.display_name[:18] + "..." if len(member.display_name) > 18 else member.display_name
    draw.text((152, 25), f"@{nickname}", fill=(255, 255, 255), font=font_name)
    
    # 分隔线（位置调整）
    draw.line([(150, 75), (699, 75)], fill=teal, width=2)
    
    # Level、XP、Rank 三列（字体加大，位置下移）
    draw.text((152, 95), f"Level: {level}", fill=(210, 215, 218), font=font_level)
    draw.text((310, 95), f"XP: {xp} / {needed_xp}", fill=(210, 215, 218), font=font_xp)
    draw.text((510, 95), f"Rank: #{rank}", fill=(210, 215, 218), font=font_rank)
    
    # 进度条（位置调整）
    bar_x, bar_y, bar_w, bar_h, r = 11, 150, 628, 34, 17
    draw.rounded_rectangle([bar_x, bar_y, bar_x+bar_w, bar_y+bar_h], radius=r, fill=(255, 255, 255))
    progress = int((xp / needed_xp) * bar_w) if needed_xp > 0 else 0
    if progress > 0:
        draw.rounded_rectangle([bar_x, bar_y, bar_x+max(progress, r*2), bar_y+bar_h], radius=r, fill=teal)
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
# ==================== Leaderboard 卡片（全新优化版） ====================
async def create_leaderboard_card(guild, top_users):
    """
    top_users: list of dict {
        'member': discord.Member/DummyMember,
        'level': int, 'xp': int, 'total_xp': int, 
        'needed_xp': int, 'is_left': bool
    }
    """
    width, height = 900, 600
    row_height = 52
    header_height = 100
    padding = 30
    
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 颜色定义
    bg_top = (30, 33, 36)
    bg_bottom = (44, 47, 51)
    gold = (255, 215, 0)
    silver = (192, 192, 192)
    bronze = (205, 127, 50)
    teal = (65, 183, 183)
    text_color = (255, 255, 255)
    sub_text = (150, 155, 160)
    
    # 渐变背景
    for y in range(height):
        t = y / height
        r = int(bg_top[0] + (bg_bottom[0] - bg_top[0]) * t)
        g = int(bg_top[1] + (bg_bottom[1] - bg_top[1]) * t)
        b = int(bg_top[2] + (bg_bottom[2] - bg_top[2]) * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    # 顶部装饰条
    draw.rectangle([0, 0, width, 6], fill=teal)
    
    # 字体
    try:
        font_title = ImageFont.truetype(FONT_BOLD, 32)
        font_rank = ImageFont.truetype(FONT_BOLD, 22)
        font_name = ImageFont.truetype(FONT_BOLD, 20)
        font_info = ImageFont.truetype(FONT_REGULAR, 16)
        font_small = ImageFont.truetype(FONT_REGULAR, 14)
    except:
        font_title = font_rank = font_name = font_info = font_small = ImageFont.load_default()
    
    # 标题栏
    icon_size = 50
    try:
        if guild.icon:
            icon_data = await guild.icon.read()
            icon_img = Image.open(io.BytesIO(icon_data)).convert("RGBA")
            icon_circle = make_circle_avatar(icon_img.resize((icon_size, icon_size), Image.Resampling.LANCZOS), icon_size)
            img.paste(icon_circle, (padding, 25), icon_circle)
    except:
        draw.ellipse([padding, 25, padding+icon_size, 25+icon_size], fill=teal)
    
    draw.text((padding + icon_size + 20, 30), f"{guild.name} 排行榜", fill=text_color, font=font_title)
    draw.text((padding + icon_size + 20, 65), "TOP 10 活跃用户", fill=sub_text, font=font_small)
    
    # 列表背景
    list_top = header_height
    list_height = len(top_users) * row_height
    draw.rounded_rectangle(
        [padding//2, list_top, width - padding//2, list_top + list_height + 10],
        radius=12, fill=(35, 39, 42, 230)
    )
    
    # 表头
    header_y = list_top + 8
    draw.text((padding + 50, header_y), "排名", fill=sub_text, font=font_small)
    draw.text((padding + 130, header_y), "用户", fill=sub_text, font=font_small)
    draw.text((width - 180, header_y), "等级", fill=sub_text, font=font_small)
    draw.text((width - 100, header_y), "总经验", fill=sub_text, font=font_small)
    
    # 并发获取所有头像
    avatar_tasks = [fetch_avatar(u['member'], size=128) for u in top_users]
    avatars = await asyncio.gather(*avatar_tasks)
    
    # 绘制每一行
    for i, (user, avatar) in enumerate(zip(top_users, avatars)):
        rank = i + 1
        y_pos = list_top + 30 + (i * row_height)
        
        # 行背景（交替）
        if i % 2 == 0:
            draw.rectangle([padding//2 + 5, y_pos - 2, width - padding//2 - 5, y_pos + row_height - 2], 
                          fill=(40, 44, 48, 100))
        
        # 前三名特殊样式
        if rank == 1:
            draw.rectangle([padding//2 + 5, y_pos - 2, width - padding//2 - 5, y_pos + row_height - 2], 
                          fill=(255, 215, 0, 25))
            rank_color = gold
        elif rank == 2:
            rank_color = silver
        elif rank == 3:
            rank_color = bronze
        else:
            rank_color = sub_text
        
        # 排名数字
        if rank <= 3:
            circle_x = padding + 45
            draw.ellipse([circle_x - 15, y_pos + 6, circle_x + 15, y_pos + 36], fill=rank_color)
            draw.text((circle_x - 7, y_pos + 10), str(rank), fill=bg_top, font=font_rank)
        else:
            draw.text((padding + 38, y_pos + 12), str(rank), fill=rank_color, font=font_info)
        
        # 头像（圆形带边框）
        av_size = 36
        av_x = padding + 90
        av_y = y_pos + 6
        border_color = (150, 150, 150) if user.get('is_left') else (255, 255, 255)
        
        draw.ellipse([av_x - 2, av_y - 2, av_x + av_size + 2, av_y + av_size + 2], fill=border_color)
        if avatar:
            circle_av = make_circle_avatar(avatar, av_size)
            img.paste(circle_av, (av_x, av_y), circle_av)
        else:
            draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=teal)
        
        # 用户名
        name_color = (130, 130, 130) if user.get('is_left') else text_color
        display_name = user['member'].display_name[:18] + "..." if len(user['member'].display_name) > 18 else user['member'].display_name
        draw.text((av_x + av_size + 12, y_pos + 8), display_name, fill=name_color, font=font_name)
        
        # 进度条（底部）
        bar_y = y_pos + 40
        bar_width = width - padding - 150
        xp_ratio = user['xp'] / user['needed_xp'] if user['needed_xp'] > 0 else 0
        draw.rounded_rectangle([padding + 90, bar_y, padding + 90 + bar_width, bar_y + 3], radius=2, fill=(60, 65, 70))
        if xp_ratio > 0:
            bar_color = rank_color if rank <= 3 else teal
            draw.rounded_rectangle([padding + 90, bar_y, padding + 90 + int(bar_width * min(xp_ratio, 1)), bar_y + 3], 
                                  radius=2, fill=bar_color)
        
        # 等级徽章
        level_x = width - 190
        level_str = f"Lv.{user['level']}"
        bbox = draw.textbbox((0, 0), level_str, font=font_info)
        text_w = bbox[2] - bbox[0]
        badge_w = text_w + 16
        draw.rounded_rectangle([level_x, y_pos + 8, level_x + badge_w, y_pos + 32], radius=10, fill=teal)
        draw.text((level_x + 8, y_pos + 10), level_str, fill=bg_top, font=font_info)
        
        # 总经验值
        total_str = f"{user['total_xp']:,}"
        draw.text((width - 100, y_pos + 12), total_str, fill=sub_text, font=font_info)
    
    # 底部装饰
    draw.rectangle([0, height - 4, width, height], fill=teal)
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ==================== Welcome/Goodbye 卡片 ====================
async def create_welcome_card(member, member_count):
    width, height = 800, 420
    img = Image.new("RGBA", (width, height), (30, 33, 40))
    draw = ImageDraw.Draw(img)
    teal = (65, 183, 183)
    teal_dark = (35, 130, 130)
    
    # 背景渐变
    for y in range(height):
        t = y / height
        draw.line([(0, y), (width, y)], fill=(int(30+t*10), int(33+t*8), int(40+t*20)))
    
    # 光晕效果
    for radius in range(180, 0, -2):
        a = int(35 * (1 - radius/180))
        draw.ellipse((-60-radius, -60-radius, -60+radius, -60+radius), fill=(*teal, a))
    
    # 边框和装饰
    draw.rectangle([0, 0, width, 5], fill=teal)
    draw.rectangle([0, height-5, width, height], fill=teal)
    
    # 头像
    av_cx, av_cy, av_r = width//2, 168, 98
    for ring in range(30, 0, -2):
        a = int(80 * (1 - ring/30))
        draw.ellipse((av_cx-av_r-ring-8, av_cy-av_r-ring-8, av_cx+av_r+ring+8, av_cy+av_r+ring+8), fill=(*teal, a))
    
    draw.ellipse((av_cx-av_r-9, av_cy-av_r-9, av_cx+av_r+9, av_cy+av_r+9), fill=teal)
    draw.ellipse((av_cx-av_r-3, av_cy-av_r-3, av_cx+av_r+3, av_cy+av_r+3), fill=(30, 33, 40))
    
    av_img = await fetch_avatar(member)
    if av_img:
        circle = make_circle_avatar(av_img, av_r*2)
        img.paste(circle, (av_cx-av_r, av_cy-av_r), circle)
    
    # 文字
    try:
        font_label = ImageFont.truetype(FONT_BOLD, 16)
        font_name = ImageFont.truetype(FONT_BOLD, 42)
        font_member = ImageFont.truetype(FONT_REGULAR, 24)
    except:
        font_label = font_name = font_member = ImageFont.load_default()
    
    label = "✦ WELCOME TO THE SERVER ✦"
    try:
        lbw = font_label.getbbox(label)[2] - font_label.getbbox(label)[0]
    except:
        lbw = len(label) * 10
    draw.text(((width-lbw)//2, 288), label, fill=teal, font=font_label)
    
    name_text = f"Welcome, {member.display_name}!"
    try:
        nw = font_name.getbbox(name_text)[2] - font_name.getbbox(name_text)[0]
    except:
        nw = len(name_text) * 20
    draw.text(((width-nw)//2, 310), name_text, fill=(255, 255, 255), font=font_name)
    
    mt = f"Member #{member_count}"
    try:
        mw = font_member.getbbox(mt)[2] - font_member.getbbox(mt)[0]
    except:
        mw = len(mt) * 12
    draw.text(((width-mw)//2, 362), mt, fill=(160, 175, 190), font=font_member)
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

async def create_goodbye_card(member, member_count):
    width, height = 800, 420
    img = Image.new("RGBA", (width, height), (30, 25, 25))
    draw = ImageDraw.Draw(img)
    red = (200, 60, 60)
    red_dark = (140, 35, 35)
    
    # 渐变背景
    for y in range(height):
        t = y / height
        draw.line([(0, y), (width, y)], fill=(int(30+t*15), int(25+t*5), int(25+t*5)))
    
    # 装饰
    draw.rectangle([0, 0, width, 5], fill=red)
    draw.rectangle([0, height-5, width, height], fill=red)
    
    av_cx, av_cy, av_r = width//2, 168, 98
    draw.ellipse((av_cx-av_r-9, av_cy-av_r-9, av_cx+av_r+9, av_cy+av_r+9), fill=red)
    draw.ellipse((av_cx-av_r-3, av_cy-av_r-3, av_cx+av_r+3, av_cy+av_r+3), fill=(30, 25, 25))
    
    av_img = await fetch_avatar(member)
    if av_img:
        circle = make_circle_avatar(av_img, av_r*2)
        img.paste(circle, (av_cx-av_r, av_cy-av_r), circle)
    
    try:
        font_label = ImageFont.truetype(FONT_BOLD, 16)
        font_name = ImageFont.truetype(FONT_BOLD, 42)
        font_member = ImageFont.truetype(FONT_REGULAR, 24)
    except:
        font_label = font_name = font_member = ImageFont.load_default()
    
    label = "✦ GOODBYE ✦"
    try:
        lbw = font_label.getbbox(label)[2] - font_label.getbbox(label)[0]
    except:
        lbw = len(label) * 10
    draw.text(((width-lbw)//2, 288), label, fill=red, font=font_label)
    
    name_text = f"Goodbye, {member.display_name}..."
    try:
        nw = font_name.getbbox(name_text)[2] - font_name.getbbox(name_text)[0]
    except:
        nw = len(name_text) * 20
    draw.text(((width-nw)//2, 310), name_text, fill=(255, 255, 255), font=font_name)
    
    mt = f"Members remaining: {member_count}"
    try:
        mw = font_member.getbbox(mt)[2] - font_member.getbbox(mt)[0]
    except:
        mw = len(mt) * 12
    draw.text(((width-mw)//2, 362), mt, fill=(180, 140, 140), font=font_member)
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ==================== 权限检查 ====================
def admin_only():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message("❌ 你需要管理员权限", ephemeral=True)
        return False
    return app_commands.check(predicate)

# ==================== 等级系统事件 ====================
_xp_cooldown: dict[str, datetime] = {}

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    
    guild_id = str(message.guild.id)
    user_id = str(message.author.id)
    key = f"{guild_id}:{user_id}"
    
    now = datetime.now()
    if key in _xp_cooldown and (now - _xp_cooldown[key]).total_seconds() < 60:
        await bot.process_commands(message)
        return
    _xp_cooldown[key] = now
    
    settings = db_get_guild_settings(guild_id)
    user_data = db_get_user(guild_id, user_id)
    xp_gain = int(random.randint(15, 25) * settings["xp_rate"])
    user_data["xp"] += xp_gain
    user_data, levels_gained = process_level_up(user_data)
    
    if levels_gained > 0:
        role_id = db_get_level_role(guild_id, user_data["level"])
        if role_id:
            role = message.guild.get_role(int(role_id))
            if role:
                try:
                    await message.author.add_roles(role)
                except discord.Forbidden:
                    pass
        embed = discord.Embed(
            title="🎉 等级提升！",
            description=f"{message.author.mention} 升到了 **{user_data['level']} 级**！",
            color=discord.Color.gold()
        )
        await message.channel.send(embed=embed, delete_after=10)
    
    db_update_user(guild_id, user_id, user_data)
    await bot.process_commands(message)

# ==================== 语音经验 ====================
_voice_tracker: dict[int, datetime] = {}

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    
    guild_id = str(member.guild.id)
    
    # 加入语音
    if before.channel is None and after.channel is not None:
        _voice_tracker[member.id] = datetime.now()
        ch_id = db_get_log_channel(guild_id, "voice_log_channel")
        if ch_id:
            ch = member.guild.get_channel(int(ch_id))
            if ch:
                embed = discord.Embed(
                    title="🔊 加入语音",
                    description=f"{member.mention} 加入了 {after.channel.mention}",
                    color=discord.Color.green()
                )
                await ch.send(embed=embed)
    
    # 离开语音
    elif before.channel is not None and after.channel is None:
        join_time = _voice_tracker.pop(member.id, None)
        if join_time:
            duration = (datetime.now() - join_time).total_seconds()
            if duration >= 60:
                settings = db_get_guild_settings(guild_id)
                xp_gain = int((duration / 60) * 5 * settings["voice_xp_rate"])
                user_data = db_get_user(guild_id, member.id)
                user_data["voice_xp"] += xp_gain
                user_data["xp"] += xp_gain
                user_data, levels_gained = process_level_up(user_data)
                if levels_gained > 0:
                    role_id = db_get_level_role(guild_id, user_data["level"])
                    if role_id:
                        role = member.guild.get_role(int(role_id))
                        if role:
                            try:
                                await member.add_roles(role)
                            except discord.Forbidden:
                                pass
                db_update_user(guild_id, member.id, user_data)
        
        ch_id = db_get_log_channel(guild_id, "voice_log_channel")
        if ch_id:
            ch = member.guild.get_channel(int(ch_id))
            if ch:
                embed = discord.Embed(
                    title="🔇 离开语音",
                    description=f"{member.mention} 离开了 {before.channel.mention}",
                    color=discord.Color.red()
                )
                await ch.send(embed=embed)

# ==================== 成员加入/离开 ====================
@bot.event
async def on_member_join(member):
    ch_id = db_get_welcome_channel(str(member.guild.id))
    if not ch_id:
        return
    ch = member.guild.get_channel(int(ch_id))
    if not ch:
        return
    
    member_count = member.guild.member_count
    try:
        buf = await create_welcome_card(member, member_count)
        file = discord.File(buf, filename="welcome.png")
        await ch.send(file=file)
    except Exception as e:
        print(f"[Welcome Card Error] {e}")

@bot.event
async def on_member_remove(member):
    ch_id = db_get_welcome_channel(str(member.guild.id))
    if not ch_id:
        return
    ch = member.guild.get_channel(int(ch_id))
    if not ch:
        return
    
    member_count = member.guild.member_count
    try:
        buf = await create_goodbye_card(member, member_count)
        file = discord.File(buf, filename="goodbye.png")
        await ch.send(file=file)
    except Exception as e:
        print(f"[Goodbye Card Error] {e}")

# ==================== 斜杠命令 ====================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot已登录: {bot.user}")

# ── 等级 ──────────────────────────────────────────
@bot.tree.command(name="rank", description="查看等级卡片")
async def slash_rank(interaction: discord.Interaction, member: discord.Member = None):
    await interaction.response.defer()
    member = member or interaction.user
    user_data = db_get_user(interaction.guild.id, member.id)
    rank_pos = db_get_rank(interaction.guild.id, member.id)
    needed = xp_needed(user_data["level"])
    
    try:
        buf = await create_rank_card(member, user_data["level"], user_data["xp"], needed, rank_pos)
        file = discord.File(buf, filename="rank.png")
        await interaction.followup.send(file=file)
    except Exception as e:
        print(f"[Rank Card Error] {e}")
        embed = discord.Embed(
            title=f"📊 {member.display_name} 的等级",
            description=f"**等级：** {user_data['level']}\n**经验：** {user_data['xp']}/{needed}\n**排名：** #{rank_pos}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="leaderboard", description="查看等级排行榜（TOP 10）")
async def slash_leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    top_data = db_get_leaderboard(interaction.guild.id, limit=10)
    
    if not top_data:
        await interaction.followup.send("📊 暂无数据，多发消息赚取经验吧！", ephemeral=True)
        return
    
    # 构建用户数据（使用并发获取）
    top_users = []
    for row in top_data:
        member, is_left = await fetch_member_with_fallback(interaction.guild, row["user_id"])
        if not member:
            continue
        top_users.append({
            "member": member,
            "level": row["level"],
            "xp": row["xp"],
            "total_xp": int(row["total_xp"]),
            "needed_xp": xp_needed(row["level"]),
            "is_left": is_left
        })
    
    if not top_users:
        await interaction.followup.send("📊 暂无有效数据", ephemeral=True)
        return
    
    try:
        buf = await create_leaderboard_card(interaction.guild, top_users)
        file = discord.File(buf, filename="leaderboard.png")
        
        # 获取调用者排名
        caller_data = db_get_user(interaction.guild.id, interaction.user.id)
        caller_total = get_total_xp(caller_data["level"], caller_data["xp"])
        caller_rank = db_get_rank(interaction.guild.id, interaction.user.id)
        
        content = None
        if caller_rank > 10:
            content = f"*你的排名：第 **{caller_rank}** 名（总经验：{caller_total:,}）*"
        
        await interaction.followup.send(content=content, file=file)
    except Exception as e:
        print(f"[Leaderboard Card Error] {e}")
        import traceback
        traceback.print_exc()
        
        # 文字回退
        desc = "🏆 **服务器排行榜 TOP 10**\n\n"
        for i, u in enumerate(top_users, 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"**{i}.**")
            status = "⚪" if u['is_left'] else "🟢"
            desc += f"{medal} {status} **{u['member'].display_name}** `Lv.{u['level']} ({u['total_xp']:,} XP)`\n"
        
        embed = discord.Embed(
            title=f"📊 {interaction.guild.name} 排行榜",
            description=desc,
            color=discord.Color.gold()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="add_level_role", description="设置等级奖励角色")
@admin_only()
async def add_level_role(interaction: discord.Interaction, level: int, role: discord.Role):
    with db_lock:
        with get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?)",
                (str(interaction.guild.id), level, str(role.id))
            )
            conn.commit()
    await interaction.response.send_message(f"✅ 等级 {level} 奖励角色已设置为 {role.mention}", ephemeral=True)

@bot.tree.command(name="set_xp_rate", description="设置经验倍率（默认1.0）")
@admin_only()
async def set_xp_rate(interaction: discord.Interaction, rate: float):
    with db_lock:
        with get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO guild_settings (guild_id, xp_rate) VALUES (?, ?)",
                (str(interaction.guild.id), max(0.1, min(rate, 10.0)))
            )
            conn.commit()
    await interaction.response.send_message(f"✅ 经验倍率已设置为 {rate}x", ephemeral=True)

# ── 反应角色 ──────────────────────────────────────
@bot.tree.command(name="add_reaction_role", description="添加反应角色")
@admin_only()
async def add_reaction_role(interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
    with db_lock:
        with get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)",
                (str(interaction.guild.id), message_id, emoji, str(role.id))
            )
            conn.commit()
    await interaction.response.send_message(f"✅ 反应角色已添加: {emoji} → {role.mention}", ephemeral=True)

@bot.tree.command(name="remove_reaction_role", description="移除反应角色")
@admin_only()
async def remove_reaction_role(interaction: discord.Interaction, message_id: str, emoji: str):
    with db_lock:
        with get_conn() as conn:
            conn.execute(
                "DELETE FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?",
                (str(interaction.guild.id), message_id, emoji)
            )
            conn.commit()
    await interaction.response.send_message("✅ 反应角色已移除", ephemeral=True)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    with get_conn() as conn:
        row = conn.execute(
            "SELECT role_id FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?",
            (str(payload.guild_id), str(payload.message_id), payload.emoji.name)
        ).fetchone()
        if row:
            guild = bot.get_guild(payload.guild_id)
            role = guild.get_role(int(row["role_id"]))
            member = guild.get_member(payload.user_id)
            if role and member:
                try:
                    await member.add_roles(role)
                except discord.Forbidden:
                    pass

@bot.event
async def on_raw_reaction_remove(payload):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT role_id FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?",
            (str(payload.guild_id), str(payload.message_id), payload.emoji.name)
        ).fetchone()
        if row:
            guild = bot.get_guild(payload.guild_id)
            role = guild.get_role(int(row["role_id"]))
            member = guild.get_member(payload.user_id)
            if role and member:
                try:
                    await member.remove_roles(role)
                except discord.Forbidden:
                    pass

# ── 计数器 ────────────────────────────────────────
@bot.tree.command(name="add_counter", description="添加计数器")
@admin_only()
async def add_counter(interaction: discord.Interaction, counter_type: str, channel: discord.TextChannel, message_template: str):
    with db_lock:
        with get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO counters (guild_id, counter_type, channel_id, message_template) VALUES (?,?,?,?)",
                (str(interaction.guild.id), counter_type, str(channel.id), message_template)
            )
            conn.commit()
    await interaction.response.send_message(f"✅ 计数器 `{counter_type}` 已添加", ephemeral=True)

@bot.tree.command(name="update_counter", description="更新计数器数值")
@admin_only()
async def update_counter(interaction: discord.Interaction, counter_type: str, value: int):
    with db_lock:
        with get_conn() as conn:
            conn.execute(
                "UPDATE counters SET current_value=? WHERE guild_id=? AND counter_type=?",
                (value, str(interaction.guild.id), counter_type)
            )
            conn.commit()
            row = conn.execute(
                "SELECT channel_id, message_template FROM counters WHERE guild_id=? AND counter_type=?",
                (str(interaction.guild.id), counter_type)
            ).fetchone()
            if row:
                ch = interaction.guild.get_channel(int(row["channel_id"]))
                msg = row["message_template"].replace("{value}", str(value))
                if ch:
                    async for m in ch.history(limit=10):
                        if m.author == bot.user and counter_type in m.content:
                            await m.edit(content=msg)
                            break
                    else:
                        await ch.send(msg)
    await interaction.response.send_message("✅ 计数器已更新", ephemeral=True)

@bot.tree.command(name="remove_counter", description="移除计数器")
@admin_only()
async def remove_counter(interaction: discord.Interaction, counter_type: str):
    with db_lock:
        with get_conn() as conn:
            conn.execute(
                "DELETE FROM counters WHERE guild_id=? AND counter_type=?",
                (str(interaction.guild.id), counter_type)
            )
            conn.commit()
    await interaction.response.send_message(f"✅ 计数器 `{counter_type}` 已移除", ephemeral=True)

# ── 日志 ──────────────────────────────────────────
def _set_log(guild_id, col, channel_id):
    with db_lock:
        with get_conn() as conn:
            conn.execute(
                f"INSERT INTO log_settings (guild_id, {col}) VALUES (?,?) "
                f"ON CONFLICT(guild_id) DO UPDATE SET {col}=excluded.{col}",
                (str(guild_id), str(channel_id))
            )
            conn.commit()

@bot.tree.command(name="set_log_channel", description="设置消息日志频道")
@admin_only()
async def set_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    _set_log(interaction.guild.id, "message_log_channel", channel.id)
    await interaction.response.send_message(f"✅ 消息日志 → {channel.mention}", ephemeral=True)

@bot.tree.command(name="set_voice_log", description="设置语音日志频道")
@admin_only()
async def set_voice_log(interaction: discord.Interaction, channel: discord.TextChannel):
    _set_log(interaction.guild.id, "voice_log_channel", channel.id)
    await interaction.response.send_message(f"✅ 语音日志 → {channel.mention}", ephemeral=True)

@bot.tree.command(name="set_mod_log", description="设置管理日志频道")
@admin_only()
async def set_mod_log(interaction: discord.Interaction, channel: discord.TextChannel):
    _set_log(interaction.guild.id, "mod_log_channel", channel.id)
    await interaction.response.send_message(f"✅ 管理日志 → {channel.mention}", ephemeral=True)

@bot.tree.command(name="set_welcome_channel", description="设置欢迎/告别频道")
@admin_only()
async def set_welcome_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    with db_lock:
        with get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO welcome_settings (guild_id, channel_id, message, color) VALUES (?,?,?,?)",
                (str(interaction.guild.id), str(channel.id), "Welcome!", "#5865F2")
            )
            conn.commit()
    await interaction.response.send_message(f"✅ 欢迎/告别频道 → {channel.mention}", ephemeral=True)

@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    ch_id = db_get_log_channel(str(message.guild.id), "message_log_channel")
    if ch_id:
        ch = message.guild.get_channel(int(ch_id))
        if ch:
            embed = discord.Embed(
                title="🗑️ 消息被删除",
                description=f"**频道:** {message.channel.mention}\n**用户:** {message.author.mention}\n**内容:** {message.content[:500]}",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            await ch.send(embed=embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
    ch_id = db_get_log_channel(str(before.guild.id), "message_log_channel")
    if ch_id:
        ch = before.guild.get_channel(int(ch_id))
        if ch:
            embed = discord.Embed(
                title="✏️ 消息被编辑",
                description=f"**频道:** {before.channel.mention}\n**用户:** {before.author.mention}\n**之前:** {before.content[:300]}\n**之后:** {after.content[:300]}",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            await ch.send(embed=embed)

# ── 管理命令 ──────────────────────────────────────
@bot.tree.command(name="kick", description="踢出用户")
@admin_only()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "无"):
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"✅ 已踢出 {member.mention}", ephemeral=True)
        ch_id = db_get_log_channel(str(interaction.guild.id), "mod_log_channel")
        if ch_id:
            ch = interaction.guild.get_channel(int(ch_id))
            if ch:
                embed = discord.Embed(
                    title="👢 用户被踢出",
                    description=f"**用户:** {member.mention}\n**管理员:** {interaction.user.mention}\n**原因:** {reason}",
                    color=discord.Color.orange(),
                    timestamp=datetime.now()
                )
                await ch.send(embed=embed)
    except discord.Forbidden:
        await interaction.response.send_message("❌ 权限不足", ephemeral=True)

@bot.tree.command(name="ban", description="封禁用户")
@admin_only()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "无"):
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"✅ 已封禁 {member.mention}", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ 权限不足", ephemeral=True)

@bot.tree.command(name="clear", description="清除消息")
@admin_only()
async def clear(interaction: discord.Interaction, amount: int):
    amount = max(1, min(amount, 100))
    await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"✅ 已清除 {amount} 条消息", ephemeral=True)

@bot.tree.command(name="userinfo", description="查看用户信息")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    av_url = member.avatar.url if member.avatar else member.default_avatar.url
    embed = discord.Embed(title=f"👤 {member.display_name}", color=member.color)
    embed.set_thumbnail(url=av_url)
    embed.add_field(name="ID", value=str(member.id), inline=True)
    embed.add_field(name="加入时间", value=member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "未知", inline=True)
    embed.add_field(name="注册时间", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="最高角色", value=member.top_role.mention, inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="help", description="查看帮助")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 Bot 帮助", color=discord.Color.green())
    embed.add_field(name="📊 等级系统", value="`/rank` `/leaderboard`\n`/add_level_role` `/set_xp_rate`", inline=False)
    embed.add_field(name="🎭 反应角色", value="`/add_reaction_role` `/remove_reaction_role`", inline=False)
    embed.add_field(name="🔢 计数器", value="`/add_counter` `/update_counter` `/remove_counter`", inline=False)
    embed.add_field(name="📋 日志系统", value="`/set_log_channel` `/set_voice_log` `/set_mod_log`", inline=False)
    embed.add_field(name="👋 欢迎/告别", value="`/set_welcome_channel`", inline=False)
    embed.add_field(name="🔧 管理", value="`/kick` `/ban` `/clear`", inline=False)
    embed.add_field(name="ℹ️ 信息", value="`/userinfo`", inline=False)
    await interaction.response.send_message(embed=embed)

# ==================== 运行 ====================
if __name__ == "__main__":
    bot.run(TOKEN)
