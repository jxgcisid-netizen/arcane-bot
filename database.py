import sqlite3
import threading
import os
from datetime import datetime
from collections import OrderedDict
from main import logger

# ==================== 配置 ====================
DB_PATH = os.environ.get("DB_PATH", "/app/data/bot_data.db")

_db_connection = None
_db_lock = threading.Lock()

_leaderboard_cache = {}
_LB_CACHE_TTL = 60

_avatar_cache = OrderedDict()
_AVATAR_CACHE_SIZE = 100
_AVATAR_CACHE_TTL = 3600

# 白名单：允许的列名
_ALLOWED_GUILD_SETTINGS = {"xp_rate", "voice_xp_rate"}
_ALLOWED_LOG_COLUMNS = {"message_log_channel", "voice_log_channel", "mod_log_channel"}


# ==================== 连接管理 ====================
def get_conn():
    global _db_connection
    with _db_lock:
        if _db_connection is None:
            db_dir = os.path.dirname(DB_PATH)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            _db_connection = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
            _db_connection.row_factory = sqlite3.Row
            _db_connection.execute("PRAGMA journal_mode=WAL")
            _db_connection.execute("PRAGMA busy_timeout=5000")
            logger.info(f"数据库连接: {DB_PATH}")
        return _db_connection


def init_db():
    tables = {
        "users": '''CREATE TABLE IF NOT EXISTS users (
            guild_id TEXT, user_id TEXT, xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1, voice_xp INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id))''',
        "level_roles": '''CREATE TABLE IF NOT EXISTS level_roles (
            guild_id TEXT, level INTEGER, role_id TEXT,
            PRIMARY KEY (guild_id, level))''',
        "reaction_roles": '''CREATE TABLE IF NOT EXISTS reaction_roles (
            guild_id TEXT, message_id TEXT, emoji TEXT, role_id TEXT,
            PRIMARY KEY (guild_id, message_id, emoji))''',
        "counters": '''CREATE TABLE IF NOT EXISTS counters (
            guild_id TEXT, counter_type TEXT, channel_id TEXT,
            message_template TEXT, current_value INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, counter_type))''',
        "welcome_settings": '''CREATE TABLE IF NOT EXISTS welcome_settings (
            guild_id TEXT PRIMARY KEY, channel_id TEXT, message TEXT, color TEXT)''',
        "guild_settings": '''CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id TEXT PRIMARY KEY, xp_rate REAL DEFAULT 1.0, voice_xp_rate REAL DEFAULT 1.0)''',
        "log_settings": '''CREATE TABLE IF NOT EXISTS log_settings (
            guild_id TEXT PRIMARY KEY, message_log_channel TEXT,
            voice_log_channel TEXT, mod_log_channel TEXT)'''
    }

    with get_conn() as conn:
        for sql in tables.values():
            conn.execute(sql)
        conn.commit()
    logger.info("数据库表初始化完成")


def close_db():
    global _db_connection
    with _db_lock:
        if _db_connection:
            _db_connection.close()
            _db_connection = None


# ==================== 缓存 ====================
def invalidate_leaderboard_cache(guild_id):
    for mode in ("xp", "voice"):
        _leaderboard_cache.pop(f"{guild_id}_{mode}", None)


def get_cached_avatar(member_id, avatar_url, size):
    cache_key = f"{member_id}_{hash(avatar_url) if avatar_url else 0}_{size}"
    entry = _avatar_cache.get(cache_key)
    if entry:
        data, ts = entry
        if datetime.now().timestamp() - ts < _AVATAR_CACHE_TTL:
            return data
        del _avatar_cache[cache_key]
    return None


def set_cached_avatar(member_id, avatar_url, size, img):
    cache_key = f"{member_id}_{hash(avatar_url) if avatar_url else 0}_{size}"
    if len(_avatar_cache) >= _AVATAR_CACHE_SIZE:
        _avatar_cache.popitem(last=False)
    _avatar_cache[cache_key] = (img, datetime.now().timestamp())
    _avatar_cache.move_to_end(cache_key)


# ==================== 用户 ====================
def db_get_user(guild_id, user_id):
    gid, uid = str(guild_id), str(user_id)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE guild_id=? AND user_id=?", (gid, uid)).fetchone()
        if not row:
            conn.execute("INSERT INTO users (guild_id, user_id) VALUES (?, ?)", (gid, uid))
            conn.commit()
            return {"xp": 0, "level": 1, "voice_xp": 0}
        return {"xp": row["xp"], "level": row["level"], "voice_xp": row["voice_xp"]}


def db_update_user(guild_id, user_id, data):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET xp=?, level=?, voice_xp=? WHERE guild_id=? AND user_id=?",
            (data["xp"], data["level"], data["voice_xp"], str(guild_id), str(user_id)))
        conn.commit()
    invalidate_leaderboard_cache(guild_id)


