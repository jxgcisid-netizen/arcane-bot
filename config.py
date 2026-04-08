import os
import logging
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

# 候选字体路径（按优先级排序）
FONT_CANDIDATES = [
    # Linux DejaVu（你服务器上的）
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # Linux Noto（中文字体支持更好）
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    # Windows
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/consolab.ttf",
    "C:/Windows/Fonts/consola.ttf",
    # macOS
    "/System/Library/Fonts/Helvetica.ttc",
]

def find_font(bold=True):
    """自动查找可用的粗体或常规字体"""
    candidates = []
    for path in FONT_CANDIDATES:
        if bold and "Bold" in path or "bd" in path or "Helvetica" in path:
            candidates.append(path)
        elif not bold and ("Sans.ttf" in path or "regular" in path or "arial.ttf" in path):
            candidates.append(path)
    
    # 如果没找到，用所有候选
    if not candidates:
        candidates = FONT_CANDIDATES
    
    for path in candidates:
        if os.path.exists(path):
            logger.info(f"找到字体: {path}")
            return path
    
    logger.warning("未找到任何字体，将使用默认字体")
    return None

# 检测并设置字体路径
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

# ==================== 字体工具函数（带缓存和自适应） ====================

_font_cache = {}

def get_font(size=36, bold=True):
    """
    获取指定大小的字体对象（自动适应系统可用字体）
    - size: 字体大小
    - bold: True 用粗体，False 用常规体
    """
    cache_key = f"{bold}_{size}"
    
    if cache_key in _font_cache:
        return _font_cache[cache_key]
    
    font_path = FONT_BOLD if bold else FONT_REGULAR
    
    if font_path is None:
        logger.warning("无可用字体，使用默认字体")
        return ImageFont.load_default()
    
    try:
        font = ImageFont.truetype(font_path, size)
        _font_cache[cache_key] = font
        return font
    except Exception as e:
        logger.error(f"加载字体失败 {font_path}: {e}")
        return ImageFont.load_default()


def get_optimal_font_size(text, max_width, initial_size=40, bold=True):
    """
    自动计算最佳字体大小，使文字不超出最大宽度
    - text: 要显示的文字
    - max_width: 最大允许宽度（像素）
    - initial_size: 初始字体大小
    - bold: 是否使用粗体
    """
    size = initial_size
    font = get_font(size, bold)
    
    try:
        bbox = font.getbbox(text)
        text_width = bbox[2] - bbox[0]
    except:
        text_width = len(text) * size // 2
    
    # 如果文字太宽，逐步减小字体
    while text_width > max_width and size > 16:
        size -= 2
        font = get_font(size, bold)
        try:
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
        except:
            text_width = len(text) * size // 2
    
    # 如果文字太窄，可以适当增大（可选）
    while text_width < max_width * 0.7 and size < 60:
        size += 2
        font = get_font(size, bold)
        try:
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
        except:
            text_width = len(text) * size // 2
    
    return font
