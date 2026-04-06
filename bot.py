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
from pilcord import RankCard, CardSettings

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
        card_settings = CardSettings(
            bar_color="#5865F2",
            text_color="white",
            background_color="#2C2F33"
        )
        
        rank_card = RankCard(
            settings=card_settings,
            avatar=member.display_avatar.url,
            level=user_data["level"],
            current_exp=user_data["xp"],
            max_exp=needed_xp,
            username=member.name,
            rank=rank_pos
        )
        
        image_bytes = await rank_card.card1()
        file = discord.File(image_bytes, filename="level.png")
        await interaction.response.send_message(file=file)
    except Exception as e:
        embed = discord.Embed(
            title=f"{member.name} 的等级",
            description=f"等级: **{user_data['level']}**\n经验: {user_data['xp']}/{needed_xp} XP\n排名: #{rank_pos}",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rank", description="查看自己的等级卡片")
async def slash_rank(interaction: discord.Interaction, member: discord.Member = None):
    await slash_level(interaction, member)

@bot.tree.command(name="leaderboard", description="查看等级排行榜")
async def slash_leaderboard(interaction: discord.Interaction):
    c.execute("SELECT user_id, level, xp FROM users WHERE guild_id=? ORDER BY level DESC, xp DESC LIMIT 10", (str(interaction.guild.id),))
    top_users = c.fetchall()
    
    if not top_users:
        await interaction.response.send_message("📭 暂无数据")
        return
    
    embed = discord.Embed(title="🏆 等级排行榜", color=discord.Color.gold())
    for i, (user_id, level, xp) in enumerate(top_users, 1):
        try:
            user = await bot.fetch_user(int(user_id))
            name = user.name
        except:
            name = f"用户{user_id[:8]}"
        
        if i == 1:
            medal = "🥇 "
        elif i == 2:
            medal = "🥈 "
        elif i == 3:
            medal = "🥉 "
        else:
            medal = ""
        
        embed.add_field(name=f"{medal}{i}. {name}", value=f"Lv.{level} ({xp} XP)", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="userinfo", description="查看用户信息")
async def slash_userinfo(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"{member.name} 的信息", color=member.color)
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="加入时间", value=member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "未知", inline=True)
    embed.add_field(name="注册时间", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="最高角色", value=member.top_role.mention if member.top_role else "无", inline=True)
    embed.add_field(name="是否机器人", value="是" if member.bot else "否", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="查看服务器信息")
async def slash_serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=guild.name, color=discord.Color.blue())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="ID", value=guild.id, inline=True)
    embed.add_field(name="创建时间", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="成员数量", value=guild.member_count, inline=True)
    embed.add_field(name="频道数量", value=len(guild.channels), inline=True)
    embed.add_field(name="角色数量", value=len(guild.roles), inline=True)
    embed.add_field(name="服务器所有者", value=guild.owner.mention if guild.owner else "未知", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="avatar", description="查看用户头像")
async def slash_avatar(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"{member.name} 的头像", color=discord.Color.blue())
    embed.set_image(url=member.avatar.url if member.avatar else member.default_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="invite", description="邀请机器人到你的服务器")
async def slash_invite(interaction: discord.Interaction):
    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=8&scope=bot%20applications.commands"
    embed = discord.Embed(title="📎 邀请我", description=f"[点击这里邀请机器人]({invite_url})", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="help", description="查看帮助")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="✨ Arcane Bot 帮助 ✨",
        description="**等级系统**\n`/level` 或 `/rank` - 查看等级卡片\n`/leaderboard` - 排行榜\n`/add_level_role` - 设置等级奖励角色\n`/set_xp_rate` - 设置经验倍率\n\n"
                    "**自定义命令**\n`/add_cmd` - 添加自定义命令\n`/del_cmd` - 删除自定义命令\n`/list_cmds` - 列出自定义命令\n\n"
                    "**反应角色**\n`/add_reaction_role` - 添加反应角色\n\n"
                    "**YouTube 通知**\n`/add_youtube` - 添加 YouTube 频道通知\n\n"
                    "**计数器**\n`/add_counter` - 添加计数器\n\n"
                    "**欢迎消息**\n`/set_welcome` - 设置欢迎消息\n\n"
                    "**日志**\n`/set_log_channel` - 设置消息日志频道\n`/set_voice_log` - 设置语音日志频道\n\n"
                    "**管理**\n`/kick`, `/ban`, `/clear` - 管理命令\n`/lock`, `/unlock` - 锁定/解锁频道\n\n"
                    "**信息**\n`/userinfo` - 用户信息\n`/serverinfo` - 服务器信息\n`/avatar` - 查看头像\n`/invite` - 邀请机器人\n\n"
                    "**权限管理（仅群主）**\n`/add_admin_role` - 添加管理角色\n`/add_admin_user` - 添加管理用户\n`/list_admins` - 查看管理权限",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)

