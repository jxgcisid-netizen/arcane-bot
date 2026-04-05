import discord
from discord.ext import commands
import json
import os
from datetime import datetime

# 配置
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", 0))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 等级数据存储（简化版，生产环境用数据库）
levels = {}

def save_levels():
    with open("levels.json", "w") as f:
        json.dump(levels, f)

def load_levels():
    global levels
    if os.path.exists("levels.json"):
        with open("levels.json", "r") as f:
            levels = json.load(f)

@bot.event
async def on_ready():
    load_levels()
    print(f"✅ {bot.user} 已上线！")
    print(f"已连接 {len(bot.guilds)} 个服务器")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    # 等级系统
    user_id = str(message.author.id)
    if user_id not in levels:
        levels[user_id] = {"xp": 0, "level": 1}
    
    levels[user_id]["xp"] += 1
    
    # 每 50 XP 升一级
    xp_needed = levels[user_id]["level"] * 50
    if levels[user_id]["xp"] >= xp_needed:
        levels[user_id]["level"] += 1
        levels[user_id]["xp"] = 0
        await message.channel.send(f"🎉 {message.author.mention} 升到 {levels[user_id]['level']} 级！")
        save_levels()
    
    save_levels()
    await bot.process_commands(message)

# 等级命令
@bot.command()
async def rank(ctx):
    user_id = str(ctx.author.id)
    if user_id not in levels:
        levels[user_id] = {"xp": 0, "level": 1}
    embed = discord.Embed(
        title=f"{ctx.author.name} 的等级",
        description=f"等级: {levels[user_id]['level']}\n经验: {levels[user_id]['xp']}/{levels[user_id]['level'] * 50}",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

# 排行榜
@bot.command()
async def leaderboard(ctx):
    sorted_users = sorted(levels.items(), key=lambda x: x[1]["level"], reverse=True)[:10]
    embed = discord.Embed(title="🏆 等级排行榜", color=discord.Color.gold())
    for i, (user_id, data) in enumerate(sorted_users, 1):
        user = await bot.fetch_user(int(user_id))
        embed.add_field(name=f"{i}. {user.name}", value=f"Lv.{data['level']}", inline=False)
    await ctx.send(embed=embed)

# 欢迎消息
@bot.event
async def on_member_join(member):
    channel = member.guild.system_channel
    if channel:
        embed = discord.Embed(
            title="👋 欢迎！",
            description=f"欢迎 {member.mention} 加入服务器！",
            color=discord.Color.green()
        )
        await channel.send(embed=embed)

# 管理员命令
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

bot.run(TOKEN)
