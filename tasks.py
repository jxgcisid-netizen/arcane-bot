import asyncio
import discord
from database import get_conn
from main import logger

async def start_counter_updater(bot):
    while True:
        await asyncio.sleep(45)
        try:
            with get_conn() as conn:
                counters = conn.execute("SELECT guild_id, counter_type, channel_id, message_template FROM counters").fetchall()

            for c in counters:
                try:
                    guild = bot.get_guild(int(c["guild_id"]))
                    if not guild:
                        continue
                    ch = guild.get_channel(int(c["channel_id"]))
                    if not ch:
                        continue

                    ct = c["counter_type"]
                    if ct == "members":
                        val = guild.member_count
                    elif ct == "online":
                        val = sum(1 for m in guild.members if m.status != discord.Status.offline)
                    elif ct == "bots":
                        val = sum(1 for m in guild.members if m.bot)
                    elif ct == "messages":
                        continue
                    else:
                        continue

                    with get_conn() as conn2:
                        conn2.execute("UPDATE counters SET current_value=? WHERE guild_id=? AND counter_type=?", (val, c["guild_id"], ct))
                        conn2.commit()

                    msg = c["message_template"].replace("{value}", str(val))
                    found = False
                    async for m in ch.history(limit=20):
                        if m.author == bot.user and ct in m.content:
                            await m.edit(content=msg)
                            found = True
                            break
                    if not found:
                        await ch.send(msg)

                except Exception as e:
                    logger.error(f"计数器 {c['counter_type']} 失败: {e}")

        except Exception as e:
            logger.error(f"计数器循环错误: {e}")
