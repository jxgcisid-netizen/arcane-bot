import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import aiohttp
import asyncio
from datetime import datetime, timedelta
import sqlite3
from collections import defaultdict
import re
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import io
import math

# ========== 配置 ==========
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="", intents=intents, help_command=None)

# ========== 检查是否是群主 ==========
def is_owner():
    async def predicate(interaction: discord.Interaction):
        return interaction.user == interaction.guild.owner
    return app_commands.check(predicate)

# ========== 权限检查 ==========
def has_permission(guild_id, user_id, command_name):
    guild = bot.get_guild(int(guild_id))
    if guild and guild.owner_id == int(user_id):
        return True
    
    c.execute("SELECT 1 FROM command_permissions WHERE guild_id=? AND command_name=? AND user_id=?", 
              (str(guild_id), command_name, str(user_id)))
    if c.fetchone():
        return True
    
    if guild:
        member = guild.get_member(int(user_id))
        if member:
            for role in member.roles:
                c.execute("SELECT 1 FROM command_permissions WHERE guild_id=? AND command_name=? AND role_id=?", 
                          (str(guild_id), command_name, str(role.id)))
                if c.fetchone():
                    return True
    
    return False

def admin_only():
    async def predicate(interaction: discord.Interaction):
        if interaction.user == interaction.guild.owner:
            return True
        return has_permission(interaction.guild.id, interaction.user.id, "admin")
    return app_commands.check(predicate)

