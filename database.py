import sqlite3
import threading
from datetime import datetime
from config import logger

# 数据库连接（单例）
_db_connection = None
_db_lock = threading.Lock()
_db_wal_lock = threading.Lock()

# 排行榜缓存
_leaderboard_cache = {}
_LB_CACHE_TTL = 60  # 60 秒

# 头像缓存（LRU）
_avatar_cache = {}
_AVATAR_CACHE_SIZE = 100
_AVATAR_CACHE_TTL = 3600  # 1 小时


def get_conn():
    """获取数据库连接（单例模式）"""
    global _db_connection
    with _db_lock:
        if _db_connection is None:
            _db_connection = sqlite3.connect("bot_data.db", check_same_thread=False)
            _db_connection.row_factory = sqlite3.Row
            # 启用 WAL 模式提高并发性能
            _db_connection.execute("PRAGMA journal_mode=WAL")
            logger.info("数据库连接已创建")
        return _db_connection


def init_db():
    """初始化数据库表"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            guild_id TEXT, user_id TEXT,
            xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, voice_xp INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS level_roles (
            guild_id TEXT, level INTEGER, role_id TEXT,
            PRIMARY KEY (guild_id, level)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS reaction_roles (
            guild_id TEXT, message_id TEXT, emoji TEXT, role_id TEXT,
            PRIMARY KEY (guild_id, message_id, emoji)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS counters (
            guild_id TEXT, counter_type TEXT, channel_id TEXT,
            message_template TEXT, current_value INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, counter_type)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS welcome_settings (
            guild_id TEXT PRIMARY KEY, channel_id TEXT, message TEXT, color TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id TEXT PRIMARY KEY, xp_rate REAL DEFAULT 1.0, voice_xp_rate REAL DEFAULT 1.0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS log_settings (
            guild_id TEXT PRIMARY KEY,
            message_log_channel TEXT, voice_log_channel TEXT, mod_log_channel TEXT
        )''')
        conn.commit()
        logger.info("数据库表初始化完成")


def invalidate_leaderboard_cache(guild_id):
    """清除服务器的排行榜缓存"""
    cache_key = f"{guild_id}_xp"
    if cache_key in _leaderboard_cache:
        del _leaderboard_cache[cache_key]
    cache_key = f"{guild_id}_voice"
    if cache_key in _leaderboard_cache:
        del _leaderboard_cache[cache_key]


# ==================== 用户数据操作 ====================

def db_get_user(guild_id, user_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE guild_id=? AND user_id=?",
            (str(guild_id), str(user_id))
        ).fetchone()
        if not row:
            conn.execute("INSERT INTO users (guild_id, user_id) VALUES (?, ?)",
                         (str(guild_id), str(user_id)))
            conn.commit()
            return {"xp": 0, "level": 1, "voice_xp": 0}
        return {"xp": row["xp"], "level": row["level"], "voice_xp": row["voice_xp"]}


def db_update_user(guild_id, user_id, data):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET xp=?, level=?, voice_xp=? WHERE guild_id=? AND user_id=?",
            (data["xp"], data["level"], data["voice_xp"], str(guild_id), str(user_id))
        )
        conn.commit()
    invalidate_leaderboard_cache(guild_id)


def db_get_guild_settings(guild_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM guild_settings WHERE guild_id=?", (str(guild_id),)).fetchone()
        return {"xp_rate": row["xp_rate"], "voice_xp_rate": row["voice_xp_rate"]} if row else {"xp_rate": 1.0, "voice_xp_rate": 1.0}


def db_update_guild_setting(guild_id, key, value):
    with get_conn() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO guild_settings (guild_id, {key}) VALUES (?, ?)",
            (str(guild_id), value)
        )
        conn.commit()


def db_get_rank(guild_id, user_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id FROM users WHERE guild_id=? ORDER BY level DESC, xp DESC",
            (str(guild_id),)
        ).fetchall()
        for i, row in enumerate(rows, 1):
            if row["user_id"] == str(user_id):
                return i
    return 0


def db_get_leaderboard(guild_id, mode="xp", limit=10):
    """获取排行榜数据（带缓存）"""
    cache_key = f"{guild_id}_{mode}"

    if cache_key in _leaderboard_cache:
        cache_data, timestamp = _leaderboard_cache[cache_key]
        if datetime.now().timestamp() - timestamp < _LB_CACHE_TTL:
            return cache_data
        else:
            del _leaderboard_cache[cache_key]

    order = "level DESC, xp DESC" if mode == "xp" else "voice_xp DESC"
    with get_conn() as conn:
        data = conn.execute(
            f"SELECT user_id, level, xp, voice_xp FROM users WHERE guild_id=? ORDER BY {order} LIMIT ?",
            (str(guild_id), limit)
        ).fetchall()

    _leaderboard_cache[cache_key] = (data, datetime.now().timestamp())
    return data


# ==================== 等级奖励 ====================

def db_get_level_role(guild_id, level):
    with get_conn() as conn:
        row = conn.execute("SELECT role_id FROM level_roles WHERE guild_id=? AND level=?",
                           (str(guild_id), level)).fetchone()
        return row["role_id"] if row else None


def db_set_level_role(guild_id, level, role_id):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?)",
                     (str(guild_id), level, str(role_id)))
        conn.commit()


# ==================== 日志设置 ====================

def db_get_log_channel(guild_id, channel_type):
    with get_conn() as conn:
        row = conn.execute(f"SELECT {channel_type} FROM log_settings WHERE guild_id=?",
                           (str(guild_id),)).fetchone()
        return row[channel_type] if row else None


def db_set_log_channel(guild_id, col, channel_id):
    with get_conn() as conn:
        conn.execute(
            f"INSERT INTO log_settings (guild_id, {col}) VALUES (?,?) "
            f"ON CONFLICT(guild_id) DO UPDATE SET {col}=excluded.{col}",
            (str(guild_id), str(channel_id))
        )
        conn.commit()


# ==================== 欢迎设置 ====================

def db_get_welcome_channel(guild_id):
    with get_conn() as conn:
        row = conn.execute("SELECT channel_id FROM welcome_settings WHERE guild_id=?",
                           (str(guild_id),)).fetchone()
        return row["channel_id"] if row else None


def db_set_welcome_channel(guild_id, channel_id):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO welcome_settings (guild_id, channel_id, message, color) VALUES (?,?,?,?)",
                     (str(guild_id), str(channel_id), "Welcome!", "#5865F2"))
        conn.commit()


# ==================== 反应角色 ====================

def db_get_reaction_role(guild_id, message_id, emoji):
    with get_conn() as conn:
        return conn.execute(
            "SELECT role_id FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?",
            (str(guild_id), str(message_id), emoji)
        ).fetchone()


def db_set_reaction_role(guild_id, message_id, emoji, role_id):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?,?,?,?)",
                     (str(guild_id), str(message_id), emoji, str(role_id)))
        conn.commit()


def db_delete_reaction_role(guild_id, message_id, emoji):
    with get_conn() as conn:
        conn.execute("DELETE FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?",
                     (str(guild_id), str(message_id), emoji))
        conn.commit()


# ==================== 计数器 ====================

def db_get_counter(guild_id, counter_type):
    with get_conn() as conn:
        return conn.execute(
            "SELECT channel_id, message_template, current_value FROM counters WHERE guild_id=? AND counter_type=?",
            (str(guild_id), counter_type)
        ).fetchone()


def db_set_counter(guild_id, counter_type, channel_id, message_template):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO counters (guild_id, counter_type, channel_id, message_template) VALUES (?,?,?,?)",
                     (str(guild_id), counter_type, str(channel_id), message_template))
        conn.commit()


def db_update_counter_value(guild_id, counter_type, value):
    with get_conn() as conn:
        conn.execute("UPDATE counters SET current_value=? WHERE guild_id=? AND counter_type=?",
                     (value, str(guild_id), counter_type))
        conn.commit()


def db_delete_counter(guild_id, counter_type):
    with get_conn() as conn:
        conn.execute("DELETE FROM counters WHERE guild_id=? AND counter_type=?",
                     (str(guild_id), counter_type))
        conn.commit()


# ==================== 头像缓存 ====================

def _get_avatar_cache_key(member_id, avatar_url, size):
    url_hash = hash(avatar_url) if avatar_url else 0
    return f"{member_id}_{url_hash}_{size}"


def get_cached_avatar(member_id, avatar_url, size):
    cache_key = _get_avatar_cache_key(member_id, avatar_url, size)
    if cache_key in _avatar_cache:
        cache_data, timestamp = _avatar_cache[cache_key]
        if datetime.now().timestamp() - timestamp < _AVATAR_CACHE_TTL:
            return cache_data
        else:
            del _avatar_cache[cache_key]
    return None


def set_cached_avatar(member_id, avatar_url, size, img):
    cache_key = _get_avatar_cache_key(member_id, avatar_url, size)
    if len(_avatar_cache) >= _AVATAR_CACHE_SIZE:
        _avatar_cache.popitem(last=False)
    _avatar_cache[cache_key] = (img, datetime.now().timestamp())


# 等级计算
def xp_needed(level):
    return level * 125


def process_level_up(user_data):
    levels_gained = 0
    while user_data["xp"] >= xp_needed(user_data["level"]):
        user_data["xp"] -= xp_needed(user_data["level"])
        user_data["level"] += 1
        levels_gained += 1
    return user_data, levels_gained
