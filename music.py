import discord
from discord import app_commands, Interaction
from discord.ext import commands
import wavelink
import asyncio
import re
from main import logger

# ==================== Lavalink 节点列表 ====================
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

# ==================== 搜索源选项 ====================
SEARCH_SOURCES = [
    app_commands.Choice(name="🎵 自动 (YT > B站)", value="auto"),
    app_commands.Choice(name="▶️ YouTube", value="ytsearch"),
    app_commands.Choice(name="📺 Bilibili", value="bili"),
    app_commands.Choice(name="🎧 SoundCloud", value="scsearch"),
]


def extract_bilibili_id(query: str) -> str | None:
    """从字符串中提取 B站 BV/AV 号"""
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


# ==================== 音乐播放器 ====================
class MusicPlayer:
    """管理单个服务器的播放状态"""

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


# ==================== 音乐 Cog ====================
class MusicCommands(commands.GroupCog, name="music"):
    def __init__(self, bot):
        self.bot = bot
        self.players: dict[int, MusicPlayer] = {}
        self.current_node_index = 0

    async def connect_lavalink(self):
        """连接 Lavalink，失败则自动切换下一个节点"""
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
        """获取当前可用的 Lavalink 节点"""
        try:
            return wavelink.Pool.get_node()
        except:
            return None

    def get_player(self, guild_id: int) -> MusicPlayer:
        """获取或创建服务器的音乐播放器"""
        if guild_id not in self.players:
            self.players[guild_id] = MusicPlayer(guild_id)
        return self.players[guild_id]

    async def ensure_voice(self, interaction: Interaction) -> bool:
        """确保 Bot 在正确的语音频道中"""
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

    # ==================== 自动播放下一首 ====================
    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload):
        player = self.get_player(payload.player.guild.id)
        next_track = player.get_next()

        if next_track:
            await payload.player.play(next_track)
        else:
            await payload.player.disconnect()

    # ==================== 无人则自动退出 ====================
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


# ==================== 注册 Cog ====================
async def setup(bot):
    await bot.add_cog(MusicCommands(bot))
