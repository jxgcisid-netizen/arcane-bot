import discord
from discord import app_commands, Interaction
from discord.ext import commands
from datetime import datetime
from main import logger

# ==================== 工具函数 ====================
def can_target(actor, target):
    if actor == target:
        return False, "不能操作自己"
    if target == target.guild.owner:
        return False, "不能操作服务器所有者"
    if actor.top_role <= target.top_role:
        return False, "不能操作权限比你高或相等的用户"
    return True, ""


# 所有 Cog 共用这个权限检查
async def check_privileged(self, interaction: Interaction) -> bool:
    """机器人主人 或 服务器群主/管理员 都可以"""
    app_info = await self.bot.application_info()
    is_owner = interaction.user.id == app_info.owner.id
    is_guild_owner = interaction.user.id == interaction.guild.owner_id
    is_admin = interaction.user.guild_permissions.administrator

    if not is_owner and not is_guild_owner and not is_admin:
        await interaction.response.send_message("❌ 只有机器人主人、服务器群主或管理员可以使用此命令", ephemeral=True)
        return False
    return True


# ==================== Admin ====================
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
    @app_commands.default_permissions(administrator=True)
    async def kick(self, interaction, member: discord.Member, reason: str = "无"):
        if not await self.check_target(interaction, member): return
        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(f"✅ 已踢出 {member.mention}", ephemeral=True)
            await self._log_mod(interaction, member, "👢 用户被踢出", discord.Color.orange(), reason)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 权限不足", ephemeral=True)

    @app_commands.command(name="ban", description="封禁用户")
    @app_commands.default_permissions(administrator=True)
    async def ban(self, interaction, member: discord.Member, reason: str = "无"):
        if not await self.check_target(interaction, member): return
        try:
            await member.ban(reason=reason)
            await interaction.response.send_message(f"✅ 已封禁 {member.mention}", ephemeral=True)
            await self._log_mod(interaction, member, "🔨 用户被封禁", discord.Color.red(), reason)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 权限不足", ephemeral=True)

    @app_commands.command(name="timeout", description="禁言用户")
    @app_commands.default_permissions(administrator=True)
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
        embed.add_field(name="📊 等级", value="`/level rank` `/level leaderboard`", inline=False)
        embed.add_field(name="🎭 反应角色", value="`/reaction add` `/reaction remove`", inline=False)
        embed.add_field(name="🔢 计数器", value="`/counter add` `/counter update` `/counter remove`", inline=False)
        embed.add_field(name="📋 日志", value="`/log set_message` `/log set_voice` `/log set_mod` `/log set_welcome`", inline=False)
        embed.add_field(name="🔧 管理", value="`/admin kick` `/admin ban` `/admin clear`", inline=False)
        embed.add_field(name="🎵 音乐", value="`/music play` `/music skip` `/music stop` `/music queue` `/music pause` `/music resume` `/music loop` `/music volume`", inline=False)
        await interaction.response.send_message(embed=embed)