# ========== 数据库初始化 ==========
conn = sqlite3.connect("arcane_data.db")
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id TEXT,
    guild_id TEXT,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    voice_xp INTEGER DEFAULT 0,
    reaction_xp INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, guild_id)
)''')

c.execute('''CREATE TABLE IF NOT EXISTS level_rewards (
    guild_id TEXT,
    level INTEGER,
    role_id TEXT,
    PRIMARY KEY (guild_id, level)
)''')

c.execute('''CREATE TABLE IF NOT EXISTS custom_commands (
    guild_id TEXT,
    command_name TEXT,
    response TEXT,
    PRIMARY KEY (guild_id, command_name)
)''')

c.execute('''CREATE TABLE IF NOT EXISTS reaction_roles (
    guild_id TEXT,
    message_id TEXT,
    emoji TEXT,
    role_id TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS youtube_notifications (
    guild_id TEXT,
    channel_id TEXT,
    youtube_channel TEXT,
    last_video_id TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS counters (
    guild_id TEXT,
    counter_type TEXT,
    channel_id TEXT,
    message_template TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS welcome_settings (
    guild_id TEXT PRIMARY KEY,
    channel_id TEXT,
    message TEXT,
    background_url TEXT,
    color TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id TEXT PRIMARY KEY,
    xp_rate REAL DEFAULT 1.0,
    voice_xp_rate REAL DEFAULT 1.0,
    card_background TEXT,
    card_color TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS log_settings (
    guild_id TEXT PRIMARY KEY,
    message_log_channel TEXT,
    voice_log_channel TEXT,
    mod_log_channel TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS command_permissions (
    guild_id TEXT,
    command_name TEXT,
    role_id TEXT,
    user_id TEXT,
    PRIMARY KEY (guild_id, command_name, role_id, user_id)
)''')

conn.commit()

# ========== 辅助函数 ==========
def get_user_data(guild_id, user_id):
    c.execute("SELECT * FROM users WHERE guild_id=? AND user_id=?", (str(guild_id), str(user_id)))
    result = c.fetchone()
    if not result:
        c.execute("INSERT INTO users (guild_id, user_id) VALUES (?, ?)", (str(guild_id), str(user_id)))
        conn.commit()
        return {"xp": 0, "level": 1, "voice_xp": 0, "reaction_xp": 0}
    return {"xp": result[2], "level": result[3], "voice_xp": result[4], "reaction_xp": result[5]}

def update_user_data(guild_id, user_id, data):
    c.execute("UPDATE users SET xp=?, level=?, voice_xp=?, reaction_xp=? WHERE guild_id=? AND user_id=?",
              (data["xp"], data["level"], data["voice_xp"], data["reaction_xp"], str(guild_id), str(user_id)))
    conn.commit()

def get_guild_settings(guild_id):
    c.execute("SELECT * FROM guild_settings WHERE guild_id=?", (str(guild_id),))
    result = c.fetchone()
    if not result:
        return {"xp_rate": 1.0, "voice_xp_rate": 1.0, "card_background": None, "card_color": "#5865F2"}
    return {"xp_rate": result[1], "voice_xp_rate": result[2], "card_background": result[3], "card_color": result[4]}

def get_rank(guild_id, user_id):
    c.execute("SELECT user_id FROM users WHERE guild_id=? ORDER BY level DESC, xp DESC", (str(guild_id),))
    users = c.fetchall()
    for i, (uid,) in enumerate(users, 1):
        if uid == str(user_id):
            return i
    return 0

# ========== 超级好看的等级卡片生成 ==========
async def create_beautiful_rank_card(member, level, xp, needed_xp, rank, guild_name):
    # 图片尺寸
    width, height = 900, 350
    
    # 1. 创建渐变背景
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)
    
    # 深色渐变背景（从深蓝到深紫）
    for y in range(height):
        # 颜色渐变计算
        r = 20 + int(15 * y / height)
        g = 20 + int(10 * y / height)
        b = 40 + int(30 * y / height)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    # 2. 添加光晕效果（左上角亮光）
    for i in range(200):
        alpha = 30 - int(i / 4)
        if alpha > 0:
            draw.ellipse([(50 - i//2, 50 - i//2, 50 + i//2, 50 + i//2)], 
                         fill=(100, 80, 200, alpha))
    
    # 3. 下载并处理头像
    async with aiohttp.ClientSession() as session:
        async with session.get(member.display_avatar.url) as resp:
            avatar_data = await resp.read()
    avatar = Image.open(io.BytesIO(avatar_data)).resize((120, 120))
    
    # 4. 制作圆形头像 + 发光边框
    mask = Image.new('L', (120, 120), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, 120, 120), fill=255)
    
    # 发光效果
    glow = Image.new('RGBA', (150, 150), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for i in range(20, 0, -2):
        alpha = 30 - i
        glow_draw.ellipse([(15 - i//2, 15 - i//2, 135 + i//2, 135 + i//2)], 
                          fill=(100, 80, 200, alpha))
    
    img.paste(avatar, (45, 115), mask)
    
    # 5. 加载字体
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
        level_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except:
        title_font = ImageFont.load_default()
        level_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # 6. 画用户名（带阴影）
    shadow_offset = 2
    draw.text((190 + shadow_offset, 125 + shadow_offset), member.name, 
              fill=(50, 50, 70), font=title_font)
    draw.text((190, 125), member.name, fill='white', font=title_font)
    
    # 7. 画等级徽章
    level_text = f"LEVEL {level}"
    # 徽章背景
    badge_width = 140
    badge_height = 40
    badge_x = 190
    badge_y = 180
    
    # 渐变徽章
    for i in range(badge_height):
        r = 100 + int(100 * i / badge_height)
        g = 50 + int(50 * i / badge_height)
        b = 150 + int(100 * i / badge_height)
        draw.line([(badge_x, badge_y + i), (badge_x + badge_width, badge_y + i)], 
                  fill=(r, g, b))
    
    # 徽章边框
    draw.rectangle([badge_x, badge_y, badge_x + badge_width, badge_y + badge_height], 
                   outline=(200, 150, 100), width=2)
    
    # 徽章文字
    draw.text((badge_x + badge_width//2, badge_y + badge_height//2 - 8), 
              level_text, fill='white', font=level_font, anchor='mm')
    
    # 8. 画排名
    rank_text = f"🏆 Rank #{rank}"
    draw.text((190, 235), rank_text, fill=(200, 180, 100), font=text_font)
    
    # 9. 画服务器名称
    draw.text((width - 20, height - 25), guild_name, 
              fill=(100, 100, 130), font=small_font, anchor='rb')
    
    # 10. 画经验条背景
    bar_x = 190
    bar_y = 275
    bar_width = 550
    bar_height = 25
    
    # 背景
    draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], 
                   fill=(30, 30, 50), outline=(80, 80, 120), width=2)
    
    # 渐变进度条
    progress = int((xp / needed_xp) * bar_width) if needed_xp > 0 else 0
    for i in range(bar_height):
        for j in range(progress):
            r = 80 + int(100 * j / bar_width)
            g = 100 + int(80 * j / bar_width)
            b = 255 - int(80 * j / bar_width)
            draw.point((bar_x + j, bar_y + i), fill=(r, g, b))
    
    # 11. 经验数字
    exp_text = f"{xp} / {needed_xp} XP"
    draw.text((bar_x + bar_width + 15, bar_y + bar_height//2 - 5), 
              exp_text, fill=(180, 180, 220), font=small_font)
    
    # 12. 添加装饰线条
    draw.line([(45, 280), (170, 280)], fill=(150, 100, 200), width=3)
    draw.line([(45, 285), (170, 285)], fill=(100, 80, 150), width=1)
    
    # 13. 添加星星装饰
    for i in range(3):
        star_x = width - 50 - i * 30
        star_y = 40
        draw.text((star_x, star_y), "⭐", fill=(255, 215, 0, 100), font=small_font)
    
    # 保存
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes

# ========== 等级系统 ==========
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    guild_id = message.guild.id
    user_id = message.author.id
    
    settings = get_guild_settings(guild_id)
    user_data = get_user_data(guild_id, user_id)
    
    xp_gain = int((1 + (hash(str(user_id) + str(datetime.now().minute)) % 3)) * settings["xp_rate"])
    user_data["xp"] += xp_gain
    
    xp_needed = user_data["level"] * 50
    level_up = False
    while user_data["xp"] >= xp_needed:
        user_data["level"] += 1
        user_data["xp"] -= xp_needed
        xp_needed = user_data["level"] * 50
        level_up = True
        
        c.execute("SELECT role_id FROM level_rewards WHERE guild_id=? AND level=?", (str(guild_id), user_data["level"]))
        reward = c.fetchone()
        if reward:
            role = message.guild.get_role(int(reward[0]))
            if role:
                await message.author.add_roles(role)
    
    if level_up:
        embed = discord.Embed(
            title="🎉 等级提升！",
            description=f"{message.author.mention} 升到了 **{user_data['level']} 级**！",
            color=discord.Color.gold()
        )
        await message.channel.send(embed=embed)
    
    update_user_data(guild_id, user_id, user_data)
    await bot.process_commands(message)

# ========== 语音经验系统 ==========
voice_tracker = defaultdict(dict)

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    
    guild_id = member.guild.id
    
    if before.channel is None and after.channel is not None:
        voice_tracker[member.id]["join_time"] = datetime.now()
        
        c.execute("SELECT voice_log_channel FROM log_settings WHERE guild_id=?", (str(guild_id),))
        result = c.fetchone()
        if result and result[0]:
            channel = member.guild.get_channel(int(result[0]))
            if channel:
                embed = discord.Embed(
                    title="🎤 加入语音",
                    description=f"{member.mention} 加入了 {after.channel.mention}",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                await channel.send(embed=embed)
    
    elif before.channel is not None and after.channel is None:
        if member.id in voice_tracker and "join_time" in voice_tracker[member.id]:
            duration = (datetime.now() - voice_tracker[member.id]["join_time"]).total_seconds()
            if duration >= 60:
                settings = get_guild_settings(guild_id)
                xp_gain = int((duration / 60) * 5 * settings["voice_xp_rate"])
                user_data = get_user_data(guild_id, member.id)
                user_data["voice_xp"] += xp_gain
                user_data["xp"] += xp_gain
                
                xp_needed = user_data["level"] * 50
                while user_data["xp"] >= xp_needed:
                    user_data["level"] += 1
                    user_data["xp"] -= xp_needed
                    xp_needed = user_data["level"] * 50
                
                update_user_data(guild_id, member.id, user_data)
            del voice_tracker[member.id]
        
        c.execute("SELECT voice_log_channel FROM log_settings WHERE guild_id=?", (str(guild_id),))
        result = c.fetchone()
        if result and result[0]:
            channel = member.guild.get_channel(int(result[0]))
            if channel:
                embed = discord.Embed(
                    title="🎤 离开语音",
                    description=f"{member.mention} 离开了 {before.channel.mention}",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                await channel.send(embed=embed)

# ========== 斜杠命令 ==========

@bot.tree.command(name="level", description="查看自己的等级卡片")
async def slash_level(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    user_data = get_user_data(interaction.guild.id, member.id)
    rank_pos = get_rank(interaction.guild.id, member.id)
    needed_xp = user_data["level"] * 50
    
    try:
        img_bytes = await create_beautiful_rank_card(
            member, user_data["level"], user_data["xp"], 
            needed_xp, rank_pos, interaction.guild.name
        )
        file = discord.File(img_bytes, filename="level.png")
        await interaction.response.send_message(file=file)
    except Exception as e:
        embed = discord.Embed(
            title=f"{member.name} 的等级",
            description=f"等级: **{user_data['level']}**\n经验: {user_data['xp']}/{needed_xp} XP\n排名: #{rank_pos}\n语音经验: {user_data['voice_xp']}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rank", description="查看自己的等级卡片")
async def slash_rank(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    user_data = get_user_data(interaction.guild.id, member.id)
    rank_pos = get_rank(interaction.guild.id, member.id)
    needed_xp = user_data["level"] * 50
    
    try:
        img_bytes = await create_beautiful_rank_card(
            member, user_data["level"], user_data["xp"], 
            needed_xp, rank_pos, interaction.guild.name
        )
        file = discord.File(img_bytes, filename="level.png")
        await interaction.response.send_message(file=file)
    except Exception as e:
        embed = discord.Embed(
            title=f"{member.name} 的等级",
            description=f"等级: **{user_data['level']}**\n经验: {user_data['xp']}/{needed_xp} XP\n排名: #{rank_pos}\n语音经验: {user_data['voice_xp']}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="查看等级排行榜")
async def slash_leaderboard(interaction: discord.Interaction):
    c.execute("SELECT user_id, level, xp FROM users WHERE guild_id=? ORDER BY level DESC, xp DESC LIMIT 10", (str(interaction.guild.id),))
    top_users = c.fetchall()
    
    if not top_users:
        await interaction.response.send_message("📭 暂无数据")
        return
    
    # 获取所有用户名称
    users_data = []
    for user_id, level, xp in top_users:
        try:
            user = await bot.fetch_user(int(user_id))
            name = user.name
        except:
            name = f"用户{user_id[:8]}"
        users_data.append((name, level, xp))
    
    # 创建排行榜图片
    height = 150 + len(users_data) * 55
    img = Image.new('RGB', (800, height), color='#1a1a2e')
    draw = ImageDraw.Draw(img)
    
    # 渐变背景
    for y in range(height):
        r = 20 + int(15 * y / height)
        g = 20 + int(10 * y / height)
        b = 40 + int(30 * y / height)
        draw.line([(0, y), (800, y)], fill=(r, g, b))
    
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        header_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except:
        title_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        font = ImageFont.load_default()
    
    draw.text((400, 30), f"{interaction.guild.name} 等级排行榜", fill='white', font=title_font, anchor='mt')
    draw.text((60, 80), "排名", fill='#a78bfa', font=header_font)
    draw.text((160, 80), "玩家", fill='#a78bfa', font=header_font)
    draw.text((500, 80), "等级", fill='#a78bfa', font=header_font)
    draw.text((620, 80), "经验", fill='#a78bfa', font=header_font)
    draw.line([(40, 110), (760, 110)], fill='#5865F2', width=2)
    
    y = 130
    for i, (name, level, xp) in enumerate(users_data, 1):
        if i == 1:
            rank_color = "#FFD700"
            medal = "🥇"
        elif i == 2:
            rank_color = "#C0C0C0"
            medal = "🥈"
        elif i == 3:
            rank_color = "#CD7F32"
            medal = "🥉"
        else:
            rank_color = "white"
            medal = f"{i}"
        
        draw.text((60, y), medal, fill=rank_color, font=font)
        draw.text((160, y), name[:20], fill="white", font=font)
        draw.text((500, y), str(level), fill="white", font=font)
        draw.text((620, y), str(xp), fill="white", font=font)
        y += 50
    
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    file = discord.File(img_bytes, filename="leaderboard.png")
    await interaction.response.send_message(file=file)

# ========== 其他命令（保持不变）==========
# userinfo, serverinfo, avatar, invite, help, add_level_role, 
# remove_level_role, set_xp_rate, add_cmd, del_cmd, list_cmds,
# add_reaction_role, add_youtube, add_counter, set_welcome,
# set_log_channel, set_voice_log, kick, ban, clear, lock, unlock,
# add_admin_role, remove_admin_role, add_admin_user, remove_admin_user, list_admins
# ... 这些命令和之前一样，保持原样

# 由于篇幅限制，我把上面这些命令省略了，它们和之前版本完全一样
# 你需要从你之前的 bot.py 中把这些命令复制过来

# ========== 后台任务 ==========
@tasks.loop(minutes=5)
async def update_counters():
    for guild in bot.guilds:
        c.execute("SELECT counter_type, channel_id, message_template FROM counters WHERE guild_id=?", (str(guild.id),))
        counters = c.fetchall()
        for counter_type, channel_id, template in counters:
            channel = guild.get_channel(int(channel_id))
            if channel:
                if counter_type == "member":
                    count = guild.member_count
                elif counter_type == "online":
                    count = len([m for m in guild.members if m.status != discord.Status.offline])
                elif counter_type == "bot":
                    count = len([m for m in guild.members if m.bot])
                elif counter_type == "role":
                    count = len(guild.roles)
                elif counter_type == "channel":
                    count = len(guild.channels)
                else:
                    continue
                message = template.replace("{count}", str(count))
                await channel.edit(name=message)

@tasks.loop(minutes=10)
async def check_youtube():
    if not os.getenv("YOUTUBE_API_KEY"):
        return
    for guild in bot.guilds:
        c.execute("SELECT channel_id, youtube_channel, last_video_id FROM youtube_notifications WHERE guild_id=?", (str(guild.id),))
        subs = c.fetchall()
        for notification_channel_id, yt_channel, last_video_id in subs:
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"https://www.googleapis.com/youtube/v3/search?key={os.getenv('YOUTUBE_API_KEY')}&channelId={yt_channel}&part=snippet&order=date&maxResults=1"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        if data.get("items"):
                            video = data["items"][0]
                            video_id = video["id"]["videoId"]
                            if video_id != last_video_id:
                                channel = guild.get_channel(int(notification_channel_id))
                                if channel:
                                    embed = discord.Embed(
                                        title=f"📺 新视频: {video['snippet']['title']}",
                                        url=f"https://youtube.com/watch?v={video_id}",
                                        color=discord.Color.red()
                                    )
                                    embed.set_thumbnail(url=video["snippet"]["thumbnails"]["default"]["url"])
                                    await channel.send(embed=embed)
                                    c.execute("UPDATE youtube_notifications SET last_video_id=? WHERE guild_id=? AND youtube_channel=?", 
                                              (video_id, str(guild.id), yt_channel))
                                    conn.commit()
            except:
                pass

# ========== 事件 ==========
@bot.event
async def on_member_join(member):
    c.execute("SELECT channel_id, message, background_url, color FROM welcome_settings WHERE guild_id=?", (str(member.guild.id),))
    result = c.fetchone()
    if result:
        channel = member.guild.get_channel(int(result[0]))
        if channel:
            embed = discord.Embed(
                title="👋 欢迎！",
                description=result[1].replace("{user}", member.mention).replace("{server}", member.guild.name),
                color=discord.Color(int(result[3].lstrip('#'), 16)) if result[3] else discord.Color.green()
            )
            embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
            if result[2]:
                embed.set_image(url=result[2])
            await channel.send(embed=embed)
    else:
        channel = member.guild.system_channel
        if channel:
            embed = discord.Embed(
                title="👋 欢迎！",
                description=f"欢迎 {member.mention} 加入 {member.guild.name}！",
                color=discord.Color.green()
            )
            await channel.send(embed=embed)

@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    c.execute("SELECT message_log_channel FROM log_settings WHERE guild_id=?", (str(message.guild.id),))
    result = c.fetchone()
    if result and result[0]:
        channel = message.guild.get_channel(int(result[0]))
        if channel:
            embed = discord.Embed(
                title="📝 消息删除",
                description=f"作者: {message.author.mention}\n频道: {message.channel.mention}\n内容: {message.content[:500]}",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            await channel.send(embed=embed)

# ========== 启动 ==========
@bot.event
async def on_ready():
    print(f"✅ {bot.user} 已上线！")
    print(f"已连接 {len(bot.guilds)} 个服务器")
    
    # 同步斜杠命令
    for guild in bot.guilds:
        try:
            await bot.tree.sync(guild=guild)
            print(f"✅ 已同步命令到服务器: {guild.name}")
        except Exception as e:
            print(f"❌ 同步失败: {e}")
    
    update_counters.start()
    if os.getenv("YOUTUBE_API_KEY"):
        check_youtube.start()

# ========== 运行 ==========
bot.run(TOKEN)
