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
from pilcord import RankCard, CardSettings

# ========== 配置 ==========
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ========== 检查是否是群主 ==========
def is_owner():
    async def predicate(ctx):
        return ctx.author == ctx.guild.owner
    return commands.check(predicate)

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

# ========== 等级卡片（图片） ==========
@bot.command()
async def rank(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_data = get_user_data(ctx.guild.id, member.id)
    settings = get_guild_settings(ctx.guild.id)
    rank_pos = get_rank(ctx.guild.id, member.id)
    
    current_xp = user_data["xp"]
    needed_xp = user_data["level"] * 50
    
    card_settings = CardSettings(
        bar_color=settings["card_color"],
        text_color="white",
        background_color="#2C2F33"
    )
    
    if settings["card_background"]:
        card_settings.background = settings["card_background"]
    
    try:
        card = RankCard(
            settings=card_settings,
            avatar=member.display_avatar.url,
            level=user_data["level"],
            current_exp=current_xp,
            max_exp=needed_xp,
            username=member.name,
            rank=rank_pos,
            server_name=ctx.guild.name
        )
        
        image_bytes = await card.card1()
        file = discord.File(image_bytes, filename="rank.png")
        await ctx.send(file=file)
    except Exception as e:
        embed = discord.Embed(
            title=f"{member.name} 的等级",
            description=f"等级: **{user_data['level']}**\n经验: {current_xp}/{needed_xp} XP\n排名: #{rank_pos}\n语音经验: {user_data['voice_xp']}",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

# ========== 排行榜 ==========
@bot.command()
async def leaderboard(ctx):
    c.execute("SELECT user_id, level, xp FROM users WHERE guild_id=? ORDER BY level DESC, xp DESC LIMIT 10", (str(ctx.guild.id),))
    top_users = c.fetchall()
    
    embed = discord.Embed(title="🏆 等级排行榜", color=discord.Color.gold())
    for i, (user_id, level, xp) in enumerate(top_users, 1):
        try:
            user = await bot.fetch_user(int(user_id))
            name = user.name
        except:
            name = f"用户{user_id[:8]}"
        embed.add_field(name=f"{i}. {name}", value=f"Lv.{level} ({xp} XP)", inline=False)
    await ctx.send(embed=embed)

# ========== 自定义命令（群主专用） ==========
@bot.command()
@is_owner()
async def addcmd(ctx, cmd_name, *, response):
    try:
        c.execute("INSERT INTO custom_commands (guild_id, command_name, response) VALUES (?, ?, ?)",
                  (str(ctx.guild.id), cmd_name, response))
        conn.commit()
        await ctx.send(f"✅ 已添加自定义命令 `!{cmd_name}`")
    except sqlite3.IntegrityError:
        await ctx.send(f"❌ 命令 `!{cmd_name}` 已存在")

@bot.command()
@is_owner()
async def delcmd(ctx, cmd_name):
    c.execute("DELETE FROM custom_commands WHERE guild_id=? AND command_name=?", (str(ctx.guild.id), cmd_name))
    conn.commit()
    await ctx.send(f"✅ 已删除自定义命令 `!{cmd_name}`")

@bot.command()
async def listcmds(ctx):
    c.execute("SELECT command_name FROM custom_commands WHERE guild_id=?", (str(ctx.guild.id),))
    commands_list = c.fetchall()
    if commands_list:
        cmd_names = ", ".join([f"!{cmd[0]}" for cmd in commands_list])
        await ctx.send(f"📋 自定义命令: {cmd_names}")
    else:
        await ctx.send("📭 暂无自定义命令")

# ========== 反应角色（群主专用） ==========
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
@is_owner()
async def addreactionrole(ctx, message_id: int, emoji, role: discord.Role):
    c.execute("INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)",
              (str(ctx.guild.id), str(message_id), emoji, str(role.id)))
    conn.commit()
    await ctx.send(f"✅ 已添加反应角色: {emoji} → {role.mention}")

# ========== 等级奖励角色（群主专用） ==========
@bot.command()
@is_owner()
async def addlevelrole(ctx, level: int, role: discord.Role):
    c.execute("INSERT OR REPLACE INTO level_rewards (guild_id, level, role_id) VALUES (?, ?, ?)",
              (str(ctx.guild.id), level, str(role.id)))
    conn.commit()
    await ctx.send(f"✅ {level} 级奖励角色设置为 {role.mention}")

@bot.command()
@is_owner()
async def removelevelrole(ctx, level: int):
    c.execute("DELETE FROM level_rewards WHERE guild_id=? AND level=?", (str(ctx.guild.id), level))
    conn.commit()
    await ctx.send(f"✅ 已删除 {level} 级的奖励角色")

# ========== 自定义 XP 倍率（群主专用） ==========
@bot.command()
@is_owner()
async def setxprate(ctx, rate: float):
    rate = max(0.1, min(5.0, rate))
    c.execute("INSERT OR REPLACE INTO guild_settings (guild_id, xp_rate) VALUES (?, ?)", (str(ctx.guild.id), rate))
    conn.commit()
    await ctx.send(f"✅ 经验倍率已设置为 {rate}x")

@bot.command()
@is_owner()
async def setvoicexprate(ctx, rate: float):
    rate = max(0.1, min(5.0, rate))
    c.execute("INSERT OR REPLACE INTO guild_settings (guild_id, voice_xp_rate) VALUES (?, ?)", (str(ctx.guild.id), rate))
    conn.commit()
    await ctx.send(f"✅ 语音经验倍率已设置为 {rate}x")

@bot.command()
@is_owner()
async def setcardbg(ctx, url: str):
    c.execute("INSERT OR REPLACE INTO guild_settings (guild_id, card_background) VALUES (?, ?)", (str(ctx.guild.id), url))
    conn.commit()
    await ctx.send(f"✅ 等级卡片背景已更新")

@bot.command()
@is_owner()
async def setcardcolor(ctx, color: str):
    if not color.startswith("#"):
        color = "#" + color
    c.execute("INSERT OR REPLACE INTO guild_settings (guild_id, card_color) VALUES (?, ?)", (str(ctx.guild.id), color))
    conn.commit()
    await ctx.send(f"✅ 等级卡片颜色已设置为 {color}")

# ========== 计数器系统（群主专用） ==========
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

@bot.command()
@is_owner()
async def addcounter(ctx, counter_type: str, channel: discord.TextChannel, *, template: str):
    c.execute("INSERT INTO counters (guild_id, counter_type, channel_id, message_template) VALUES (?, ?, ?, ?)",
              (str(ctx.guild.id), counter_type, str(channel.id), template))
    conn.commit()
    await ctx.send(f"✅ 已添加 {counter_type} 计数器")

# ========== YouTube 通知系统（群主专用） ==========
@tasks.loop(minutes=10)
async def check_youtube():
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

@bot.command()
@is_owner()
async def addyoutube(ctx, youtube_channel_id: str, notification_channel: discord.TextChannel):
    c.execute("INSERT INTO youtube_notifications (guild_id, channel_id, youtube_channel, last_video_id) VALUES (?, ?, ?, ?)",
              (str(ctx.guild.id), str(notification_channel.id), youtube_channel_id, ""))
    conn.commit()
    await ctx.send(f"✅ 已添加 YouTube 频道 {youtube_channel_id} 的通知")

# ========== 欢迎消息（群主专用） ==========
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

@bot.command()
@is_owner()
async def setwelcome(ctx, channel: discord.TextChannel, *, message: str):
    c.execute("INSERT OR REPLACE INTO welcome_settings (guild_id, channel_id, message) VALUES (?, ?, ?)",
              (str(ctx.guild.id), str(channel.id), message))
    conn.commit()
    await ctx.send(f"✅ 欢迎消息已设置到 {channel.mention}")

# ========== 日志系统（群主专用） ==========
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

@bot.command()
@is_owner()
async def setlogchannel(ctx, channel: discord.TextChannel):
    c.execute("INSERT OR REPLACE INTO log_settings (guild_id, message_log_channel) VALUES (?, ?)",
              (str(ctx.guild.id), str(channel.id)))
    conn.commit()
    await ctx.send(f"✅ 日志频道已设置为 {channel.mention}")

@bot.command()
@is_owner()
async def setvoicelog(ctx, channel: discord.TextChannel):
    c.execute("INSERT OR REPLACE INTO log_settings (guild_id, voice_log_channel) VALUES (?, ?)",
              (str(ctx.guild.id), str(channel.id)))
    conn.commit()
    await ctx.send(f"✅ 语音日志频道已设置为 {channel.mention}")

# ========== 自定义 XP 值（群主专用） ==========
@bot.command()
@is_owner()
async def addxp(ctx, member: discord.Member, amount: int):
    user_data = get_user_data(ctx.guild.id, member.id)
    user_data["xp"] += amount
    update_user_data(ctx.guild.id, member.id, user_data)
    await ctx.send(f"✅ 已给 {member.mention} 添加 {amount} 经验")

# ========== 管理命令（需要相应权限） ==========
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

# ========== 帮助命令 ==========
@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="✨ Arcane 功能帮助 ✨",
        description="**等级系统**\n`!rank` - 查看等级卡片（图片）\n`!leaderboard` - 排行榜\n\n"
                    "**自定义命令**\n`!addcmd` - 添加自定义命令（仅群主）\n`!delcmd` - 删除自定义命令（仅群主）\n`!listcmds` - 列出自定义命令\n\n"
                    "**反应角色**\n`!addreactionrole` - 添加反应角色（仅群主）\n\n"
                    "**YouTube 通知**\n`!addyoutube` - 添加 YouTube 频道通知（仅群主）\n\n"
                    "**计数器**\n`!addcounter` - 添加计数器（仅群主）\n\n"
                    "**欢迎消息**\n`!setwelcome` - 设置欢迎消息（仅群主）\n\n"
                    "**日志**\n`!setlogchannel` - 设置消息日志频道（仅群主）\n`!setvoicelog` - 设置语音日志频道（仅群主）\n\n"
                    "**管理**\n`!kick`, `!ban`, `!clear` - 管理命令\n`!lock`, `!unlock` - 锁定/解锁频道",
        color=discord.Color.purple()
    )
    await ctx.send(embed=embed)

# ========== 启动 ==========
@bot.event
async def on_ready():
    print(f"✅ {bot.user} 已上线！")
    print(f"已连接 {len(bot.guilds)} 个服务器")
    update_counters.start()
    if os.getenv("YOUTUBE_API_KEY"):
        check_youtube.start()

bot.run(TOKEN)
