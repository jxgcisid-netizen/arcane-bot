import discord
from discord import app_commands
from discord.ext import commands
from database import db_set_log_channel, db_get_log_channel
from config import logger


class LogCommands(commands.GroupCog, name="log"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="set_message", description="设置消息日志频道")
    @app_commands.default_permissions(administrator=True)
    async def set_message_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        db_set_log_channel(interaction.guild.id, "message_log_channel", channel.id)
        await interaction.response.send_message(f"✅ 消息日志 → {channel.mention}", ephemeral=True)

    @app_commands.command(name="set_voice", description="设置语音日志频道")
    @app_commands.default_permissions(administrator=True)
    async def set_voice_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        db_set_log_channel(interaction.guild.id, "voice_log_channel", channel.id)
        await interaction.response.send_message(f"✅ 语音日志 → {channel.mention}", ephemeral=True)

    @app_commands.command(name="set_mod", description="设置管理日志频道")
    @app_commands.default_permissions(administrator=True)
    async def set_mod_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        db_set_log_channel(interaction.guild.id, "mod_log_channel", channel.id)
        await interaction.response.send_message(f"✅ 管理日志 → {channel.mention}", ephemeral=True)

    @app_commands.command(name="set_welcome", description="设置欢迎/告别频道")
    @app_commands.default_permissions(administrator=True)
    async def set_welcome_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        from database import db_set_welcome_channel
        db_set_welcome_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(f"✅ 欢迎/告别频道 → {channel.mention}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(LogCommands(bot))

    @bot.event
    async def on_message_delete(message):
        if message.author.bot:
            return
        ch_id = db_get_log_channel(str(message.guild.id), "message_log_channel")
        if ch_id:
            ch = message.guild.get_channel(int(ch_id))
            if ch:
                embed = discord.Embed(
                    title="🗑️ 消息被删除",
                    description=f"**频道:** {message.channel.mention}\n**用户:** {message.author.mention}\n**内容:** {message.content[:500]}",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                await ch.send(embed=embed)

    @bot.event
    async def on_message_edit(before, after):
        if before.author.bot or before.content == after.content:
            return
        ch_id = db_get_log_channel(str(before.guild.id), "message_log_channel")
        if ch_id:
            ch = before.guild.get_channel(int(ch_id))
            if ch:
                embed = discord.Embed(
                    title="✏️ 消息被编辑",
                    description=f"**频道:** {before.channel.mention}\n**用户:** {before.author.mention}\n**之前:** {before.content[:300]}\n**之后:** {after.content[:300]}",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                await ch.send(embed=embed)