# ========== 等级设置命令 ==========
@bot.tree.command(name="add_level_role", description="设置等级奖励角色")
@admin_only()
async def add_level_role(interaction: discord.Interaction, level: int, role: discord.Role):
    c.execute("INSERT OR REPLACE INTO level_rewards (guild_id, level, role_id) VALUES (?, ?, ?)",
              (str(interaction.guild.id), level, str(role.id)))
    conn.commit()
    await interaction.response.send_message(f"✅ {level} 级奖励角色设置为 {role.mention}", ephemeral=True)

@bot.tree.command(name="remove_level_role", description="删除等级奖励角色")
@admin_only()
async def remove_level_role(interaction: discord.Interaction, level: int):
    c.execute("DELETE FROM level_rewards WHERE guild_id=? AND level=?", (str(interaction.guild.id), level))
    conn.commit()
    await interaction.response.send_message(f"✅ 已删除 {level} 级的奖励角色", ephemeral=True)

@bot.tree.command(name="set_xp_rate", description="设置经验倍率")
@admin_only()
async def set_xp_rate(interaction: discord.Interaction, rate: float):
    rate = max(0.1, min(5.0, rate))
    c.execute("INSERT OR REPLACE INTO guild_settings (guild_id, xp_rate) VALUES (?, ?)", (str(interaction.guild.id), rate))
    conn.commit()
    await interaction.response.send_message(f"✅ 经验倍率已设置为 {rate}x", ephemeral=True)

# ========== 自定义命令 ==========
@bot.tree.command(name="add_cmd", description="添加自定义命令")
@admin_only()
async def add_cmd(interaction: discord.Interaction, name: str, response: str):
    try:
        c.execute("INSERT INTO custom_commands (guild_id, command_name, response) VALUES (?, ?, ?)",
                  (str(interaction.guild.id), name, response))
        conn.commit()
        await interaction.response.send_message(f"✅ 已添加自定义命令 `/{name}`", ephemeral=True)
    except sqlite3.IntegrityError:
        await interaction.response.send_message(f"❌ 命令 `/{name}` 已存在", ephemeral=True)

@bot.tree.command(name="del_cmd", description="删除自定义命令")
@admin_only()
async def del_cmd(interaction: discord.Interaction, name: str):
    c.execute("DELETE FROM custom_commands WHERE guild_id=? AND command_name=?", (str(interaction.guild.id), name))
    conn.commit()
    await interaction.response.send_message(f"✅ 已删除自定义命令 `/{name}`", ephemeral=True)

@bot.tree.command(name="list_cmds", description="列出自定义命令")
async def list_cmds(interaction: discord.Interaction):
    c.execute("SELECT command_name FROM custom_commands WHERE guild_id=?", (str(interaction.guild.id),))
    commands_list = c.fetchall()
    if commands_list:
        cmd_names = ", ".join([f"/{cmd[0]}" for cmd in commands_list])
        await interaction.response.send_message(f"📋 自定义命令: {cmd_names}", ephemeral=True)
    else:
        await interaction.response.send_message("📭 暂无自定义命令", ephemeral=True)

