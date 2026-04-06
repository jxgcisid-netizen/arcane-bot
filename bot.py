import discord
from discord.ext import commands
from discord import app_commands
import os
import aiohttp
import asyncio
from datetime import datetime
import sqlite3
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont
import io

# 配置
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# 数据库初始化
conn = sqlite3.connect("bot_data.db")
c = conn.cursor()

# 创建表
c.execute('''CREATE TABLE IF NOT EXISTS users (
    guild_id TEXT, user_id TEXT, xp INTEGER DEFAULT 0, 
    level INTEGER DEFAULT 1, voice_xp INTEGER DEFAULT 0, 
    PRIMARY KEY (guild_id, user_id)
)''')

c.execute('CREATE TABLE IF NOT EXISTS level_roles (guild_id TEXT, level INTEGER, role_id TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS reaction_roles (guild_id TEXT, message_id TEXT, emoji TEXT, role_id TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS counters (guild_id TEXT, counter_type TEXT, channel_id TEXT, message_template TEXT, current_value INTEGER DEFAULT 0)')
c.execute('CREATE TABLE IF NOT EXISTS welcome_settings (guild_id TEXT PRIMARY KEY, channel_id TEXT, message TEXT, color TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS guild_settings (guild_id TEXT PRIMARY KEY, xp_rate REAL DEFAULT 1.0, voice_xp_rate REAL DEFAULT 1.0)')
c.execute('CREATE TABLE IF NOT EXISTS log_settings (guild_id TEXT PRIMARY KEY, message_log_channel TEXT, voice_log_channel TEXT, mod_log_channel TEXT)')

conn.commit()

# ==================== 辅助函数 ====================

def get_user_data(guild_id, user_id):
    c.execute("SELECT * FROM users WHERE guild_id=? AND user_id=?", (str(guild_id), str(user_id)))
    result = c.fetchone()
    if not result:
        c.execute("INSERT INTO users (guild_id, user_id) VALUES (?, ?)", (str(guild_id), str(user_id)))
        conn.commit()
        return {"xp": 0, "level": 1, "voice_xp": 0}
    return {"xp": result[2], "level": result[3], "voice_xp": result[4]}

def update_user_data(guild_id, user_id, data):
    c.execute("UPDATE users SET xp=?, level=?, voice_xp=? WHERE guild_id=? AND user_id=?", 
              (data["xp"], data["level"], data["voice_xp"], str(guild_id), str(user_id)))
    conn.commit()

def get_guild_settings(guild_id):
    c.execute("SELECT * FROM guild_settings WHERE guild_id=?", (str(guild_id),))
    result = c.fetchone()
    if not result:
        return {"xp_rate": 1.0, "voice_xp_rate": 1.0}
    return {"xp_rate": result[1], "voice_xp_rate": result[2]}

def get_rank(guild_id, user_id):
    c.execute("SELECT user_id FROM users WHERE guild_id=? ORDER BY level DESC, xp DESC", (str(guild_id),))
    users = c.fetchall()
    for i, (uid,) in enumerate(users, 1):
        if uid == str(user_id):
            return i
    return 0

# ==================== 权限检查 ====================

def admin_only():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message("❌ 你需要管理员权限", ephemeral=True)
        return False
    return app_commands.check(predicate)

# ==================== 等级卡片 ====================