# ==================== Level ====================
class LevelCommands(commands.GroupCog, name="level"):
    def __init__(self, bot):
        self.bot = bot

    # ==================== 公开命令 ====================
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

    # ==================== 特权命令（主人/群主/管理员） ====================
    @app_commands.command(name="add_role", description="设置等级奖励角色")
    async def add_role(self, interaction, level: int, role: discord.Role):
        if not await check_privileged(self, interaction): return
        from database import db_set_level_role
        db_set_level_role(interaction.guild.id, level, role.id)
        await interaction.response.send_message(f"✅ 等级 {level} → {role.mention}", ephemeral=True)

    @app_commands.command(name="set_xp", description="设置经验倍率")
    async def set_xp(self, interaction, rate: float):
        if not await check_privileged(self, interaction): return
        from database import db_update_guild_setting
        rate = max(0.1, min(rate, 10.0))
        db_update_guild_setting(interaction.guild.id, "xp_rate", rate)
        await interaction.response.send_message(f"✅ 经验倍率 → {rate}x", ephemeral=True)

    @app_commands.command(name="set_level", description="设置指定用户的等级")
    async def set_level(self, interaction: Interaction, member: discord.Member, level: int):
        if not await check_privileged(self, interaction): return
        from database import db_update_user, xp_needed
        level = max(1, level)
        xp = xp_needed(level) - 1
        user_data = {"xp": xp, "level": level, "voice_xp": 0}
        db_update_user(interaction.guild.id, member.id, user_data)
        await interaction.response.send_message(f"✅ {member.display_name} 的等级已设为 **{level}**", ephemeral=True)

    @app_commands.command(name="set_xp_user", description="设置指定用户的 XP")
    async def set_xp_user(self, interaction: Interaction, member: discord.Member, xp: int):
        if not await check_privileged(self, interaction): return
        from database import db_get_user, db_update_user, process_level_up
        data = db_get_user(interaction.guild.id, member.id)
        data["xp"] = xp
        data, gained = process_level_up(data)
        db_update_user(interaction.guild.id, member.id, data)
        msg = f"✅ {member.display_name} 的 XP 已设为 **{xp}** (等级: {data['level']})"
        if gained > 0:
            msg += f"，连升 **{gained}** 级！"
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="recover_from_roles", description="根据等级身份组恢复数据")
    async def recover_from_roles(self, interaction: Interaction):
        if not await check_privileged(self, interaction): return
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
        roles_removed = 0

        for member in guild.members:
            if member.bot:
                continue

            level_roles = []
            for role in member.roles:
                name = role.name.strip().lower()
                parts = name.split()
                if len(parts) == 2 and parts[1] == "level":
                    try:
                        level_num = int(parts[0])
                        level_roles.append((level_num, role))
                    except:
                        continue

            if not level_roles:
                continue

            highest = max(level_roles, key=lambda x: x[0])
            highest_level = highest[0]
            highest_role = highest[1]

            for level_num, role in level_roles:
                if role != highest_role:
                    try:
                        await member.remove_roles(role, reason="等级恢复：保留最高等级身份组")
                        roles_removed += 1
                    except:
                        pass

            uid = str(member.id)
            old_level = db_users.get(uid, 1)

            if highest_level > old_level:
                xp = xp_needed(highest_level) - 1
                user_data = {"xp": xp, "level": highest_level, "voice_xp": 0}
                db_update_user(guild.id, member.id, user_data)
                updated += 1

        msg = f"✅ 已恢复 **{updated}** 位成员的等级"
        if roles_removed > 0:
            msg += f"，清理了 **{roles_removed}** 个低等级身份组"
        await interaction.followup.send(msg, ephemeral=True)


# ==================== Reaction Role ====================
class ReactionCommands(commands.GroupCog, name="reaction"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="add", description="添加反应角色")
    async def add(self, interaction, message_id: str, emoji: str, role: discord.Role):
        if not await check_privileged(self, interaction): return
        from database import db_set_reaction_role
        db_set_reaction_role(interaction.guild.id, message_id, emoji, role.id)
        await interaction.response.send_message(f"✅ {emoji} → {role.mention}", ephemeral=True)

    @app_commands.command(name="remove", description="移除反应角色")
    async def remove(self, interaction, message_id: str, emoji: str):
        if not await check_privileged(self, interaction): return
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
    @app_commands.choices(counter_type=COUNTER_CHOICES)
    async def add(self, interaction, counter_type: app_commands.Choice[str], channel: discord.TextChannel, message_template: str):
        if not await check_privileged(self, interaction): return
        from database import db_set_counter
        db_set_counter(interaction.guild.id, counter_type.value, channel.id, message_template)
        await interaction.response.send_message(f"✅ {counter_type.name} → {channel.mention}", ephemeral=True)

    @app_commands.command(name="update", description="手动更新计数器")
    @app_commands.choices(counter_type=COUNTER_CHOICES)
    async def update(self, interaction, counter_type: app_commands.Choice[str], value: int):
        if not await check_privileged(self, interaction): return
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
    @app_commands.choices(counter_type=COUNTER_CHOICES)
    async def remove(self, interaction, counter_type: app_commands.Choice[str]):
        if not await check_privileged(self, interaction): return
        from database import db_delete_counter
        db_delete_counter(interaction.guild.id, counter_type.value)
        await interaction.response.send_message(f"✅ {counter_type.name} 已移除", ephemeral=True)


