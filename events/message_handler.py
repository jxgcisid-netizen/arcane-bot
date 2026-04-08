import random
from datetime import datetime
from discord.ext import commands
from config import logger
from database import db_get_guild_settings, db_get_user, db_update_user, db_get_level_role, process_level_up, xp_needed

_xp_cooldown: dict[str, datetime] = {}


async def setup(bot):
    @bot.event
    async def on_message(message):
        if message.author.bot or not message.guild:
            return

        guild_id = str(message.guild.id)
        user_id = str(message.author.id)
        key = f"{guild_id}:{user_id}"
        now = datetime.now()

        # XP 冷却：60 秒
        if key in _xp_cooldown and (now - _xp_cooldown[key]).total_seconds() < 60:
            await bot.process_commands(message)
            return
        _xp_cooldown[key] = now

        settings = db_get_guild_settings(guild_id)
        user_data = db_get_user(guild_id, user_id)
        user_data["xp"] += int(random.randint(15, 25) * settings["xp_rate"])
        user_data, levels_gained = process_level_up(user_data)

        if levels_gained > 0:
            role_id = db_get_level_role(guild_id, user_data["level"])
            if role_id:
                role = message.guild.get_role(int(role_id))
                if role:
                    try:
                        await message.author.add_roles(role)
                    except:
                        pass
            embed = discord.Embed(
                title="🎉 等级提升！",
                description=f"{message.author.mention} 升到了 **{user_data['level']} 级**！",
                color=discord.Color.gold()
            )
            await message.channel.send(embed=embed, delete_after=10)

        db_update_user(guild_id, user_id, user_data)
        await bot.process_commands(message)
