import discord
from config import logger
from database import db_get_welcome_channel
from utils.welcome_card import create_welcome_card
from utils.goodbye_card import create_goodbye_card


async def setup(bot):
    @bot.event
    async def on_member_join(member):
        ch_id = db_get_welcome_channel(str(member.guild.id))
        if not ch_id:
            return
        ch = member.guild.get_channel(int(ch_id))
        if not ch:
            return
        try:
            buf = await create_welcome_card(member, member.guild.member_count)
            await ch.send(file=discord.File(buf, filename="welcome.png"))
        except Exception as e:
            logger.error(f"欢迎卡片生成失败: {e}")
            embed = discord.Embed(
                title="👋 欢迎加入！",
                description=f"欢迎 {member.mention}！你是第 **{member.guild.member_count}** 位成员",
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await ch.send(embed=embed)

    @bot.event
    async def on_member_remove(member):
        ch_id = db_get_welcome_channel(str(member.guild.id))
        if not ch_id:
            return
        ch = member.guild.get_channel(int(ch_id))
        if not ch:
            return
        try:
            buf = await create_goodbye_card(member, member.guild.member_count)
            await ch.send(file=discord.File(buf, filename="goodbye.png"))
        except Exception as e:
            logger.error(f"告别卡片生成失败: {e}")
            embed = discord.Embed(
                title="👋 再见！",
                description=f"{member.display_name} 离开了，还剩 **{member.guild.member_count}** 位成员",
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await ch.send(embed=embed)
