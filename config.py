import os
import logging
import platform
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

# ==================== Bot 配置 ====================

TOKEN = os.getenv("DISCORD_TOKEN")

# ==================== 字体路径 ====================

system = platform.system()

if system == "Windows":
    FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
    FONT_REGULAR = "C:/Windows/Fonts/arial.ttf"
elif system == "Darwin":
    FONT_BOLD = "/System/Library/Fonts/Helvetica.ttc"
    FONT_REGULAR = "/System/Library/Fonts/Helvetica.ttc"
elif system == "Linux":
    FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

# ==================== 颜色定义 ====================

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

# ==================== 字体工具函数 ====================

_font_cache = {}

def get_font(size, bold=True):
    """获取指定大小的字体对象"""
    cache_key = f"{bold}_{size}"
    
    if cache_key in _font_cache:
        return _font_cache[cache_key]
    
    font_path = FONT_BOLD if bold else FONT_REGULAR
    
    try:
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, size)
            _font_cache[cache_key] = font
            return font
        else:
            logger.warning(f"字体不存在: {font_path}")
            return ImageFont.load_default()
    except Exception as e:
        logger.error(f"加载字体失败: {e}")
        return ImageFont.load_default()
