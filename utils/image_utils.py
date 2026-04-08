import io
import aiohttp
from PIL import Image, ImageDraw
from config import logger
from database import get_cached_avatar, set_cached_avatar


async def fetch_avatar(member, size=256):
    """下载并返回圆形裁剪的头像 Image，带缓存"""
    avatar_url = member.display_avatar.url
    cache_key = f"{member.id}_{avatar_url}_{size}"

    # 检查缓存
    cached = get_cached_avatar(member.id, avatar_url, size)
    if cached:
        return cached

    try:
        url = avatar_url.replace("?size=1024", f"?size={size}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    img = Image.open(io.BytesIO(data)).convert("RGBA")
                    set_cached_avatar(member.id, avatar_url, size, img)
                    return img
    except Exception as e:
        logger.warning(f"头像下载失败 {member.id}: {e}")

    return None


def make_circle_avatar(av_img, size):
    """把头像裁成圆形"""
    av = av_img.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    circle = Image.new("RGBA", (size, size))
    circle.paste(av, (0, 0), av)
    circle.putalpha(mask)
    return circle


def draw_text_with_shadow(draw, xy, text, shadow_color, text_color, font, offset=2):
    """绘制带阴影的文字"""
    x, y = xy
    draw.text((x + offset, y + offset), text, fill=shadow_color, font=font)
    draw.text((x, y), text, fill=text_color, font=font)


def draw_rounded_rect_with_gradient(draw, xy, radius, start_color, end_color):
    """绘制渐变圆角矩形"""
    x1, y1, x2, y2 = xy
    height = y2 - y1
    for y in range(y1, y2):
        t = (y - y1) / height
        r = int(start_color[0] + (end_color[0] - start_color[0]) * t)
        g = int(start_color[1] + (end_color[1] - start_color[1]) * t)
        b = int(start_color[2] + (end_color[2] - start_color[2]) * t)
        draw.line([(x1 + radius, y), (x2 - radius, y)], fill=(r, g, b))
