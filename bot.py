import discord
from discord.ext import commands, tasks
import json
import os
import aiohttp
import asyncio
from datetime import datetime, timedelta
import sqlite3
from collections import defaultdict
import re

# ========== 配置 ==========
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", 0))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ========== 数据库初始化 ==========
conn = sqlite3.connect("arcane_data.db")
c = conn.cursor()

# 用户数据表
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id TEXT,
    guild_id TEXT,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    voice_xp INTEGER DEFAULT 0,
    reaction_xp INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, guild_id)
)''')

# 等级奖励角色表
c.execute('''CREATE TABLE IF NOT EXISTS level_rewards (
    guild_id TEXT,
    level INTEGER,
    role_id TEXT,
    PRIMARY KEY (guild_id, level)
)''')

# 自定义命令表
c.execute('''CREATE TABLE IF NOT EXISTS custom_commands (
    guild_id TEXT,
    command_name TEXT,
    response TEXT,
    PRIMARY KEY (guild_id, command_name)
)''')

# 反应角色表
c.execute('''CREATE TABLE IF NOT EXISTS reaction_roles (
    guild_id TEXT,
    message_id TEXT,
    emoji TEXT,
    role_id TEXT
)''')

# YouTube通知表
c.execute('''CREATE TABLE IF NOT EXISTS youtube_notifications (
    guild_id TEXT,
    channel_id TEXT,
    youtube_channel TEXT
)''')

# 计数器表
c.execute('''CREATE TABLE IF NOT EXISTS counters (
    guild_id TEXT,
    counter_type TEXT,
    channel_id TEXT,
    message_template TEXT
)''')

# 欢迎设置表
c.execute('''CREATE TABLE IF NOT EXISTS welcome_settings (
    guild_id TEXT PRIMARY KEY,
    channel_id TEXT,
    message TEXT,
    background_url TEXT,
    color TEXT,
    reactions TEXT
)''')

# 服务器设置表
c.execute('''CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id TEXT PRIMARY KEY,
    custom_name TEXT,
    custom_avatar TEXT,
    custom_banner TEXT,
    xp_rate REAL DEFAULT 1.0,
    voice_xp_rate REAL DEFAULT 1.0,
    reaction_xp_rate REAL DEFAULT 1.0
)''')

# 日志设置表
c.execute('''CREATE TABLE IF NOT EXISTS log_settings (
    guild_id TEXT PRIMARY KEY,
    message_log_channel TEXT,
    voice_log_channel TEXT,
    mod_log_channel TEXT
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
        return {"custom_name": None, "custom_avatar": None, "custom_banner": None, "xp_rate": 1.0, "voice_xp_rate": 1.0, "reaction_xp_rate": 1.0}
    return {"custom_name": result[1], "custom_avatar": result[2], "custom_banner": result[3], "xp_rate": result[4], "voice_xp_rate": result[5], "reaction_xp_rate": result[6]}

# ========== 等级系统 ==========
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    guild_id = message.guild.id
    user_id = message.author.id
    
    settings = get_guild_settings(guild_id)
    user_data = get_user_data(guild_id, user_id)
    
    # 获得经验 (1-3 随机，乘以倍率)
    xp_gain = int((1 + (hash(str(user_id) + str(datetime.now().minute)) % 3)) * settings["xp_rate"])
    user_data["xp"] += xp_gain
    
    # 检查升级
    xp_needed = user_data["level"] * 50
    level_up = False
    while user_data["xp"] >= xp_needed:
        user_data["level"] += 1
        user_data["xp"] -= xp_needed
        xp_needed = user_data["level"] * 50
        level_up = True
        
        # 检查等级奖励角色
        c.execute("SELECT role_id FROM level_rewards WHERE guild_id=? AND level=?", (str(guild_id), user_data["level"]))
        reward = c.fetchone()
        if reward:
            role = message.guild.get_role(int(reward[0]))
            if role:
                await message.author.add_roles(role)
                await message.channel.send(f"🎉 {message.author.mention} 达到 {user_data['level']} 级，获得 {role.mention} 角色！")
    
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
    
    # 用户加入语音频道
    if before.channel is None and after.channel is not None:
        voice_tracker[member.id]["join_time"] = datetime.now()
    
    # 用户离开语音频道
    elif before.channel is not None and after.channel is None:
        if member.id in voice_tracker and "join_time" in voice_tracker[member.id]:
            duration = (datetime.now() - voice_tracker[member.id]["join_time"]).total_seconds()
            if duration >= 60:  # 至少1分钟才给经验
                settings = get_guild_settings(guild_id)
                xp_gain = int((duration / 60) * 5 * settings["voice_xp_rate"])  # 每分钟5经验
                
                user_data = get_user_data(guild_id, member.id)
                user_data["voice_xp"] += xp_gain
                
                # 语音经验也增加总经验
                user_data["xp"] += xp_gain
                
                # 检查升级
                xp_needed = user_data["level"] * 50
                while user_data["xp"] >= xp_needed:
                    user_data["level"] += 1
                    user_data["xp"] -= xp_needed
                    xp_needed = user_data["level"] * 50
                
                update_user_data(guild_id, member.id, user_data)
            del voice_tracker[member.id]

# ========== 自定义命令系统 ==========
@bot.command()
@commands.has_permissions(administrator=True)
async def addcmd(ctx, cmd_name, *, response):
    """添加自定义命令"""
    try:
        c.execute("INSERT INTO custom_commands (guild_id, command_name, response) VALUES (?, ?, ?)",
                  (str(ctx.guild.id), cmd_name, response))
        conn.commit()
        await ctx.send(f"✅ 已添加自定义命令 `!{cmd_name}`")
    except sqlite3.IntegrityError:
        await ctx.send(f"❌ 命令 `!{cmd_name}` 已存在")

@bot.command()
@commands.has_permissions(administrator=True)
async def delcmd(ctx, cmd_name):
    """删除自定义命令"""
    c.execute("DELETE FROM custom_commands WHERE guild_id=? AND command_name=?", (str(ctx.guild.id), cmd_name))
    conn.commit()
    await ctx.send(f"✅ 已删除自定义命令 `!{cmd_name}`")

@bot.command()
async def listcmds(ctx):
    """列出所有自定义命令"""
    c.execute("SELECT command_name FROM custom_commands WHERE guild_id=?", (str(ctx.guild.id),))
    commands_list = c.fetchall()
    if commands_list:
        cmd_names = ", ".join([f"!{cmd[0]}" for cmd in commands_list])
        await ctx.send(f"📋 自定义命令: {cmd_names}")
    else:
        await ctx.send("📭 暂无自定义命令")

# 动态执行自定义命令
async def execute_custom_command(ctx, cmd_name):
    c.execute("SELECT response FROM custom_commands WHERE guild_id=? AND command_name=?", (str(ctx.guild.id), cmd_name))
    result = c.fetchone()
    if result:
        await ctx.send(result[0])
        return True
    return False

# ========== 反应角色系统 ==========
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    
    c.execute("SELECT role_id FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?",
              (str(payload.guild_id), str(payload.message_id), payload.emoji.name))
    result = c.fetchone()
    if result:
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        role = guild.get_role(int(result[0]))
        if role:
            await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    c.execute("SELECT role_id FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?",
              (str(payload.guild_id), str(payload.message_id), payload.emoji.name))
    result = c.fetchone()
    if result:
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        role = guild.get_role(int(result[0]))
        if role and role in member.roles:
            await member.remove_roles(role)

@bot.command()
@commands.has_permissions(administrator=True)
async def addreactionrole(ctx, message_id: int, emoji, role: discord.Role):
    """添加反应角色"""
    c.execute("INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)",
              (str(ctx.guild.id), str(message_id), emoji, str(role.id)))
    conn.commit()
    await ctx.send(f"✅ 已添加反应角色: {emoji} → {role.mention}")

# ========== 等级奖励角色系统 ==========
@bot.command()
@commands.has_permissions(administrator=True)
async def addlevelrole(ctx, level: int, role: discord.Role):
    """添加等级奖励角色"""
    c.execute("INSERT OR REPLACE INTO level_rewards (guild_id, level, role_id) VALUES (?, ?, ?)",
              (str(ctx.guild.id), level, str(role.id)))
    conn.commit()
    await ctx.send(f"✅ {level} 级奖励角色设置为 {role.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def removelevelrole(ctx, level: int):
    """删除等级奖励角色"""
    c.execute("DELETE FROM level_rewards WHERE guild_id=? AND level=?", (str(ctx.guild.id), level))
    conn.commit()
    await ctx.send(f"✅ 已删除 {level} 级的奖励角色")

# ========== 自定义 XP 倍率 ==========
@bot.command()
@commands.has_permissions(administrator=True)
async def setxprate(ctx, rate: float):
    """设置经验倍率 (0.1-5.0)"""
    rate = max(0.1, min(5.0, rate))
    c.execute("INSERT OR REPLACE INTO guild_settings (guild_id, xp_rate) VALUES (?, ?)", (str(ctx.guild.id), rate))
    conn.commit()
    await ctx.send(f"✅ 经验倍率已设置为 {rate}x")

@bot.command()
@commands.has_permissions(administrator=True)
async def setvoicexprate(ctx, rate: float):
    """设置语音经验倍率 (0.1-5.0)"""
    rate = max(0.1, min(5.0, rate))
    c.execute("INSERT OR REPLACE INTO guild_settings (guild_id, voice_xp_rate) VALUES (?, ?)", (str(ctx.guild.id), rate))
    conn.commit()
    await ctx.send(f"✅ 语音经验倍率已设置为 {rate}x")

# ========== 排行榜 ==========
@bot.command()
async def leaderboard(ctx):
    """查看等级排行榜"""
    c.execute("SELECT user_id, level, xp FROM users WHERE guild_id=? ORDER BY level DESC, xp DESC LIMIT 10", (str(ctx.guild.id),))
    top_users = c.fetchall()
    
    embed = discord.Embed(title="🏆 等级排行榜", color=discord.Color.gold())
    for i, (user_id, level, xp) in enumerate(top_users, 1):
        user = await bot.fetch_user(int(user_id))
        embed.add_field(name=f"{i}. {user.name}", value=f"Lv.{level} ({xp} XP)", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def rank(ctx, member: discord.Member = None):
    """查看等级"""
    member = member or ctx.author
    user_data = get_user_data(ctx.guild.id, member.id)
    
    embed = discord.Embed(
        title=f"{member.name} 的等级",
        description=f"等级: **{user_data['level']}**\n经验: {user_data['xp']}/{user_data['level'] * 50}\n语音经验: {user_data['voice_xp']}\n反应经验: {user_data['reaction_xp']}",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

# ========== 自定义 Bot 形象 ==========
@bot.command()
@commands.has_permissions(administrator=True)
async def setbotname(ctx, *, name: str):
    """设置机器人在本服务器的显示名称"""
    if len(name) > 32:
        await ctx.send("❌ 名称不能超过 32 个字符")
        return
    await ctx.guild.me.edit(nick=name)
    c.execute("INSERT OR REPLACE INTO guild_settings (guild_id, custom_name) VALUES (?, ?)", (str(ctx.guild.id), name))
    conn.commit()
    await ctx.send(f"✅ 机器人名称已设置为: {name}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setbotavatar(ctx, url: str):
    """设置机器人在本服务器的头像"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    image_data = await resp.read()
                    await bot.user.edit(avatar=image_data)
                    await ctx.send("✅ 机器人头像已更新")
    except:
        await ctx.send("❌ 无效的图片 URL")

# ========== 计数器系统 ==========
@bot.command()
@commands.has_permissions(administrator=True)
async def addcounter(ctx, counter_type: str, channel: discord.TextChannel, *, template: str):
    """添加计数器 (member/role/channel)"""
    c.execute("INSERT INTO counters (guild_id, counter_type, channel_id, message_template) VALUES (?, ?, ?, ?)",
              (str(ctx.guild.id), counter_type, str(channel.id), template))
    conn.commit()
    await ctx.send(f"✅ 已添加 {counter_type} 计数器")

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
                else:
                    continue
                message = template.replace("{count}", str(count))
                await channel.edit(name=message)

# ========== 欢迎消息系统 ==========
@bot.event
async def on_member_join(member):
    c.execute("SELECT channel_id, message, background_url, color, reactions FROM welcome_settings WHERE guild_id=?", (str(member.guild.id),))
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

@bot.command()
@commands.has_permissions(administrator=True)
async def setwelcome(ctx, channel: discord.TextChannel, *, message: str):
    """设置欢迎消息"""
    c.execute("INSERT OR REPLACE INTO welcome_settings (guild_id, channel_id, message) VALUES (?, ?, ?)",
              (str(ctx.guild.id), str(channel.id), message))
    conn.commit()
    await ctx.send(f"✅ 欢迎消息已设置到 {channel.mention}")

# ========== 日志系统 ==========
@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    c.execute("SELECT message_log_channel FROM log_settings WHERE guild_id=?", (str(message.guild.id),))
    result = c.fetchone()
    if result:
        channel = message.guild.get_channel(int(result[0]))
        if channel:
            embed = discord.Embed(
                title="📝 消息删除",
                description=f"作者: {message.author.mention}\n频道: {message.channel.mention}\n内容: {message.content[:500]}",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            await channel.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def setlogchannel(ctx, channel: discord.TextChannel):
    """设置日志频道"""
    c.execute("INSERT OR REPLACE INTO log_settings (guild_id, message_log_channel) VALUES (?, ?)",
              (str(ctx.guild.id), str(channel.id)))
    conn.commit()
    await ctx.send(f"✅ 日志频道已设置为 {channel.mention}")

# ========== 自定义 XP 值 ==========
@bot.command()
@commands.has_permissions(administrator=True)
async def addxp(ctx, member: discord.Member, amount: int):
    """给用户添加经验"""
    user_data = get_user_data(ctx.guild.id, member.id)
    user_data["xp"] += amount
    update_user_data(ctx.guild.id, member.id, user_data)
    await ctx.send(f"✅ 已给 {member.mention} 添加 {amount} 经验")

# ========== 帮助命令 ==========
@bot.command()
async def help(ctx):
    """显示帮助"""
    embed = discord.Embed(
        title="✨ Arcane 功能帮助 ✨",
        description="**等级系统**\n`!rank` - 查看等级\n`!leaderboard` - 排行榜\n`!addlevelrole` - 设置等级奖励角色\n`!setxprate` - 设置经验倍率\n\n"
                    "**自定义命令**\n`!addcmd` - 添加自定义命令\n`!delcmd` - 删除自定义命令\n`!listcmds` - 列出自定义命令\n\n"
                    "**反应角色**\n`!addreactionrole` - 添加反应角色\n\n"
                    "**管理**\n`!kick`, `!ban`, `!clear` - 管理命令\n`!setwelcome` - 设置欢迎消息\n`!setlogchannel` - 设置日志频道\n\n"
                    "**Bot 个性化**\n`!setbotname` - 设置机器人名称\n`!setbotavatar` - 设置机器人头像\n\n"
                    "**计数器**\n`!addcounter` - 添加计数器\n\n"
                    "**管理员命令**\n`!addxp` - 添加经验\n`!setvoicexprate` - 语音经验倍率",
        color=discord.Color.purple()
    )
    await ctx.send(embed=embed)

# ========== 基础管理命令 ==========
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    await member.kick(reason=reason)
    await ctx.send(f"✅ 已踢出 {member.mention}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    await member.ban(reason=reason)
    await ctx.send(f"✅ 已封禁 {member.mention}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"✅ 已清除 {amount} 条消息", delete_after=3)

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send(f"🔒 {channel.mention} 已锁定")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send(f"🔓 {channel.mention} 已解锁")

# ========== 启动计数器 ==========
@bot.event
async def on_ready():
    print(f"✅ {bot.user} 已上线！")
    print(f"已连接 {len(bot.guilds)} 个服务器")
    update_counters.start()

# ========== 启动 ==========
bot.run(TOKEN)