# ========== 反应角色 ==========
@bot.tree.command(name="add_reaction_role", description="添加反应角色")
@admin_only()
async def add_reaction_role(interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
    c.execute("INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)",
              (str(interaction.guild.id), message_id, emoji, str(role.id)))
    conn.commit()
    await interaction.response.send_message(f"✅ 已添加反应角色: {emoji} → {role.mention}", ephemeral=True)

# ========== YouTube 通知 ==========
@bot.tree.command(name="add_youtube", description="添加 YouTube 频道通知")
@admin_only()
async def add_youtube(interaction: discord.Interaction, youtube_channel_id: str, notification_channel: discord.TextChannel):
    c.execute("INSERT INTO youtube_notifications (guild_id, channel_id, youtube_channel, last_video_id) VALUES (?, ?, ?, ?)",
              (str(interaction.guild.id), str(notification_channel.id), youtube_channel_id, ""))
    conn.commit()
    await interaction.response.send_message(f"✅ 已添加 YouTube 频道 {youtube_channel_id} 的通知", ephemeral=True)

# ========== 计数器 ==========
@bot.tree.command(name="add_counter", description="添加计数器")
@admin_only()
async def add_counter(interaction: discord.Interaction, counter_type: str, channel: discord.TextChannel, template: str):
    c.execute("INSERT INTO counters (guild_id, counter_type, channel_id, message_template) VALUES (?, ?, ?, ?)",
              (str(interaction.guild.id), counter_type, str(channel.id), template))
    conn.commit()
    await interaction.response.send_message(f"✅ 已添加 {counter_type} 计数器", ephemeral=True)

# ========== 欢迎消息 ==========
@bot.tree.command(name="set_welcome", description="设置欢迎消息")
@admin_only()
async def set_welcome(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    c.execute("INSERT OR REPLACE INTO welcome_settings (guild_id, channel_id, message) VALUES (?, ?, ?)",
              (str(interaction.guild.id), str(channel.id), message))
    conn.commit()
    await interaction.response.send_message(f"✅ 欢迎消息已设置到 {channel.mention}", ephemeral=True)

# ========== 日志设置 ==========
@bot.tree.command(name="set_log_channel", description="设置消息日志频道")
@admin_only()
async def set_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    c.execute("INSERT OR REPLACE INTO log_settings (guild_id, message_log_channel) VALUES (?, ?)",
              (str(interaction.guild.id), str(channel.id)))
    conn.commit()
    await interaction.response.send_message(f"✅ 日志频道已设置为 {channel.mention}", ephemeral=True)

@bot.tree.command(name="set_voice_log", description="设置语音日志频道")
@admin_only()
async def set_voice_log(interaction: discord.Interaction, channel: discord.TextChannel):
    c.execute("INSERT OR REPLACE INTO log_settings (guild_id, voice_log_channel) VALUES (?, ?)",
              (str(interaction.guild.id), str(channel.id)))
    conn.commit()
    await interaction.response.send_message(f"✅ 语音日志频道已设置为 {channel.mention}", ephemeral=True)

# ========== 管理命令 ==========
@bot.tree.command(name="kick", description="踢出用户")
@admin_only()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"✅ 已踢出 {member.mention}", ephemeral=True)

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

@bot.tree.command(name="lock", description="锁定频道")
@admin_only()
async def lock(interaction: discord.Interaction, channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await interaction.response.send_message(f"🔒 {channel.mention} 已锁定", ephemeral=True)

@bot.tree.command(name="unlock", description="解锁频道")
@admin_only()
async def unlock(interaction: discord.Interaction, channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=True)
    await interaction.response.send_message(f"🔓 {channel.mention} 已解锁", ephemeral=True)

# ========== 权限管理命令 ==========
@bot.tree.command(name="add_admin_role", description="添加有管理权限的角色（仅群主）")
@is_owner()
async def add_admin_role(interaction: discord.Interaction, role: discord.Role):
    c.execute("INSERT OR REPLACE INTO command_permissions (guild_id, command_name, role_id) VALUES (?, ?, ?)",
              (str(interaction.guild.id), "admin", str(role.id)))
    conn.commit()
    await interaction.response.send_message(f"✅ 角色 {role.mention} 已获得管理权限", ephemeral=True)

@bot.tree.command(name="remove_admin_role", description="移除角色的管理权限（仅群主）")
@is_owner()
async def remove_admin_role(interaction: discord.Interaction, role: discord.Role):
    c.execute("DELETE FROM command_permissions WHERE guild_id=? AND command_name=? AND role_id=?", 
              (str(interaction.guild.id), "admin", str(role.id)))
    conn.commit()
    await interaction.response.send_message(f"✅ 角色 {role.mention} 的管理权限已移除", ephemeral=True)

@bot.tree.command(name="add_admin_user", description="添加有管理权限的用户（仅群主）")
@is_owner()
async def add_admin_user(interaction: discord.Interaction, user: discord.User):
    c.execute("INSERT OR REPLACE INTO command_permissions (guild_id, command_name, user_id) VALUES (?, ?, ?)",
              (str(interaction.guild.id), "admin", str(user.id)))
    conn.commit()
    await interaction.response.send_message(f"✅ 用户 {user.mention} 已获得管理权限", ephemeral=True)

@bot.tree.command(name="remove_admin_user", description="移除用户的管理权限（仅群主）")
@is_owner()
async def remove_admin_user(interaction: discord.Interaction, user: discord.User):
    c.execute("DELETE FROM command_permissions WHERE guild_id=? AND command_name=? AND user_id=?", 
              (str(interaction.guild.id), "admin", str(user.id)))
    conn.commit()
    await interaction.response.send_message(f"✅ 用户 {user.mention} 的管理权限已移除", ephemeral=True)

@bot.tree.command(name="list_admins", description="查看有管理权限的角色和用户（仅群主）")
@is_owner()
async def list_admins(interaction: discord.Interaction):
    c.execute("SELECT role_id FROM command_permissions WHERE guild_id=? AND command_name=?", (str(interaction.guild.id), "admin"))
    roles = c.fetchall()
    c.execute("SELECT user_id FROM command_permissions WHERE guild_id=? AND command_name=?", (str(interaction.guild.id), "admin"))
    users = c.fetchall()
    
    msg = "**👑 管理权限列表**\n"
    if roles:
        msg += "\n**角色：**\n"
        for role_id in roles:
            role = interaction.guild.get_role(int(role_id[0]))
            if role:
                msg += f"• {role.mention}\n"
    if users:
        msg += "\n**用户：**\n"
        for user_id in users:
            user = await bot.fetch_user(int(user_id[0]))
            if user:
                msg += f"• {user.mention}\n"
    if not roles and not users:
        msg += "\n暂无管理权限，只有群主有权限"
    
    await interaction.response.send_message(msg, ephemeral=True)

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