async def create_rank_card(member, level, xp, needed_xp, rank, guild_name):
    width, height = 900, 350
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 1. 渐变背景
    for y in range(height):
        r = 20 + int(15 * y / height)
        g = 20 + int(10 * y / height)
        b = 40 + int(30 * y / height)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    # 2. 下载头像
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(member.display_avatar.url) as resp:
                if resp.status == 200:
                    avatar_data = await resp.read()
                    avatar = Image.open(io.BytesIO(avatar_data)).convert('RGBA')
                    avatar = avatar.resize((120, 120))
                    
                    # 制作圆形头像
                    mask = Image.new('L', (120, 120), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse((0, 0, 120, 120), fill=255)
                    
                    avatar_circular = Image.new('RGBA', (120, 120))
                    avatar_circular.paste(avatar, (0, 0), avatar)
                    avatar_circular.putalpha(mask)
                    
                    # 金色边框
                    border_img = Image.new('RGBA', (130, 130), (0, 0, 0, 0))
                    border_draw = ImageDraw.Draw(border_img)
                    border_draw.ellipse((5, 5, 125, 125), outline=(255, 215, 0), width=4)
                    border_img.paste(avatar_circular, (5, 5), avatar_circular)
                    
                    # 粘贴到头像位置 (45, 45)
                    img.paste(border_img, (45, 45), border_img)
                else:
                    # 头像下载失败，画一个默认圆形
                    draw.ellipse((45, 45, 165, 165), fill=(100, 100, 150), outline=(255, 215, 0), width=4)
    except Exception as e:
        print(f"头像处理失败: {e}")
        # 画默认头像
        draw.ellipse((45, 45, 165, 165), fill=(100, 100, 150), outline=(255, 215, 0), width=4)
    
    # 3. 字体设置
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        level_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except:
        try:
            title_font = ImageFont.truetype("arial.ttf", 36)
            level_font = ImageFont.truetype("arial.ttf", 28)
            text_font = ImageFont.truetype("arial.ttf", 22)
            small_font = ImageFont.truetype("arial.ttf", 18)
        except:
            title_font = ImageFont.load_default()
            level_font = ImageFont.load_default()
            text_font = ImageFont.load_default()
            small_font = ImageFont.load_default()
    
    # 4. 用户名（带 @）
    name = member.display_name[:15] + "..." if len(member.display_name) > 15 else member.display_name
    draw.text((190, 70), f"@{name}", fill=(255, 255, 255), font=title_font)
    
    # 5. 等级徽章（渐变彩色）
    badge_x, badge_y = 190, 120
    badge_width, badge_height = 120, 45
    for i in range(badge_height):
        r = 255 - int(155 * i / badge_height)
        g = 100 + int(155 * i / badge_height)
        b = 50 + int(50 * i / badge_height)
        draw.line([(badge_x, badge_y + i), (badge_x + badge_width, badge_y + i)], fill=(r, g, b))
    draw.rectangle([badge_x, badge_y, badge_x + badge_width, badge_y + badge_height], outline=(255, 215, 0), width=2)
    draw.text((badge_x + badge_width//2, badge_y + badge_height//2 - 3), f"Lv.{level}", fill='white', font=level_font, anchor='mm')
    
    # 6. 排名
    draw.text((190, 180), f"🏆 排名 #{rank}", fill=(255, 215, 0), font=text_font)
    
    # 7. 服务器名称
    draw.text((width - 20, height - 25), guild_name[:20], fill=(150, 150, 180), font=small_font, anchor='rb')
    
    # 8. 经验条背景
    bar_x, bar_y = 190, 235
    bar_width, bar_height = 550, 30
    draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], fill=(40, 40, 60), outline=(100, 100, 150), width=2)
    
    # 9. 渐变进度条
    progress = int((xp / needed_xp) * bar_width) if needed_xp > 0 else 0
    for i in range(bar_height):
        for j in range(min(progress, bar_width)):
            r = 80 + int(100 * j / bar_width)
            g = 100 + int(80 * j / bar_width)
            b = 255 - int(80 * j / bar_width)
            draw.point((bar_x + j, bar_y + i), fill=(r, g, b))
    
    # 10. 经验数字
    exp_text = f"{xp} / {needed_xp} XP"
    draw.text((bar_x + bar_width + 15, bar_y + bar_height//2 - 5), exp_text, fill=(220, 220, 255), font=small_font)
    
    # 11. 百分比显示
    percent = int((xp / needed_xp) * 100) if needed_xp > 0 else 0
    draw.text((bar_x + bar_width//2, bar_y + bar_height//2 - 5), f"{percent}%", fill=(255, 255, 255, 200), font=small_font, anchor='mm')
    
    # 12. 装饰线条
    draw.line([(45, 290), (170, 290)], fill=(150, 100, 200), width=3)
    draw.line([(45, 295), (170, 295)], fill=(100, 80, 150), width=1)
    
    # 13. 星星装饰
    for i in range(3):
        star_x = width - 50 - i * 35
        star_y = 45
        draw.text((star_x, star_y), "★", fill=(255, 215, 0), font=small_font)
    
    # 14. 底部装饰线
    draw.line([(0, height - 2), (width, height - 2)], fill=(100, 80, 150), width=2)
    
    # 保存图片
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes

# ==================== 等级系统 ====================

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
        
        c.execute("SELECT role_id FROM level_roles WHERE guild_id=? AND level=?", (str(guild_id), user_data["level"]))
        reward = c.fetchone()
        if reward:
            role = message.guild.get_role(int(reward[0]))
            if role:
                await message.author.add_roles(role)
    
    if level_up:
        embed = discord.Embed(title="🎉 等级提升！", description=f"{message.author.mention} 升到了 **{user_data['level']} 级**！", color=discord.Color.gold())
        await message.channel.send(embed=embed)
    
    update_user_data(guild_id, user_id, user_data)
    await bot.process_commands(message)

# ==================== 语音经验 ====================

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
                embed = discord.Embed(title="🔊 加入语音", description=f"{member.mention} 加入了 {after.channel.mention}", color=discord.Color.green())
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
                    
                    c.execute("SELECT role_id FROM level_roles WHERE guild_id=? AND level=?", (str(guild_id), user_data["level"]))
                    reward = c.fetchone()
                    if reward:
                        role = member.guild.get_role(int(reward[0]))
                        if role:
                            await member.add_roles(role)
                
                update_user_data(guild_id, member.id, user_data)
            del voice_tracker[member.id]
        
        c.execute("SELECT voice_log_channel FROM log_settings WHERE guild_id=?", (str(guild_id),))
        result = c.fetchone()
        if result and result[0]:
            channel = member.guild.get_channel(int(result[0]))
            if channel:
                embed = discord.Embed(title="🔇 离开语音", description=f"{member.mention} 离开了 {before.channel.mention}", color=discord.Color.red())
                await channel.send(embed=embed)

# ==================== 斜杠命令 ====================

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot已登录: {bot.user}")

# 等级命令
@bot.tree.command(name="rank", description="查看等级卡片")
async def slash_rank(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    user_data = get_user_data(interaction.guild.id, member.id)
    rank_pos = get_rank(interaction.guild.id, member.id)
    needed_xp = user_data["level"] * 50
    
    try:
        img_bytes = await create_rank_card(member, user_data["level"], user_data["xp"], needed_xp, rank_pos, interaction.guild.name)
        file = discord.File(img_bytes, filename="level.png")
        await interaction.response.send_message(file=file)
    except:
        embed = discord.Embed(title=f"📊 {member.name}的等级", description=f"**等级：** {user_data['level']}\n**经验：** {user_data['xp']}/{needed_xp} XP\n**排名：** #{rank_pos}", color=discord.Color.blue())
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="查看等级排行榜")
async def slash_leaderboard(interaction: discord.Interaction):
    c.execute("SELECT user_id, level, xp FROM users WHERE guild_id=? ORDER BY level DESC, xp DESC LIMIT 10", (str(interaction.guild.id),))
    top_users = c.fetchall()
    
    if not top_users:
        await interaction.response.send_message("📊 暂无数据")
        return
    
    description = ""
    for i, (user_id, level, xp) in enumerate(top_users, 1):
        try:
            user = await bot.fetch_user(int(user_id))
            name = user.name
        except:
            name = f"用户{user_id[:8]}"
        
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        description += f"{medal} **{name}** - Lv.{level} ({xp} XP)\n"
    
    embed = discord.Embed(title=f"🏆 {interaction.guild.name} 等级排行榜", description=description, color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="add_level_role", description="添加等级奖励角色")
@admin_only()
async def add_level_role(interaction: discord.Interaction, level: int, role: discord.Role):
    c.execute("INSERT OR REPLACE INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?)", (str(interaction.guild.id), level, str(role.id)))
    conn.commit()
    await interaction.response.send_message(f"✅ 已设置等级 {level} 奖励角色 {role.mention}", ephemeral=True)

@bot.tree.command(name="set_xp_rate", description="设置经验倍率")
@admin_only()
async def set_xp_rate(interaction: discord.Interaction, rate: float):
    c.execute("INSERT OR REPLACE INTO guild_settings (guild_id, xp_rate) VALUES (?, ?)", (str(interaction.guild.id), rate))
    conn.commit()
    await interaction.response.send_message(f"✅ 经验倍率已设置为 {rate}x", ephemeral=True)

# ==================== 反应角色 ====================

@bot.tree.command(name="add_reaction_role", description="添加反应角色")
@admin_only()
async def add_reaction_role(interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
    c.execute("INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)", (str(interaction.guild.id), message_id, emoji, str(role.id)))
    conn.commit()
    await interaction.response.send_message(f"✅ 已添加反应角色: {emoji} → {role.mention}", ephemeral=True)

@bot.tree.command(name="remove_reaction_role", description="移除反应角色")
@admin_only()
async def remove_reaction_role(interaction: discord.Interaction, message_id: str, emoji: str):
    c.execute("DELETE FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?", (str(interaction.guild.id), message_id, emoji))
    conn.commit()
    await interaction.response.send_message(f"✅ 已移除反应角色", ephemeral=True)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    
    c.execute("SELECT role_id FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?", (str(payload.guild_id), str(payload.message_id), payload.emoji.name))
    result = c.fetchone()
    
    if result:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(int(result[0]))
        member = guild.get_member(payload.user_id)
        if role and member:
            await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    c.execute("SELECT role_id FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?", (str(payload.guild_id), str(payload.message_id), payload.emoji.name))
    result = c.fetchone()
    
    if result:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(int(result[0]))
        member = guild.get_member(payload.user_id)
        if role and member:
            await member.remove_roles(role)

# ==================== 计数器 ====================

@bot.tree.command(name="add_counter", description="添加计数器")
@admin_only()
async def add_counter(interaction: discord.Interaction, counter_type: str, channel: discord.TextChannel, message_template: str):
    c.execute("INSERT INTO counters (guild_id, counter_type, channel_id, message_template) VALUES (?, ?, ?, ?)", (str(interaction.guild.id), counter_type, str(channel.id), message_template))
    conn.commit()
    await interaction.response.send_message(f"✅ 已添加计数器: {counter_type}", ephemeral=True)

@bot.tree.command(name="update_counter", description="更新计数器数值")
@admin_only()
async def update_counter(interaction: discord.Interaction, counter_type: str, value: int):
    c.execute("UPDATE counters SET current_value=? WHERE guild_id=? AND counter_type=?", (value, str(interaction.guild.id), counter_type))
    conn.commit()
    
    c.execute("SELECT channel_id, message_template FROM counters WHERE guild_id=? AND counter_type=?", (str(interaction.guild.id), counter_type))
    result = c.fetchone()
    if result:
        channel = interaction.guild.get_channel(int(result[0]))
        if channel:
            message = result[1].replace("{value}", str(value))
            async for msg in channel.history(limit=10):
                if msg.author == bot.user and counter_type in msg.content:
                    await msg.edit(content=message)
                    await interaction.response.send_message(f"✅ 已更新计数器", ephemeral=True)
                    return
            await channel.send(message)
            await interaction.response.send_message(f"✅ 已更新计数器", ephemeral=True)

@bot.tree.command(name="remove_counter", description="移除计数器")
@admin_only()
async def remove_counter(interaction: discord.Interaction, counter_type: str):
    c.execute("DELETE FROM counters WHERE guild_id=? AND counter_type=?", (str(interaction.guild.id), counter_type))
    conn.commit()
    await interaction.response.send_message(f"✅ 已移除计数器", ephemeral=True)

# ==================== 日志系统 ====================

@bot.tree.command(name="set_log_channel", description="设置消息日志频道")
@admin_only()
async def set_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    c.execute("INSERT OR REPLACE INTO log_settings (guild_id, message_log_channel) VALUES (?, ?)", (str(interaction.guild.id), str(channel.id)))
    conn.commit()
    await interaction.response.send_message(f"✅ 消息日志频道已设置为 {channel.mention}", ephemeral=True)

@bot.tree.command(name="set_voice_log", description="设置语音日志频道")
@admin_only()
async def set_voice_log(interaction: discord.Interaction, channel: discord.TextChannel):
    c.execute("INSERT OR REPLACE INTO log_settings (guild_id, voice_log_channel) VALUES (?, ?)", (str(interaction.guild.id), str(channel.id)))
    conn.commit()
    await interaction.response.send_message(f"✅ 语音日志频道已设置为 {channel.mention}", ephemeral=True)

@bot.tree.command(name="set_mod_log", description="设置管理日志频道")
@admin_only()
async def set_mod_log(interaction: discord.Interaction, channel: discord.TextChannel):
    c.execute("INSERT OR REPLACE INTO log_settings (guild_id, mod_log_channel) VALUES (?, ?)", (str(interaction.guild.id), str(channel.id)))
    conn.commit()
    await interaction.response.send_message(f"✅ 管理日志频道已设置为 {channel.mention}", ephemeral=True)

@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    
    c.execute("SELECT message_log_channel FROM log_settings WHERE guild_id=?", (str(message.guild.id),))
    result = c.fetchone()
    
    if result and result[0]:
        channel = message.guild.get_channel(int(result[0]))
        if channel:
            embed = discord.Embed(title="🗑️ 消息被删除", description=f"**频道:** {message.channel.mention}\n**用户:** {message.author.mention}\n**内容:** {message.content[:500]}", color=discord.Color.red(), timestamp=datetime.now())
            await channel.send(embed=embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
    
    c.execute("SELECT message_log_channel FROM log_settings WHERE guild_id=?", (str(before.guild.id),))
    result = c.fetchone()
    
    if result and result[0]:
        channel = before.guild.get_channel(int(result[0]))
        if channel:
            embed = discord.Embed(title="✏️ 消息被编辑", description=f"**频道:** {before.channel.mention}\n**用户:** {before.author.mention}\n**之前:** {before.content[:500]}\n**之后:** {after.content[:500]}", color=discord.Color.blue(), timestamp=datetime.now())
            await channel.send(embed=embed)

# ==================== 其他命令 ====================

@bot.tree.command(name="kick", description="踢出用户")
@admin_only()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"✅ 已踢出 {member.mention}", ephemeral=True)
    
    c.execute("SELECT mod_log_channel FROM log_settings WHERE guild_id=?", (str(interaction.guild.id),))
    result = c.fetchone()
    if result and result[0]:
        channel = interaction.guild.get_channel(int(result[0]))
        if channel:
            embed = discord.Embed(title="👢 用户被踢出", description=f"**用户:** {member.mention}\n**管理员:** {interaction.user.mention}\n**原因:** {reason or '无'}", color=discord.Color.orange(), timestamp=datetime.now())
            await channel.send(embed=embed)

@bot.tree.command(name="ban", description="封禁用户")
@admin_only()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"✅ 已封禁 {member.mention}", ephemeral=True)

@bot.tree.command(name="clear", description="清除消息")
@admin_only()
async def clear(interaction: discord.Interaction, amount: int):
    await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"✅ 已清除 {amount} 条消息", ephemeral=True)

@bot.tree.command(name="userinfo", description="查看用户信息")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"👤 {member.name} 的信息", color=member.color)
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="加入时间", value=member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "未知", inline=True)
    embed.add_field(name="注册时间", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="最高角色", value=member.top_role.mention if member.top_role else "无", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="help", description="查看帮助")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 Bot 帮助", color=discord.Color.green())
    embed.add_field(name="📊 等级系统", value="/rank - 查看等级\n/leaderboard - 排行榜\n/add_level_role - 等级奖励\n/set_xp_rate - 经验倍率", inline=False)
    embed.add_field(name="🎭 反应角色", value="/add_reaction_role - 添加\n/remove_reaction_role - 移除", inline=False)
    embed.add_field(name="🔢 计数器", value="/add_counter - 添加\n/update_counter - 更新\n/remove_counter - 移除", inline=False)
    embed.add_field(name="📋 日志系统", value="/set_log_channel - 消息日志\n/set_voice_log - 语音日志\n/set_mod_log - 管理日志", inline=False)
    embed.add_field(name="🔧 管理", value="/kick, /ban, /clear", inline=False)
    embed.add_field(name="ℹ️ 信息", value="/userinfo", inline=False)
    await interaction.response.send_message(embed=embed)

# ==================== 运行 ====================

if __name__ == "__main__":
    bot.run(TOKEN)
