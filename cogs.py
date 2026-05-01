import discord
from discord import app_commands, Interaction
from discord.ext import commands
from datetime import datetime
from main import logger

# ==================== Admin ====================
def can_target(actor, target):
    if actor == target:
        return False, "不能操作自己"
    if target == target.guild.owner:
        return False, "不能操作服务器所有者"
    if actor.top_role <= target.top_role:
        return False, "不能操作权限比你高或相等的用户"
    return True, ""


class AdminCommands(commands.GroupCog, name="admin"):
    def __init__(self, bot):
        self.bot = bot

    async def check_target(self, interaction, member):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 需要管理员权限", ephemeral=True)
            return False
        ok, reason = can_target(interaction.user, member)
        if not ok:
            await interaction.response.send_message(f"❌ {reason}", ephemeral=True)
        return ok

    async def _log_mod(self, interaction, member, title, color, reason, **extra):
        from database import db_get_log_channel
        ch_id = db_get_log_channel(str(interaction.guild.id), "mod_log_channel")
        if ch_id:
            ch = interaction.guild.get_channel(int(ch_id))
            if ch:
                desc = f"**用户:** {member.mention}\n**管理员:** {interaction.user.mention}\n**原因:** {reason}"
                for k, v in extra.items():
                    desc += f"\n**{k}:** {v}"
                await ch.send(embed=discord.Embed(title=title, description=desc, color=color, timestamp=datetime.now()))

    @app_commands.command(name="kick", description="踢出用户")
    async def kick(self, interaction, member: discord.Member, reason: str = "无"):
        if not await self.check_target(interaction, member): return
        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(f"✅ 已踢出 {member.mention}", ephemeral=True)
            await self._log_mod(interaction, member, "👢 用户被踢出", discord.Color.orange(), reason)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 权限不足", ephemeral=True)

    @app_commands.command(name="ban", description="封禁用户")
    async def ban(self, interaction, member: discord.Member, reason: str = "无"):
        if not await self.check_target(interaction, member): return
        try:
            await member.ban(reason=reason)
            await interaction.response.send_message(f"✅ 已封禁 {member.mention}", ephemeral=True)
            await self._log_mod(interaction, member, "🔨 用户被封禁", discord.Color.red(), reason)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 权限不足", ephemeral=True)

    @app_commands.command(name="timeout", description="禁言用户")
    async def timeout(self, interaction, member: discord.Member, minutes: int, reason: str = "无"):
        if not await self.check_target(interaction, member): return
        minutes = max(1, min(minutes, 40320))
        try:
            await member.timeout(datetime.now() + datetime.timedelta(minutes=minutes), reason=reason)
            await interaction.response.send_message(f"✅ 禁言 {member.mention} {minutes}分钟", ephemeral=True)
            await self._log_mod(interaction, member, "🔇 用户被禁言", discord.Color.orange(), reason, 时长=f"{minutes}分钟")
        except discord.Forbidden:
            await interaction.response.send_message("❌ 权限不足", ephemeral=True)

    @app_commands.command(name="clear", description="清除消息")
    @app_commands.default_permissions(administrator=True)
    async def clear(self, interaction, amount: int):
        amount = max(1, min(amount, 100))
        await interaction.channel.purge(limit=amount)
        await interaction.response.send_message(f"✅ 已清除 {amount} 条消息", ephemeral=True)


# ==================== Info ====================
class InfoCommands(commands.GroupCog, name="info"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="user", description="查看用户信息")
    async def userinfo(self, interaction, member: discord.Member = None):
        member = member or interaction.user
        av = member.avatar.url if member.avatar else member.default_avatar.url
        embed = discord.Embed(title=f"👤 {member.display_name}", color=member.color)
        embed.set_thumbnail(url=av)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="加入时间", value=member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "未知", inline=True)
        embed.add_field(name="注册时间", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="最高角色", value=member.top_role.mention, inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description="查看帮助")
    async def help(self, interaction):
        embed = discord.Embed(title="🤖 帮助", color=discord.Color.green())
        embed.add_field(name="📊 等级", value="`/level rank` `/level leaderboard` `/level add_role` `/level set_xp` `/level recover_from_roles`", inline=False)
        embed.add_field(name="🎭 反应角色", value="`/reaction add` `/reaction remove`", inline=False)
        embed.add_field(name="🔢 计数器", value="`/counter add` `/counter update` `/counter remove`", inline=False)
        embed.add_field(name="📋 日志", value="`/log set_message` `/log set_voice` `/log set_mod` `/log set_welcome`", inline=False)
        embed.add_field(name="🔧 管理", value="`/admin kick` `/admin ban` `/admin clear`", inline=False)
        await interaction.response.send_message(embed=embed)


