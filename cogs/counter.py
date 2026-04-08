import discord
from discord import app_commands
from discord.ext import commands
from database import db_set_counter, db_update_counter_value, db_delete_counter, db_get_counter


class CounterCommands(commands.GroupCog, name="counter"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="add", description="添加计数器")
    @app_commands.default_permissions(administrator=True)
    async def add_counter(self, interaction: discord.Interaction, counter_type: str, channel: discord.TextChannel, message_template: str):
        db_set_counter(interaction.guild.id, counter_type, channel.id, message_template)
        await interaction.response.send_message(f"✅ 计数器 `{counter_type}` 已添加", ephemeral=True)

    @app_commands.command(name="update", description="更新计数器数值")
    @app_commands.default_permissions(administrator=True)
    async def update_counter(self, interaction: discord.Interaction, counter_type: str, value: int):
        db_update_counter_value(interaction.guild.id, counter_type, value)
        counter = db_get_counter(interaction.guild.id, counter_type)
        if counter:
            ch = interaction.guild.get_channel(int(counter["channel_id"]))
            msg = counter["message_template"].replace("{value}", str(value))
            if ch:
                async for m in ch.history(limit=10):
                    if m.author == self.bot.user and counter_type in m.content:
                        await m.edit(content=msg)
                        break
                else:
                    await ch.send(msg)
        await interaction.response.send_message("✅ 计数器已更新", ephemeral=True)

    @app_commands.command(name="remove", description="移除计数器")
    @app_commands.default_permissions(administrator=True)
    async def remove_counter(self, interaction: discord.Interaction, counter_type: str):
        db_delete_counter(interaction.guild.id, counter_type)
        await interaction.response.send_message(f"✅ 计数器 `{counter_type}` 已移除", ephemeral=True)


async def setup(bot):
    await bot.add_cog(CounterCommands(bot))
