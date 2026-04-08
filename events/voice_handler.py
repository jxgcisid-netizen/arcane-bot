from datetime import datetime
from config import logger
from database import db_get_guild_settings, db_get_user, db_update_user, db_get_log_channel, process_level_up, db_get_level_role

_voice_tracker: dict[int, datetime] = {}


async def setup(bot):
    @bot.event
    async def on_voice_state_update(member, before, after):
        if member.bot:
            return
        guild_id = str(member.guild.id)

        # 加入语音
        if before.channel is None and after.channel is not None:
            _voice_tracker[member.id] = datetime.now()
            ch_id = db_get_log_channel(guild_id, "voice_log_channel")
            if ch_id:
                ch = member.guild.get_channel(int(ch_id))
                if ch:
                    embed = discord.Embed(
                        title="🔊 加入语音",
                        description=f"{member.mention} 加入了 {after.channel.mention}",
                        color=discord.Color.green()
                    )
                    await ch.send(embed=embed)

        # 离开语音
        elif before.channel is not None and after.channel is None:
            join_time = _voice_tracker.pop(member.id, None)
            if join_time:
                duration = (datetime.now() - join_time).total_seconds()
                if duration >= 60:
                    settings = db_get_guild_settings(guild_id)
                    xp_gain = int((duration / 60) * 5 * settings["voice_xp_rate"])
                    user_data = db_get_user(guild_id, member.id)
                    user_data["voice_xp"] += xp_gain
                    user_data["xp"] += xp_gain
                    user_data, levels_gained = process_level_up(user_data)
                    if levels_gained > 0:
                        role_id = db_get_level_role(guild_id, user_data["level"])
                        if role_id:
                            role = member.guild.get_role(int(role_id))
                            if role:
                                try:
                                    await member.add_roles(role)
                                except:
                                    pass
                    db_update_user(guild_id, member.id, user_data)

            ch_id = db_get_log_channel(guild_id, "voice_log_channel")
            if ch_id:
                ch = member.guild.get_channel(int(ch_id))
                if ch:
                    embed = discord.Embed(
                        title="🔇 离开语音",
                        description=f"{member.mention} 离开了 {before.channel.mention}",
                        color=discord.Color.red()
                    )
                    await ch.send(embed=embed)
