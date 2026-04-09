import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from database import db_set_counter, db_update_counter_value, db_delete_counter, db_get_counter, get_conn
from config import logger

# 计数器类型选项
COUNTER_CHOICES = [
    app_commands.Choice(name="👥 成员数量", value="members"),
    app_commands.Choice(name="🟢 在线人数", value="online"),
    app_commands.Choice(name="🤖 Bot数量", value="bots"),
    app_commands.Choice(name="📝 消息总数", value="messages"),
]


class CounterCommands(commands.GroupCog, name="counter"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="add", description="添加计数器")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        counter_type="计数器类型",
        channel="发送到哪个频道",
        message_template="消息模板，用 {value} 代表数值，例如：👥 成员数量：{value}"
    )
    @app_commands.choices(counter_type=COUNTER_CHOICES)
    async def add_counter(self, interaction: discord.Interaction,
                          counter_type: app_commands.Choice[str],
                          channel: discord.TextChannel,
                          message_template: str):
        """添加一个计数器"""
        actual_type = counter_type.value
        with get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO counters (guild_id, counter_type, channel_id, message_template) VALUES (?,?,?,?)",
                (str(interaction.guild.id), actual_type, str(channel.id), message_template)
            )
            conn.commit()
        await interaction.response.send_message(
            f"✅ 计数器 `{counter_type.name}` 已添加到 {channel.mention}", ephemeral=True
        )

    @app_commands.command(name="update", description="更新计数器数值")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(counter_type="要更新的计数器", value="新的数值")
    @app_commands.choices(counter_type=COUNTER_CHOICES)
    async def update_counter(self, interaction: discord.Interaction,
                             counter_type: app_commands.Choice[str],
                             value: int):
        """手动更新计数器的数值"""
        actual_type = counter_type.value
        with get_conn() as conn:
            conn.execute(
                "UPDATE counters SET current_value=? WHERE guild_id=? AND counter_type=?",
                (value, str(interaction.guild.id), actual_type)
            )
            conn.commit()
            row = conn.execute(
                "SELECT channel_id, message_template FROM counters WHERE guild_id=? AND counter_type=?",
                (str(interaction.guild.id), actual_type)
            ).fetchone()

        if row:
            ch = interaction.guild.get_channel(int(row["channel_id"]))
            msg = row["message_template"].replace("{value}", str(value))
            if ch:
                async for m in ch.history(limit=10):
                    if m.author == self.bot.user and actual_type in m.content:
                        await m.edit(content=msg)
                        break
                else:
                    await ch.send(msg)

        await interaction.response.send_message(f"✅ 计数器 `{counter_type.name}` 已更新为 {value}", ephemeral=True)

    @app_commands.command(name="remove", description="移除计数器")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(counter_type="要移除的计数器")
    @app_commands.choices(counter_type=COUNTER_CHOICES)
    async def remove_counter(self, interaction: discord.Interaction,
                             counter_type: app_commands.Choice[str]):
        """移除一个计数器"""
        actual_type = counter_type.value
        with get_conn() as conn:
            conn.execute(
                "DELETE FROM counters WHERE guild_id=? AND counter_type=?",
                (str(interaction.guild.id), actual_type)
            )
            conn.commit()
        await interaction.response.send_message(f"✅ 计数器 `{counter_type.name}` 已移除", ephemeral=True)


async def setup(bot):
    await bot.add_cog(CounterCommands(bot))
