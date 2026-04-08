import discord
from discord import app_commands
from discord.ext import commands


class InfoCommands(commands.GroupCog, name="info"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="user", description="查看用户信息")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        av_url = member.avatar.url if member.avatar else member.default_avatar.url
        embed = discord.Embed(title=f"👤 {member.display_name}", color=member.color)
        embed.set_thumbnail(url=av_url)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="加入时间", value=member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "未知", inline=True)
        embed.add_field(name="注册时间", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="最高角色", value=member.top_role.mention, inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description="查看帮助")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🤖 Bot 帮助", color=discord.Color.green())
        embed.add_field(name="📊 等级系统", value="`/level rank` `/level leaderboard`\n`/level add_level_role` `/level set_xp_rate`", inline=False)
        embed.add_field(name="🎭 反应角色", value="`/reaction add` `/reaction remove`", inline=False)
        embed.add_field(name="🔢 计数器", value="`/counter add` `/counter update` `/counter remove`", inline=False)
        embed.add_field(name="📋 日志系统", value="`/log set_message` `/log set_voice` `/log set_mod`", inline=False)
        embed.add_field(name="👋 欢迎/告别", value="`/log set_welcome`", inline=False)
        embed.add_field(name="🔧 管理", value="`/admin kick` `/admin ban` `/admin clear`", inline=False)
        embed.add_field(name="ℹ️ 信息", value="`/info user`", inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(InfoCommands(bot))
