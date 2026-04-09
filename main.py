import discord
from discord.ext import commands
import asyncio
from config import TOKEN, logger
from database import init_db
from tasks.counter_updater import start_counter_updater

# 设置 intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


async def load_extensions():
    """加载所有扩展模块"""
    # 加载事件模块
    await bot.load_extension("events.message_handler")
    await bot.load_extension("events.voice_handler")
    await bot.load_extension("events.member_handler")

    # 加载命令模块
    await bot.load_extension("cogs.level")
    await bot.load_extension("cogs.reaction_role")
    await bot.load_extension("cogs.counter")
    await bot.load_extension("cogs.logs")
    await bot.load_extension("cogs.admin")
    await bot.load_extension("cogs.info")

    logger.info("所有模块加载完成")


@bot.event
async def on_ready():
    await load_extensions()
    await bot.tree.sync()
    logger.info(f"✅ Bot已登录: {bot.user}")
    logger.info("已同步斜杠命令")
    
    # 启动计数器自动更新任务
    bot.loop.create_task(start_counter_updater(bot))


if __name__ == "__main__":
    init_db()
    bot.run(TOKEN)