# ==================== Log ====================
class LogCommands(commands.GroupCog, name="log"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="set_message", description="设置消息日志频道")
    async def set_message(self, interaction, channel: discord.TextChannel):
        if not await check_privileged(self, interaction): return
        from database import db_set_log_channel
        db_set_log_channel(interaction.guild.id, "message_log_channel", channel.id)
        await interaction.response.send_message(f"✅ 消息日志 → {channel.mention}", ephemeral=True)

    @app_commands.command(name="set_voice", description="设置语音日志频道")
    async def set_voice(self, interaction, channel: discord.TextChannel):
        if not await check_privileged(self, interaction): return
        from database import db_set_log_channel
        db_set_log_channel(interaction.guild.id, "voice_log_channel", channel.id)
        await interaction.response.send_message(f"✅ 语音日志 → {channel.mention}", ephemeral=True)

    @app_commands.command(name="set_mod", description="设置管理日志频道")
    async def set_mod(self, interaction, channel: discord.TextChannel):
        if not await check_privileged(self, interaction): return
        from database import db_set_log_channel
        db_set_log_channel(interaction.guild.id, "mod_log_channel", channel.id)
        await interaction.response.send_message(f"✅ 管理日志 → {channel.mention}", ephemeral=True)

    @app_commands.command(name="set_welcome", description="设置欢迎/告别频道")
    async def set_welcome(self, interaction, channel: discord.TextChannel):
        if not await check_privileged(self, interaction): return
        from database import db_set_welcome_channel
        db_set_welcome_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(f"✅ 欢迎/告别 → {channel.mention}", ephemeral=True)


# ==================== Music ====================
import wavelink
import asyncio
import re

LAVALINK_NODES = [
    {
        "host": "lavalinkv4.serenetia.com",
        "port": 443,
        "password": "9f4fd53e593108bf-HKG",
        "secure": True,
        "name": "Serenetia-HKG"
    },
    {
        "host": "lava-v4.ajieblogs.eu.org",
        "port": 443,
        "password": "https://dsc.gg/ajidevserver",
        "secure": True,
        "name": "AjieBlogs"
    },
    {
        "host": "lavalinkv4.eu.nadeko.net",
        "port": 443,
        "password": "youshallnotpass",
        "secure": True,
        "name": "Nadeko-EU"
    },
    {
        "host": "lavalinkv4.us.nadeko.net",
        "port": 443,
        "password": "youshallnotpass",
        "secure": True,
        "name": "Nadeko-US"
    },
]

SEARCH_SOURCES = [
    app_commands.Choice(name="🎵 自动 (YT > B站)", value="auto"),
    app_commands.Choice(name="▶️ YouTube", value="ytsearch"),
    app_commands.Choice(name="📺 Bilibili", value="bili"),
    app_commands.Choice(name="🎧 SoundCloud", value="scsearch"),
]