# ==================== Level ====================
class LevelCommands(commands.GroupCog, name="level"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="rank", description="查看等级卡片")
    async def rank(self, interaction, member: discord.Member = None):
        await interaction.response.defer()
        member = member or interaction.user
        from database import db_get_user, db_get_rank, xp_needed
        from cards import create_rank_card

        data = db_get_user(interaction.guild.id, member.id)
        pos = db_get_rank(interaction.guild.id, member.id)
        needed = xp_needed(data["level"])

        try:
            buf = await create_rank_card(member, data["level"], data["xp"], needed, pos)
            await interaction.followup.send(file=discord.File(buf, "rank.png"))
        except Exception as e:
            logger.error(f"等级卡片失败: {e}")
            embed = discord.Embed(title=f"📊 {member.display_name}", description=f"等级：{data['level']}\nXP：{data['xp']}/{needed}\n排名：#{pos}", color=discord.Color.blue())
            embed.set_thumbnail(url=member.display_avatar.url)
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="leaderboard", description="查看排行榜")
    @app_commands.choices(mode=[app_commands.Choice(name="打字 XP", value="xp"), app_commands.Choice(name="语音 VP", value="voice")])
    async def leaderboard(self, interaction, mode: str = "xp"):
        await interaction.response.defer()
        from database import db_get_leaderboard, xp_needed
        from cards import create_leaderboard_card

        data = db_get_leaderboard(interaction.guild.id, mode=mode)
        if not data:
            await interaction.followup.send("📊 暂无数据")
            return

        users = []
        for row in data:
            try:
                member = await interaction.guild.fetch_member(int(row["user_id"]))
            except:
                try:
                    member = await self.bot.fetch_user(int(row["user_id"]))
                except:
                    continue
            users.append({"member": member, "name": member.display_name, "level": row["level"], "xp": row["xp"], "voice_xp": row["voice_xp"], "needed_xp": xp_needed(row["level"])})

        if not users:
            await interaction.followup.send("📊 暂无数据")
            return

        try:
            buf = await create_leaderboard_card(interaction.guild, users, mode)
            await interaction.followup.send(file=discord.File(buf, "leaderboard.png"))
        except Exception as e:
            logger.error(f"排行榜卡片失败: {e}")
            desc = ""
            for i, u in enumerate(users, 1):
                m = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                val = u["xp"] if mode == "xp" else u["voice_xp"]
                desc += f"{m} **{u['name']}** — Lv.{u['level']} ({val} {'XP' if mode=='xp' else 'VP'})\n"
            await interaction.followup.send(embed=discord.Embed(title="🏆 排行榜", description=desc, color=discord.Color.gold()))

    @app_commands.command(name="add_role", description="设置等级奖励角色")
    @app_commands.default_permissions(administrator=True)
    async def add_role(self, interaction, level: int, role: discord.Role):
        from database import db_set_level_role
        db_set_level_role(interaction.guild.id, level, role.id)
        await interaction.response.send_message(f"✅ 等级 {level} → {role.mention}", ephemeral=True)

    @app_commands.command(name="set_xp", description="设置经验倍率")
    @app_commands.default_permissions(administrator=True)
    async def set_xp(self, interaction, rate: float):
        from database import db_update_guild_setting
        rate = max(0.1, min(rate, 10.0))
        db_update_guild_setting(interaction.guild.id, "xp_rate", rate)
        await interaction.response.send_message(f"✅ 经验倍率 → {rate}x", ephemeral=True)

    @app_commands.command(name="recover_from_roles", description="根据成员已有的等级身份组，恢复数据库中的等级")
    @app_commands.default_permissions(administrator=True)
    async def recover_from_roles(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)

        from database import db_update_user, xp_needed, get_conn, release_conn

        guild = interaction.guild
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT user_id, level FROM users WHERE guild_id = %s", (str(guild.id),))
        db_users = {row[0]: row[1] for row in cur.fetchall()}
        cur.close()
        release_conn(conn)

        updated = 0

        for member in guild.members:
            if member.bot:
                continue

            highest_level = 0
            for role in member.roles:
                name = role.name.lower()
                if name.startswith("level ") or name.startswith("lv."):
                    try:
                        num = int(name.split()[-1]) if " " in name else int(name.split(".")[-1])
                        highest_level = max(highest_level, num)
                    except:
                        continue

            if highest_level > 0:
                uid = str(member.id)
                old_level = db_users.get(uid, 1)

                if highest_level > old_level:
                    xp = xp_needed(highest_level) - 1
                    user_data = {"xp": xp, "level": highest_level, "voice_xp": 0}
                    db_update_user(guild.id, member.id, user_data)
                    updated += 1

        await interaction.followup.send(f"✅ 已根据身份组恢复了 **{updated}** 位成员的等级", ephemeral=True)