# ==================== 服务器设置 ====================
def db_get_guild_settings(guild_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM guild_settings WHERE guild_id=?", (str(guild_id),)).fetchone()
        return {"xp_rate": row["xp_rate"], "voice_xp_rate": row["voice_xp_rate"]} if row else {"xp_rate": 1.0, "voice_xp_rate": 1.0}


def db_update_guild_setting(guild_id, key, value):
    if key not in _ALLOWED_GUILD_SETTINGS:
        raise ValueError(f"不允许的设置项: {key}")
    with get_conn() as conn:
        conn.execute(f"INSERT INTO guild_settings (guild_id, {key}) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET {key}=excluded.{key}",
                     (str(guild_id), value))
        conn.commit()


# ==================== 排行榜 ====================
def db_get_rank(guild_id, user_id):
    """获取用户排名（等级优先，同级比经验）"""
    gid = str(guild_id)
    uid = str(user_id)
    with get_conn() as conn:
        user = conn.execute(
            "SELECT level, xp FROM users WHERE guild_id=? AND user_id=?",
            (gid, uid)
        ).fetchone()
        if not user:
            return 0
        row = conn.execute("""
            SELECT COUNT(*) + 1 FROM users 
            WHERE guild_id=? 
            AND (
                level > ? 
                OR (level = ? AND xp > ?)
            )
        """, (gid, user["level"], user["level"], user["xp"])).fetchone()
        return row[0] if row else 0


def db_get_leaderboard(guild_id, mode="xp", limit=10):
    """获取排行榜（等级优先，同级比经验/语音XP）"""
    cache_key = f"{guild_id}_{mode}"
    entry = _leaderboard_cache.get(cache_key)
    now_ts = datetime.now().timestamp()
    if entry:
        data, ts = entry
        if now_ts - ts < _LB_CACHE_TTL:
            return data
        del _leaderboard_cache[cache_key]

    if mode == "xp":
        order = "level DESC, xp DESC"
    else:
        order = "level DESC, voice_xp DESC"

    with get_conn() as conn:
        data = conn.execute(
            f"SELECT user_id, level, xp, voice_xp FROM users WHERE guild_id=? ORDER BY {order} LIMIT ?",
            (str(guild_id), limit)
        ).fetchall()

    _leaderboard_cache[cache_key] = (data, now_ts)
    return data


# ==================== 等级奖励 ====================
def db_get_level_role(guild_id, level):
    with get_conn() as conn:
        row = conn.execute("SELECT role_id FROM level_roles WHERE guild_id=? AND level=?", (str(guild_id), level)).fetchone()
    return row["role_id"] if row else None


def db_set_level_role(guild_id, level, role_id):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?)",
                     (str(guild_id), level, str(role_id)))
        conn.commit()


def db_remove_level_role(guild_id, level):
    with get_conn() as conn:
        conn.execute("DELETE FROM level_roles WHERE guild_id=? AND level=?", (str(guild_id), level))
        conn.commit()


# ==================== 日志频道 ====================
def db_get_log_channel(guild_id, channel_type):
    if channel_type not in _ALLOWED_LOG_COLUMNS:
        raise ValueError(f"不允许的频道类型: {channel_type}")
    with get_conn() as conn:
        row = conn.execute(f"SELECT {channel_type} FROM log_settings WHERE guild_id=?", (str(guild_id),)).fetchone()
    return row[channel_type] if row else None


def db_set_log_channel(guild_id, col, channel_id):
    if col not in _ALLOWED_LOG_COLUMNS:
        raise ValueError(f"不允许的列名: {col}")
    with get_conn() as conn:
        conn.execute(f"INSERT INTO log_settings (guild_id, {col}) VALUES (?,?) ON CONFLICT(guild_id) DO UPDATE SET {col}=excluded.{col}",
                     (str(guild_id), str(channel_id)))
        conn.commit()


# ==================== 欢迎频道 ====================
def db_get_welcome_channel(guild_id):
    with get_conn() as conn:
        row = conn.execute("SELECT channel_id FROM welcome_settings WHERE guild_id=?", (str(guild_id),)).fetchone()
    return row["channel_id"] if row else None


def db_set_welcome_channel(guild_id, channel_id):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO welcome_settings (guild_id, channel_id, message, color) VALUES (?,?,?,?)",
                     (str(guild_id), str(channel_id), "Welcome!", "#5865F2"))
        conn.commit()


# ==================== 反应角色 ====================
def db_get_reaction_role(guild_id, message_id, emoji):
    with get_conn() as conn:
        return conn.execute("SELECT role_id FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?",
                            (str(guild_id), str(message_id), emoji)).fetchone()


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
        return conn.execute("SELECT channel_id, message_template, current_value FROM counters WHERE guild_id=? AND counter_type=?",
                            (str(guild_id), counter_type)).fetchone()


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
        conn.execute("DELETE FROM counters WHERE guild_id=? AND counter_type=?", (str(guild_id), counter_type))
        conn.commit()


# ==================== 等级计算 ====================
def xp_needed(level):
    return level * 125


def process_level_up(user_data):
    """处理升级，返回(新数据, 升了几级)"""
    gained = 0
    while user_data["xp"] >= xp_needed(user_data["level"]):
        user_data["xp"] -= xp_needed(user_data["level"])
        user_data["level"] += 1
        gained += 1
    return user_data, gained
