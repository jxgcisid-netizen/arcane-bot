import io
import aiohttp
from PIL import Image, ImageDraw
from main import logger
from database import get_cached_avatar, set_cached_avatar


async def fetch_avatar(member, size=256):
    """下载头像，带缓存"""
    avatar_url = member.display_avatar.url
    cached = get_cached_avatar(member.id, avatar_url, size)
    if cached:
        return cached

    try:
        url = avatar_url.replace("?size=1024", f"?size={size}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    img = Image.open(io.BytesIO(await resp.read())).convert("RGBA")
                    set_cached_avatar(member.id, avatar_url, size, img)
                    return img
    except Exception as e:
        logger.warning(f"头像下载失败 {member.id}: {e}")
    return None


def make_circle_avatar(av_img, size):
    av = av_img.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    circle = Image.new("RGBA", (size, size))
    circle.paste(av, (0, 0), av)
    circle.putalpha(mask)
    return circle


def draw_text_with_shadow(draw, xy, text, shadow_color, text_color, font, offset=2):
    x, y = xy
    draw.text((x + offset, y + offset), text, fill=shadow_color, font=font)
    draw.text((x, y), text, fill=text_color, font=font)


def draw_rounded_rect_with_gradient(draw, xy, radius, start_color, end_color):
    x1, y1, x2, y2 = xy
    for y in range(y1, y2):
        t = (y - y1) / (y2 - y1)
        r = int(start_color[0] + (end_color[0] - start_color[0]) * t)
        g = int(start_color[1] + (end_color[1] - start_color[1]) * t)
        b = int(start_color[2] + (end_color[2] - start_color[2]) * t)
        draw.line([(x1 + radius, y), (x2 - radius, y)], fill=(r, g, b))
