import discord
from discord import app_commands
from discord.ext import commands
from database import db_set_reaction_role, db_delete_reaction_role, db_get_reaction_role
from config import logger


class ReactionRoleCommands(commands.GroupCog, name="reaction"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="add", description="添加反应角色")
    @app_commands.default_permissions(administrator=True)
    async def add_reaction_role(self, interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
        db_set_reaction_role(interaction.guild.id, message_id, emoji, role.id)
        await interaction.response.send_message(f"✅ {emoji} → {role.mention}", ephemeral=True)

    @app_commands.command(name="remove", description="移除反应角色")
    @app_commands.default_permissions(administrator=True)
    async def remove_reaction_role(self, interaction: discord.Interaction, message_id: str, emoji: str):
        db_delete_reaction_role(interaction.guild.id, message_id, emoji)
        await interaction.response.send_message("✅ 反应角色已移除", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ReactionRoleCommands(bot))

    @bot.event
    async def on_raw_reaction_add(payload):
        if payload.user_id == bot.user.id:
            return
        row = db_get_reaction_role(payload.guild_id, payload.message_id, payload.emoji.name)
        if row:
            guild = bot.get_guild(payload.guild_id)
            role = guild.get_role(int(row["role_id"]))
            member = guild.get_member(payload.user_id)
            if role and member:
                try:
                    await member.add_roles(role)
                except:
                    pass

    @bot.event
    async def on_raw_reaction_remove(payload):
        row = db_get_reaction_role(payload.guild_id, payload.message_id, payload.emoji.name)
        if row:
            guild = bot.get_guild(payload.guild_id)
            role = guild.get_role(int(row["role_id"]))
            member = guild.get_member(payload.user_id)
            if role and member:
                try:
                    await member.remove_roles(role)
                except:
                    pass
