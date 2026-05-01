import asyncio
import discord
from database import get_conn, release_conn
from main import logger

async def start_counter_updater(bot):
    while True:
        await asyncio.sleep(45)
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT guild_id, counter_type, channel_id, message_template FROM counters")
            counters = cur.fetchall()
            cur.close()
            release_conn(conn)

            for c in counters:
                try:
                    guild = bot.get_guild(int(c[0]))
                    if not guild:
                        continue
                    ch = guild.get_channel(int(c[2]))
                    if not ch:
                        continue

                    ct = c[1]
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

                    conn2 = get_conn()
                    cur2 = conn2.cursor()
                    cur2.execute("UPDATE counters SET current_value=%s WHERE guild_id=%s AND counter_type=%s", (val, c[0], ct))
                    conn2.commit()
                    cur2.close()
                    release_conn(conn2)

                    msg = c[3].replace("{value}", str(val))
                    found = False
                    async for m in ch.history(limit=20):
                        if m.author == bot.user and ct in m.content:
                            await m.edit(content=msg)
                            found = True
                            break
                    if not found:
                        await ch.send(msg)

                except Exception as e:
                    logger.error(f"计数器 {c[1]} 失败: {e}")

        except Exception as e:
            logger.error(f"计数器循环错误: {e}")
