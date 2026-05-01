import os
import logging
import platform
import discord
from discord.ext import commands
from PIL import ImageFont

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("DiscordBot")

# ==================== 令牌 ====================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    logger.error("请设置 DISCORD_TOKEN 环境变量")
    exit(1)

# ==================== 字体路径 ====================
system = platform.system()
if system == "Windows":
    FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
    FONT_REGULAR = "C:/Windows/Fonts/arial.ttf"
elif system == "Darwin":
    FONT_BOLD = "/System/Library/Fonts/Helvetica.ttc"
    FONT_REGULAR = "/System/Library/Fonts/Helvetica.ttc"
else:
    FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# ==================== 颜色 ====================
TEAL = (65, 183, 183)
TEAL_DARK = (45, 130, 130)
TEAL_DIM = (45, 100, 100)
RED = (200, 60, 60)
RED_DARK = (140, 35, 35)
RED_DIM = (100, 30, 30)
GOLD = (255, 215, 0)
SILVER = (192, 192, 192)
BRONZE = (205, 127, 50)
RANK_COLORS = {1: GOLD, 2: SILVER, 3: BRONZE}
RANK_BG = {1: (55, 48, 10), 2: (42, 47, 58), 3: (52, 32, 12)}
RANK_BAR = {1: (255, 200, 0), 2: (180, 190, 210), 3: (200, 110, 50)}

# ==================== 字体缓存 ====================
_font_cache = {}

def get_font(size, bold=True):
    cache_key = f"{bold}_{size}"
    if cache_key in _font_cache:
        return _font_cache[cache_key]

    font_path = FONT_BOLD if bold else FONT_REGULAR
    try:
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, size)
            _font_cache[cache_key] = font
            return font
        logger.warning(f"字体不存在: {font_path}")
    except Exception as e:
        logger.error(f"加载字体失败: {e}")
    return ImageFont.load_default()


# ==================== Bot初始化 ====================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


@bot.event
async def on_ready():
    logger.info(f"✅ 已登录: {bot.user}")
    try:
        await bot.tree.sync()
        logger.info("✅ 斜杠命令已同步")
    except Exception as e:
        logger.error(f"同步命令失败: {e}")


async def load_modules():
    """加载所有模块"""
    import events as ev
    import cogs as cog
    import tasks as tsk

    await ev.setup(bot)
    await cog.setup(bot)
    bot.loop.create_task(tsk.start_counter_updater(bot))
    logger.info("所有模块加载完成")

@bot.command(name="dump_db")
@commands.has_permissions(administrator=True)
async def dump_database(ctx):
    """将数据库文件转为文本发送"""
    import base64
    with open("/app/data/bot_data.db", "rb") as f:
        data = base64.b64encode(f.read()).decode()
    # 分段发送（Discord 有 2000 字限制）
    for i in range(0, len(data), 1800):
        await ctx.send(data[i:i+1800])
    await ctx.send("✅ 导出完成")
    
@bot.event
async def setup_hook():
    await load_modules()


if __name__ == "__main__":
    from database import init_db
    init_db()
    bot.run(TOKEN)
