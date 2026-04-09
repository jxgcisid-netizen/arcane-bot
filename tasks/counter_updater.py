import asyncio
import discord
from database import get_conn
from config import logger

async def start_counter_updater(bot):
    """启动计数器自动更新任务"""
    while True:
        await asyncio.sleep(45)  # 每30秒更新一次
        
        try:
            with get_conn() as conn:
                # 获取所有服务器的所有计数器
                counters = conn.execute(
                    "SELECT guild_id, counter_type, channel_id, message_template FROM counters"
                ).fetchall()
            
            for counter in counters:
                try:
                    guild = bot.get_guild(int(counter["guild_id"]))
                    if not guild:
                        continue
                    
                    channel = guild.get_channel(int(counter["channel_id"]))
                    if not channel:
                        continue
                    
                    counter_type = counter["counter_type"]
                    new_value = 0
                    
                    # 根据类型计算新数值
                    if counter_type == "members":
                        new_value = guild.member_count
                    elif counter_type == "online":
                        # 在线人数（包括各种状态）
                        online = sum(1 for member in guild.members if member.status != discord.Status.offline)
                        new_value = online
                    elif counter_type == "bots":
                        bots = sum(1 for member in guild.members if member.bot)
                        new_value = bots
                    elif counter_type == "messages":
                        # 消息总数跳过自动更新，让管理员手动更新
                        continue
                    else:
                        continue
                    
                    # 更新数据库中的值
                    conn.execute(
                        "UPDATE counters SET current_value=? WHERE guild_id=? AND counter_type=?",
                        (new_value, counter["guild_id"], counter_type)
                    )
                    conn.commit()
                    
                    # 发送/更新消息
                    msg_template = counter["message_template"]
                    msg_content = msg_template.replace("{value}", str(new_value))
                    
                    # 查找之前的消息
                    found = False
                    async for m in channel.history(limit=20):
                        if m.author == bot.user and counter_type in m.content:
                            await m.edit(content=msg_content)
                            found = True
                            break
                    
                    if not found:
                        await channel.send(msg_content)
                        
                except Exception as e:
                    logger.error(f"更新计数器失败 {counter['counter_type']}: {e}")
                    
        except Exception as e:
            logger.error(f"计数器更新循环错误: {e}")
