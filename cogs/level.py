import discord
from discord import app_commands
from discord.ext import commands
from database import db_get_user, db_get_rank, db_set_level_role, xp_needed
from utils.rank_card import create_rank_card
from utils.leaderboard_card import create_leaderboard_card
from config import logger


class LevelCommands(commands.GroupCog, name="level"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="rank", description="查看等级卡片")
    async def slash_rank(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.defer()
        member = member or interaction.user
        user_data = db_get_user(interaction.guild.id, member.id)
        rank_pos = db_get_rank(interaction.guild.id, member.id)
        needed = xp_needed(user_data["level"])

        try:
            buf = await create_rank_card(member, user_data["level"], user_data["xp"], needed, rank_pos)
            await interaction.followup.send(file=discord.File(buf, filename="rank.png"))
        except Exception as e:
            logger.error(f"等级卡片生成失败: {e}")
            embed = discord.Embed(
                title=f"📊 {member.display_name} 的等级",
                description=f"等级：{user_data['level']}\nXP：{user_data['xp']}/{needed}\n排名：#{rank_pos}",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="leaderboard", description="查看排行榜")
    @app_commands.describe(mode="排行类型：xp=打字  voice=语音")
    @app_commands.choices(mode=[
        app_commands.Choice(name="打字 XP", value="xp"),
        app_commands.Choice(name="语音 VP", value="voice"),
    ])
    async def slash_leaderboard(self, interaction: discord.Interaction, mode: str = "xp"):
        await interaction.response.defer()
        from database import db_get_leaderboard
        top_data = db_get_leaderboard(interaction.guild.id, mode=mode)

        if not top_data:
            await interaction.followup.send("📊 暂无数据")
            return

        top_users = []
        for row in top_data:
            try:
                member = await interaction.guild.fetch_member(int(row["user_id"]))
            except:
                try:
                    member = await self.bot.fetch_user(int(row["user_id"]))
                except:
                    continue
            top_users.append({
                "member": member,
                "name": member.display_name,
                "level": row["level"],
                "xp": row["xp"],
                "voice_xp": row["voice_xp"],
                "needed_xp": xp_needed(row["level"]),
            })

        if not top_users:
            await interaction.followup.send("📊 暂无数据")
            return

        try:
            buf = await create_leaderboard_card(interaction.guild, top_users, mode=mode)
            await interaction.followup.send(file=discord.File(buf, filename="leaderboard.png"))
        except Exception as e:
            logger.error(f"排行榜卡片生成失败: {e}")
            desc = ""
            for i, u in enumerate(top_users, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                val = u["xp"] if mode == "xp" else u["voice_xp"]
                desc += f"{medal} **{u['name']}** — Lv.{u['level']} ({val} {'XP' if mode=='xp' else 'VP'})\n"
            embed = discord.Embed(title="🏆 排行榜", description=desc, color=discord.Color.gold())
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="add_level_role", description="设置等级奖励角色")
    @app_commands.default_permissions(administrator=True)
    async def add_level_role(self, interaction: discord.Interaction, level: int, role: discord.Role):
        db_set_level_role(interaction.guild.id, level, role.id)
        await interaction.response.send_message(f"✅ 等级 {level} 奖励角色 → {role.mention}", ephemeral=True)

    @app_commands.command(name="set_xp_rate", description="设置经验倍率")
    @app_commands.default_permissions(administrator=True)
    async def set_xp_rate(self, interaction: discord.Interaction, rate: float):
        from database import db_update_guild_setting
        rate = max(0.1, min(rate, 10.0))
        db_update_guild_setting(interaction.guild.id, "xp_rate", rate)
        await interaction.response.send_message(f"✅ 经验倍率 → {rate}x", ephemeral=True)


async def setup(bot):
    await bot.add_cog(LevelCommands(bot))
