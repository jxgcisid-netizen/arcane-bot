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

# ==================== 自动检测字体路径 ====================

system = platform.system()

FONT_CANDIDATES = []

if system == "Windows":
    FONT_CANDIDATES = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/consolab.ttf",
        "C:/Windows/Fonts/consola.ttf",
    ]
elif system == "Darwin":
    FONT_CANDIDATES = [
        "/System/Library/Fonts/Helvetica.ttc",
    ]
else:
    FONT_CANDIDATES = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    ]

def find_font(bold=True):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            if bold and ("Bold" in path or "bd" in path):
                logger.info(f"找到粗体字体: {path}")
                return path
            elif not bold and ("Sans.ttf" in path or "arial.ttf" in path or "NotoSansCJK" in path):
                logger.info(f"找到常规字体: {path}")
                return path
    # 如果没找到粗体，返回第一个存在的
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            logger.info(f"找到备用字体: {path}")
            return path
    logger.warning("未找到任何字体")
    return None

FONT_BOLD = find_font(bold=True)
FONT_REGULAR = find_font(bold=False)

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

def get_font(size=36, bold=True):
    """
    获取指定大小的字体对象
    支持两种调用方式：
    - get_font(36, True)      # 标准方式
    - get_font("bold", 36)    # 兼容旧代码
    """
    # 兼容旧调用方式
    if isinstance(size, str):
        # 第一个参数是字符串（如 "bold"），第二个是大小
        font_type = size
        size = bold if isinstance(bold, int) else 36
        bold = (font_type == "bold")
    
    # 确保 size 是整数
    if not isinstance(size, int):
        size = 36
    
    cache_key = f"{bold}_{size}"
    
    if cache_key in _font_cache:
        return _font_cache[cache_key]
    
    font_path = FONT_BOLD if bold else FONT_REGULAR
    
    if font_path is None:
        return ImageFont.load_default()
    
    try:
        font = ImageFont.truetype(font_path, size)
        _font_cache[cache_key] = font
        return font
    except Exception as e:
        logger.error(f"加载字体失败: {e}")
        return ImageFont.load_default()


def get_optimal_font(text, max_width, max_height=None, initial_size=40, bold=True):
    """自动计算最佳字体大小"""
    size = initial_size
    
    while size > 16:
        font = get_font(size, bold)
        try:
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
            if max_height:
                text_height = bbox[3] - bbox[1]
        except:
            text_width = len(text) * size // 2
            text_height = size
        
        if text_width <= max_width:
            if max_height is None or text_height <= max_height:
                return font, size
        
        size -= 2
    
    return get_font(16, bold), 16
