import discord
from discord import app_commands
from discord.ext import commands
from database import db_get_log_channel
from config import logger


def can_target(actor, target):
    """检查是否可以操作目标用户"""
    # 不能操作自己
    if actor == target:
        return False, "不能操作自己"
    
    # 不能操作服务器所有者
    if target == target.guild.owner:
        return False, "不能操作服务器所有者"
    
    # 操作者必须是管理员或拥有更高权限
    if actor.top_role <= target.top_role:
        return False, f"不能操作权限比你高或相等的用户"
    
    return True, ""


class AdminCommands(commands.GroupCog, name="admin"):
    def __init__(self, bot):
        self.bot = bot

    async def check_target(self, interaction: discord.Interaction, member: discord.Member):
        """检查目标用户是否可操作"""
        # 检查操作者是否有管理员权限
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 你需要管理员权限", ephemeral=True)
            return False
        
        # 检查目标是否可操作
        can, reason = can_target(interaction.user, member)
        if not can:
            await interaction.response.send_message(f"❌ {reason}", ephemeral=True)
            return False
        
        return True

    @app_commands.command(name="kick", description="踢出用户")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "无"):
        """踢出用户（只能踢权限比自己低的）"""
        if not await self.check_target(interaction, member):
            return
        
        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(f"✅ 已踢出 {member.mention}", ephemeral=True)
            
            # 记录日志
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
            await interaction.response.send_message("❌ 权限不足，无法踢出该用户", ephemeral=True)

    @app_commands.command(name="ban", description="封禁用户")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "无"):
        """封禁用户（只能封权限比自己低的）"""
        if not await self.check_target(interaction, member):
            return
        
        try:
            await member.ban(reason=reason)
            await interaction.response.send_message(f"✅ 已封禁 {member.mention}", ephemeral=True)
            
            # 记录日志
            ch_id = db_get_log_channel(str(interaction.guild.id), "mod_log_channel")
            if ch_id:
                ch = interaction.guild.get_channel(int(ch_id))
                if ch:
                    embed = discord.Embed(
                        title="🔨 用户被封禁",
                        description=f"**用户:** {member.mention}\n**管理员:** {interaction.user.mention}\n**原因:** {reason}",
                        color=discord.Color.red(),
                        timestamp=datetime.now()
                    )
                    await ch.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 权限不足，无法封禁该用户", ephemeral=True)

    @app_commands.command(name="timeout", description="禁言用户")
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "无"):
        """禁言用户（只能禁言权限比自己低的）"""
        if not await self.check_target(interaction, member):
            return
        
        minutes = max(1, min(minutes, 40320))  # 最多28天
        duration = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
        
        try:
            await member.timeout(duration, reason=reason)
            await interaction.response.send_message(f"✅ 已禁言 {member.mention} {minutes}分钟", ephemeral=True)
            
            # 记录日志
            ch_id = db_get_log_channel(str(interaction.guild.id), "mod_log_channel")
            if ch_id:
                ch = interaction.guild.get_channel(int(ch_id))
                if ch:
                    embed = discord.Embed(
                        title="🔇 用户被禁言",
                        description=f"**用户:** {member.mention}\n**管理员:** {interaction.user.mention}\n**时长:** {minutes}分钟\n**原因:** {reason}",
                        color=discord.Color.orange(),
                        timestamp=datetime.now()
                    )
                    await ch.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 权限不足，无法禁言该用户", ephemeral=True)

    @app_commands.command(name="clear", description="清除消息（最多100条）")
    @app_commands.default_permissions(administrator=True)
    async def clear(self, interaction: discord.Interaction, amount: int):
        """清除消息"""
        amount = max(1, min(amount, 100))
        await interaction.channel.purge(limit=amount)
        await interaction.response.send_message(f"✅ 已清除 {amount} 条消息", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdminCommands(bot))
