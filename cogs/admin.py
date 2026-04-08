import discord
from discord import app_commands
from discord.ext import commands
from database import db_get_log_channel
from config import logger


class AdminCommands(commands.GroupCog, name="admin"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="kick", description="踢出用户")
    @app_commands.default_permissions(administrator=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "无"):
        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(f"✅ 已踢出 {member.mention}", ephemeral=True)
            ch_id = db_get_log_channel(str(interaction.guild.id), "mod_log_channel")
            if ch_id:
                ch = interaction.guild.get_channel(int(ch_id))
                if ch:
                    embed = discord.Embed(
                        title="👢 用户被踢出",
                        description=f"**用户:** {member.mention}\n**管理员:** {interaction.user.mention}\n**原因:** {reason}",
                        color=discord.Color.orange(),
                        timestamp=datetime.now()
                    )
                    await ch.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 权限不足", ephemeral=True)

    @app_commands.command(name="ban", description="封禁用户")
    @app_commands.default_permissions(administrator=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "无"):
        try:
            await member.ban(reason=reason)
            await interaction.response.send_message(f"✅ 已封禁 {member.mention}", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 权限不足", ephemeral=True)

    @app_commands.command(name="clear", description="清除消息（最多100条）")
    @app_commands.default_permissions(administrator=True)
    async def clear(self, interaction: discord.Interaction, amount: int):
        amount = max(1, min(amount, 100))
        await interaction.channel.purge(limit=amount)
        await interaction.response.send_message(f"✅ 已清除 {amount} 条消息", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdminCommands(bot))