# ==================== Reaction Role ====================
class ReactionCommands(commands.GroupCog, name="reaction"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="add", description="添加反应角色")
    @app_commands.default_permissions(administrator=True)
    async def add(self, interaction, message_id: str, emoji: str, role: discord.Role):
        from database import db_set_reaction_role
        db_set_reaction_role(interaction.guild.id, message_id, emoji, role.id)
        await interaction.response.send_message(f"✅ {emoji} → {role.mention}", ephemeral=True)

    @app_commands.command(name="remove", description="移除反应角色")
    @app_commands.default_permissions(administrator=True)
    async def remove(self, interaction, message_id: str, emoji: str):
        from database import db_delete_reaction_role
        db_delete_reaction_role(interaction.guild.id, message_id, emoji)
        await interaction.response.send_message("✅ 已移除", ephemeral=True)


# ==================== Counter ====================
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
    @app_commands.choices(counter_type=COUNTER_CHOICES)
    async def add(self, interaction, counter_type: app_commands.Choice[str], channel: discord.TextChannel, message_template: str):
        from database import db_set_counter
        db_set_counter(interaction.guild.id, counter_type.value, channel.id, message_template)
        await interaction.response.send_message(f"✅ {counter_type.name} → {channel.mention}", ephemeral=True)

    @app_commands.command(name="update", description="手动更新计数器")
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(counter_type=COUNTER_CHOICES)
    async def update(self, interaction, counter_type: app_commands.Choice[str], value: int):
        from database import db_update_counter_value, db_get_counter
        db_update_counter_value(interaction.guild.id, counter_type.value, value)
        row = db_get_counter(interaction.guild.id, counter_type.value)
        if row:
            ch = interaction.guild.get_channel(int(row["channel_id"]))
            if ch:
                msg_content = row["message_template"].replace("{value}", str(value))
                found = False
                async for m in ch.history(limit=10):
                    if m.author == self.bot.user and counter_type.value in m.content:
                        await m.edit(content=msg_content)
                        found = True
                        break
                if not found:
                    await ch.send(msg_content)
        await interaction.response.send_message(f"✅ {counter_type.name} → {value}", ephemeral=True)

    @app_commands.command(name="remove", description="移除计数器")
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(counter_type=COUNTER_CHOICES)
    async def remove(self, interaction, counter_type: app_commands.Choice[str]):
        from database import db_delete_counter
        db_delete_counter(interaction.guild.id, counter_type.value)
        await interaction.response.send_message(f"✅ {counter_type.name} 已移除", ephemeral=True)


# ==================== Log ====================
class LogCommands(commands.GroupCog, name="log"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="set_message", description="设置消息日志频道")
    @app_commands.default_permissions(administrator=True)
    async def set_message(self, interaction, channel: discord.TextChannel):
        from database import db_set_log_channel
        db_set_log_channel(interaction.guild.id, "message_log_channel", channel.id)
        await interaction.response.send_message(f"✅ 消息日志 → {channel.mention}", ephemeral=True)

    @app_commands.command(name="set_voice", description="设置语音日志频道")
    @app_commands.default_permissions(administrator=True)
    async def set_voice(self, interaction, channel: discord.TextChannel):
        from database import db_set_log_channel
        db_set_log_channel(interaction.guild.id, "voice_log_channel", channel.id)
        await interaction.response.send_message(f"✅ 语音日志 → {channel.mention}", ephemeral=True)

    @app_commands.command(name="set_mod", description="设置管理日志频道")
    @app_commands.default_permissions(administrator=True)
    async def set_mod(self, interaction, channel: discord.TextChannel):
        from database import db_set_log_channel
        db_set_log_channel(interaction.guild.id, "mod_log_channel", channel.id)
        await interaction.response.send_message(f"✅ 管理日志 → {channel.mention}", ephemeral=True)

    @app_commands.command(name="set_welcome", description="设置欢迎/告别频道")
    @app_commands.default_permissions(administrator=True)
    async def set_welcome(self, interaction, channel: discord.TextChannel):
        from database import db_set_welcome_channel
        db_set_welcome_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(f"✅ 欢迎/告别 → {channel.mention}", ephemeral=True)


# ==================== 注册所有Cog ====================
async def setup(bot):
    cogs = [AdminCommands(bot), InfoCommands(bot), LevelCommands(bot), ReactionCommands(bot), CounterCommands(bot), LogCommands(bot)]
    for cog in cogs:
        await bot.add_cog(cog)
