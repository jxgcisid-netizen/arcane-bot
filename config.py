import os
import logging

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

# 字体路径
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# 颜色定义
TEAL = (65, 183, 183)
TEAL_DARK = (45, 130, 130)
TEAL_DIM = (45, 100, 100)
RED = (200, 60, 60)
RED_DARK = (140, 35, 35)
RED_DIM = (100, 30, 30)
GOLD = (255, 215, 0)
SILVER = (192, 192, 192)
BRONZE = (205, 127, 50)

# 排行榜颜色
RANK_COLORS = {
    1: GOLD,
    2: SILVER,
    3: BRONZE,
}
RANK_BG = {
    1: (55, 48, 10),
    2: (42, 47, 58),
    3: (52, 32, 12),
}
RANK_BAR = {
    1: (255, 200, 0),
    2: (180, 190, 210),
    3: (200, 110, 50),
}

# ==================== 字体工具函数 ====================
from PIL import ImageFont

def get_font(size=36, bold=True):
    """
    获取指定大小的字体对象
    - size: 字体大小
    - bold: True 用粗体，False 用常规体
    """
    font_path = FONT_BOLD if bold else FONT_REGULAR
    
    try:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
        else:
            logger.warning(f"字体文件不存在: {font_path}，使用默认字体")
            return ImageFont.load_default()
    except Exception as e:
        logger.error(f"加载字体失败: {e}，使用默认字体")
        return ImageFont.load_default()