def extract_bilibili_id(query: str) -> str | None:
    patterns = [
        r'bilibili\.com/video/(BV\w+)',
        r'bilibili\.com/video/(av\d+)',
        r'b23\.tv/(\w+)',
        r'(BV\w{10})',
        r'(av\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


class MusicPlayer:
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.queue: list = []
        self.current = None
        self.loop_mode = "off"

    def add(self, track):
        self.queue.append(track)

    def get_next(self):
        if self.loop_mode == "track" and self.current:
            return self.current
        if self.loop_mode == "queue" and self.current:
            self.queue.append(self.current)
        if self.queue:
            self.current = self.queue.pop(0)
            return self.current
        self.current = None
        return None

    def clear(self):
        self.queue.clear()
        self.current = None

    def shuffle(self):
        import random
        random.shuffle(self.queue)


class MusicCommands(commands.GroupCog, name="music"):
    def __init__(self, bot):
        self.bot = bot
        self.players: dict[int, MusicPlayer] = {}
        self.current_node_index = 0

    async def connect_lavalink(self):
        for attempt in range(len(LAVALINK_NODES)):
            node_info = LAVALINK_NODES[self.current_node_index % len(LAVALINK_NODES)]
            try:
                existing = wavelink.Pool.get_node(name=node_info["name"])
                if existing:
                    return existing
            except:
                pass

            try:
                node = await wavelink.Pool.connect(
                    client=self.bot,
                    nodes=[
                        wavelink.Node(
                            uri=f"{'wss' if node_info['secure'] else 'ws'}://{node_info['host']}:{node_info['port']}",
                            password=node_info["password"],
                            name=node_info["name"],
                        )
                    ],
                )
                logger.info(f"✅ Lavalink 已连接: {node_info['name']}")
                return node
            except Exception as e:
                logger.warning(f"❌ 节点 {node_info['name']} 连接失败: {e}，尝试下一个...")
                self.current_node_index += 1

        logger.error("❌ 所有 Lavalink 节点均无法连接")
        return None

    def get_node(self):
        try:
            return wavelink.Pool.get_node()
        except:
            return None

    def get_player(self, guild_id: int) -> MusicPlayer:
        if guild_id not in self.players:
            self.players[guild_id] = MusicPlayer(guild_id)
        return self.players[guild_id]

    async def ensure_voice(self, interaction: Interaction) -> bool:
        if not interaction.user.voice:
            await interaction.response.send_message("❌ 你需要先加入一个语音频道", ephemeral=True)
            return False

        node = self.get_node()
        if node is None:
            await interaction.response.send_message("❌ 音乐服务暂时不可用，请稍后再试", ephemeral=True)
            return False

        if not interaction.guild.voice_client:
            await interaction.user.voice.channel.connect(cls=wavelink.Player)
        elif interaction.guild.voice_client.channel != interaction.user.voice.channel:
            await interaction.guild.voice_client.move_to(interaction.user.voice.channel)

        return True

    @app_commands.command(name="play", description="播放一首歌曲（支持 B站/YouTube/SoundCloud）")
    @app_commands.choices(source=SEARCH_SOURCES)
    async def play(self, interaction: Interaction, query: str, source: str = "auto"):
        await interaction.response.defer()

        if not await self.ensure_voice(interaction):
            return

        node = self.get_node()
        if node is None:
            await interaction.followup.send("❌ 音乐服务暂时不可用")
            return

        search_query = query

        if extract_bilibili_id(query):
            bv_id = extract_bilibili_id(query)
            search_query = f"https://www.bilibili.com/video/{bv_id}" if bv_id else query
            actual_source = "bili"
            logger.info(f"检测到 B站链接: {search_query}")
        elif "youtube.com" in query or "youtu.be" in query:
            actual_source = "ytsearch"
        elif "soundcloud.com" in query:
            actual_source = "scsearch"
        elif "bilibili.com" in query or "b23.tv" in query:
            actual_source = "bili"
        elif source != "auto":
            actual_source = source
        else:
            actual_source = "ytsearch"

        try:
            if actual_source == "bili":
                search_query = f"bilibili:{search_query}" if not search_query.startswith("bilibili:") else search_query
                tracks = await wavelink.Playable.search(search_query, node=node, source="ytsearch")
                if not tracks:
                    tracks = await wavelink.Playable.search(query, node=node, source="ytsearch")
            else:
                tracks = await wavelink.Playable.search(search_query, node=node, source=actual_source)
        except Exception as e:
            logger.error(f"搜索失败 ({actual_source}): {e}")
            try:
                tracks = await wavelink.Playable.search(query, node=node, source="ytsearch")
            except Exception as e2:
                logger.error(f"降级搜索也失败: {e2}")
                await interaction.followup.send("❌ 搜索歌曲失败，请稍后再试")
                return

        if not tracks:
            await interaction.followup.send("❌ 未找到相关歌曲，换个关键词试试吧")
            return

        track = tracks[0]
        player = self.get_player(interaction.guild.id)
        vc = interaction.guild.voice_client

        source_names = {
            "auto": "自动",
            "ytsearch": "YouTube",
            "bili": "Bilibili",
            "scsearch": "SoundCloud",
        }

        if isinstance(vc, wavelink.Player):
            if vc.playing or not vc.paused:
                player.add(track)
                await interaction.followup.send(
                    f"✅ 已加入队列 [{source_names.get(actual_source, actual_source)}]: **{track.title}**"
                )
            else:
                await vc.play(track)
                player.current = track
                await interaction.followup.send(
                    f"🎵 [{source_names.get(actual_source, actual_source)}] 正在播放: **{track.title}**"
                )
        else:
            await interaction.followup.send("❌ 语音连接异常，请尝试重新播放")

    @app_commands.command(name="skip", description="跳过当前歌曲")
    async def skip(self, interaction: Interaction):
        await interaction.response.defer()

        vc = interaction.guild.voice_client
        if not vc or not isinstance(vc, wavelink.Player) or not vc.playing:
            await interaction.followup.send("❌ 当前没有正在播放的歌曲")
            return

        await vc.stop()
        await interaction.followup.send("⏭️ 已跳过当前歌曲")

    @app_commands.command(name="stop", description="停止播放并清空队列")
    async def stop(self, interaction: Interaction):
        await interaction.response.defer()

        player = self.get_player(interaction.guild.id)
        player.clear()

        vc = interaction.guild.voice_client
        if vc and isinstance(vc, wavelink.Player):
            await vc.disconnect()

        await interaction.followup.send("⏹️ 已停止播放并离开语音频道")

    @app_commands.command(name="queue", description="查看播放队列")
    async def queue(self, interaction: Interaction):
        await interaction.response.defer()

        player = self.get_player(interaction.guild.id)
        desc = ""

        if player.current:
            desc += f"🎵 **正在播放:** {player.current.title}\n\n"
        else:
            desc += "🎵 当前无正在播放的歌曲\n\n"

        if player.queue:
            desc += f"📋 **队列 ({len(player.queue)} 首):**\n"
            for i, track in enumerate(player.queue[:10], 1):
                desc += f"  {i}. {track.title}\n"
            if len(player.queue) > 10:
                desc += f"  ...还有 {len(player.queue) - 10} 首\n"
        else:
            desc += "📋 队列为空"

        desc += f"\n\n🔄 循环模式: **{player.loop_mode}**"
        await interaction.followup.send(desc)

    @app_commands.command(name="pause", description="暂停播放")
    async def pause(self, interaction: Interaction):
        await interaction.response.defer()

        vc = interaction.guild.voice_client
        if vc and isinstance(vc, wavelink.Player) and vc.playing:
            await vc.pause()
            await interaction.followup.send("⏸️ 已暂停")
        else:
            await interaction.followup.send("❌ 当前没有正在播放的歌曲")

    @app_commands.command(name="resume", description="继续播放")
    async def resume(self, interaction: Interaction):
        await interaction.response.defer()

        vc = interaction.guild.voice_client
        if vc and isinstance(vc, wavelink.Player) and vc.paused:
            await vc.resume()
            await interaction.followup.send("▶️ 继续播放")
        else:
            await interaction.followup.send("❌ 当前没有暂停的歌曲")

    @app_commands.command(name="loop", description="设置循环模式")
    @app_commands.choices(mode=[
        app_commands.Choice(name="关闭", value="off"),
        app_commands.Choice(name="单曲循环", value="track"),
        app_commands.Choice(name="队列循环", value="queue"),
    ])
    async def loop(self, interaction: Interaction, mode: str):
        player = self.get_player(interaction.guild.id)
        player.loop_mode = mode
        mode_names = {"off": "关闭", "track": "单曲循环", "queue": "队列循环"}
        await interaction.response.send_message(f"🔄 循环模式已设置为: **{mode_names[mode]}**")

    @app_commands.command(name="volume", description="设置音量 (1-100)")
    async def volume(self, interaction: Interaction, level: int):
        vc = interaction.guild.voice_client
        if vc and isinstance(vc, wavelink.Player):
            level = max(1, min(level, 100))
            await vc.set_volume(level)
            await interaction.response.send_message(f"🔊 音量已设置为: **{level}%**")
        else:
            await interaction.response.send_message("❌ 当前没有播放中的歌曲")

    @app_commands.command(name="shuffle", description="随机打乱队列")
    async def shuffle_cmd(self, interaction: Interaction):
        player = self.get_player(interaction.guild.id)
        if not player.queue:
            await interaction.response.send_message("❌ 队列为空，无法打乱")
            return
        player.shuffle()
        await interaction.response.send_message("🔀 队列已随机打乱")

    @app_commands.command(name="nowplaying", description="查看当前播放的歌曲")
    async def nowplaying(self, interaction: Interaction):
        await interaction.response.defer()

        player = self.get_player(interaction.guild.id)
        vc = interaction.guild.voice_client

        if not vc or not isinstance(vc, wavelink.Player) or not vc.playing:
            await interaction.followup.send("❌ 当前没有正在播放的歌曲")
            return

        track = player.current
        if track:
            desc = (
                f"🎵 **{track.title}**\n"
                f"👤 作者: {track.author}\n"
                f"⏱️ 时长: {track.length // 60000}:{(track.length // 1000) % 60:02d}\n"
                f"🔗 {track.uri}"
            )
            await interaction.followup.send(desc)
        else:
            await interaction.followup.send("❌ 无法获取当前歌曲信息")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload):
        player = self.get_player(payload.player.guild.id)
        next_track = player.get_next()

        if next_track:
            await payload.player.play(next_track)
        else:
            await payload.player.disconnect()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        vc = member.guild.voice_client
        if vc and isinstance(vc, wavelink.Player):
            if len(vc.channel.members) == 1:
                await asyncio.sleep(60)
                if len(vc.channel.members) == 1:
                    await vc.disconnect()


# ==================== 注册所有Cog ====================
async def setup(bot):
    cogs = [AdminCommands(bot), InfoCommands(bot), LevelCommands(bot), ReactionCommands(bot), CounterCommands(bot), LogCommands(bot), MusicCommands(bot)]
    for cog in cogs:
        await bot.add_cog(cog)
