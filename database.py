import os
import threading
from datetime import datetime
from collections import OrderedDict
import psycopg2
import psycopg2.pool
import psycopg2.extras
from main import logger

# ==================== 配置 ====================
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/bot")

_pool = None
_pool_lock = threading.Lock()

_leaderboard_cache = {}
_LB_CACHE_TTL = 60

_avatar_cache = OrderedDict()
_AVATAR_CACHE_SIZE = 100
_AVATAR_CACHE_TTL = 3600

# 白名单：允许的列名
_ALLOWED_GUILD_SETTINGS = {"xp_rate", "voice_xp_rate"}
_ALLOWED_LOG_COLUMNS = {"message_log_channel", "voice_log_channel", "mod_log_channel"}


# ==================== 连接池 ====================
def get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            import urllib.parse
            url = urllib.parse.urlparse(DATABASE_URL)
            query = urllib.parse.parse_qs(url.query)
            sslmode = query.get('sslmode', ['disable'])[0]
            
            # 重建不含 sslmode 的 DSN
            base_url = f"{url.scheme}://{url.username}:{url.password}@{url.hostname}:{url.port}{url.path}"
            
            _pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                dsn=base_url,
                sslmode=sslmode
            )
            logger.info("PostgreSQL 连接池已创建")
        return _pool


def get_conn():
    """获取数据库连接"""
    pool = get_pool()
    conn = pool.getconn()
    conn.set_isolation_level(0)
    return conn


def release_conn(conn):
    """归还连接"""
    pool = get_pool()
    pool.putconn(conn)


def close_db():
    global _pool
    with _pool_lock:
        if _pool:
            _pool.closeall()
            _pool = None


# ==================== 初始化 ====================
def init_db():
    tables = [
        '''CREATE TABLE IF NOT EXISTS users (
            guild_id TEXT, user_id TEXT, xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1, voice_xp INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id))''',
        '''CREATE TABLE IF NOT EXISTS level_roles (
            guild_id TEXT, level INTEGER, role_id TEXT,
            PRIMARY KEY (guild_id, level))''',
        '''CREATE TABLE IF NOT EXISTS reaction_roles (
            guild_id TEXT, message_id TEXT, emoji TEXT, role_id TEXT,
            PRIMARY KEY (guild_id, message_id, emoji))''',
        '''CREATE TABLE IF NOT EXISTS counters (
            guild_id TEXT, counter_type TEXT, channel_id TEXT,
            message_template TEXT, current_value INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, counter_type))''',
        '''CREATE TABLE IF NOT EXISTS welcome_settings (
            guild_id TEXT PRIMARY KEY, channel_id TEXT, message TEXT, color TEXT)''',
        '''CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id TEXT PRIMARY KEY, xp_rate REAL DEFAULT 1.0, voice_xp_rate REAL DEFAULT 1.0)''',
        '''CREATE TABLE IF NOT EXISTS log_settings (
            guild_id TEXT PRIMARY KEY, message_log_channel TEXT,
            voice_log_channel TEXT, mod_log_channel TEXT)'''
    ]

    conn = get_conn()
    try:
        cur = conn.cursor()
        for sql in tables:
            cur.execute(sql)
        conn.commit()
        cur.close()
        logger.info("PostgreSQL 表初始化完成")
    finally:
        release_conn(conn)


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
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE guild_id=%s AND user_id=%s", (gid, uid))
        row = cur.fetchone()
        cur.close()
        if not row:
            conn2 = get_conn()
            try:
                cur2 = conn2.cursor()
                cur2.execute("INSERT INTO users (guild_id, user_id) VALUES (%s, %s)", (gid, uid))
                conn2.commit()
                cur2.close()
            finally:
                release_conn(conn2)
            return {"xp": 0, "level": 1, "voice_xp": 0}
        cols = [desc[0] for desc in cur.description]
        data = dict(zip(cols, row))
        return {"xp": data["xp"], "level": data["level"], "voice_xp": data["voice_xp"]}
    finally:
        release_conn(conn)


def db_update_user(guild_id, user_id, data):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET xp=%s, level=%s, voice_xp=%s WHERE guild_id=%s AND user_id=%s",
            (data["xp"], data["level"], data["voice_xp"], str(guild_id), str(user_id)))
        conn.commit()
        cur.close()
    finally:
        release_conn(conn)
    invalidate_leaderboard_cache(guild_id)


# ==================== 服务器设置 ====================
def db_get_guild_settings(guild_id):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM guild_settings WHERE guild_id=%s", (str(guild_id),))
        row = cur.fetchone()
        cur.close()
        if row:
            cols = [desc[0] for desc in cur.description]
            data = dict(zip(cols, row))
            return {"xp_rate": data["xp_rate"], "voice_xp_rate": data["voice_xp_rate"]}
        return {"xp_rate": 1.0, "voice_xp_rate": 1.0}
    finally:
        release_conn(conn)


def db_update_guild_setting(guild_id, key, value):
    if key not in _ALLOWED_GUILD_SETTINGS:
        raise ValueError(f"不允许的设置项: {key}")
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO guild_settings (guild_id, {key}) VALUES (%s, %s) ON CONFLICT (guild_id) DO UPDATE SET {key}=EXCLUDED.{key}",
            (str(guild_id), value))
        conn.commit()
        cur.close()
    finally:
        release_conn(conn)


# ==================== 排行榜 ====================
def db_get_rank(guild_id, user_id):
    gid = str(guild_id)
    uid = str(user_id)
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT level, xp FROM users WHERE guild_id=%s AND user_id=%s",
            (gid, uid)
        )
        user = cur.fetchone()
        if not user:
            cur.close()
            return 0

        cur.execute("""
            SELECT COUNT(*) + 1 FROM users
            WHERE guild_id=%s
            AND (
                level > %s
                OR (level = %s AND xp > %s)
            )
        """, (gid, user[0], user[0], user[1]))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else 0
    finally:
        release_conn(conn)


def db_get_leaderboard(guild_id, mode="xp", limit=10):
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

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT user_id, level, xp, voice_xp FROM users WHERE guild_id=%s ORDER BY {order} LIMIT %s",
            (str(guild_id), limit)
        )
        rows = cur.fetchall()
        cur.close()
        data = []
        for row in rows:
            data.append({"user_id": row[0], "level": row[1], "xp": row[2], "voice_xp": row[3]})
    finally:
        release_conn(conn)

    _leaderboard_cache[cache_key] = (data, now_ts)
    return data


# ==================== 等级奖励 ====================
def db_get_level_role(guild_id, level):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT role_id FROM level_roles WHERE guild_id=%s AND level=%s", (str(guild_id), level))
        row = cur.fetchone()
        cur.close()
    finally:
        release_conn(conn)
    return row[0] if row else None


def db_set_level_role(guild_id, level, role_id):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO level_roles (guild_id, level, role_id) VALUES (%s, %s, %s) ON CONFLICT (guild_id, level) DO UPDATE SET role_id=EXCLUDED.role_id",
                     (str(guild_id), level, str(role_id)))
        conn.commit()
        cur.close()
    finally:
        release_conn(conn)


def db_remove_level_role(guild_id, level):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM level_roles WHERE guild_id=%s AND level=%s", (str(guild_id), level))
        conn.commit()
        cur.close()
    finally:
        release_conn(conn)


# ==================== 日志频道 ====================
def db_get_log_channel(guild_id, channel_type):
    if channel_type not in _ALLOWED_LOG_COLUMNS:
        raise ValueError(f"不允许的频道类型: {channel_type}")
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT {channel_type} FROM log_settings WHERE guild_id=%s", (str(guild_id),))
        row = cur.fetchone()
        cur.close()
    finally:
        release_conn(conn)
    return row[0] if row else None


def db_set_log_channel(guild_id, col, channel_id):
    if col not in _ALLOWED_LOG_COLUMNS:
        raise ValueError(f"不允许的列名: {col}")
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"INSERT INTO log_settings (guild_id, {col}) VALUES (%s, %s) ON CONFLICT (guild_id) DO UPDATE SET {col}=EXCLUDED.{col}",
                     (str(guild_id), str(channel_id)))
        conn.commit()
        cur.close()
    finally:
        release_conn(conn)


# ==================== 欢迎频道 ====================
def db_get_welcome_channel(guild_id):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT channel_id FROM welcome_settings WHERE guild_id=%s", (str(guild_id),))
        row = cur.fetchone()
        cur.close()
    finally:
        release_conn(conn)
    return row[0] if row else None


def db_set_welcome_channel(guild_id, channel_id):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO welcome_settings (guild_id, channel_id, message, color) VALUES (%s, %s, %s, %s) ON CONFLICT (guild_id) DO UPDATE SET channel_id=EXCLUDED.channel_id",
                     (str(guild_id), str(channel_id), "Welcome!", "#5865F2"))
        conn.commit()
        cur.close()
    finally:
        release_conn(conn)


# ==================== 反应角色 ====================
def db_get_reaction_role(guild_id, message_id, emoji):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT role_id FROM reaction_roles WHERE guild_id=%s AND message_id=%s AND emoji=%s",
                     (str(guild_id), str(message_id), emoji))
        row = cur.fetchone()
        cur.close()
    finally:
        release_conn(conn)
    return row


def db_set_reaction_role(guild_id, message_id, emoji, role_id):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (%s, %s, %s, %s) ON CONFLICT (guild_id, message_id, emoji) DO UPDATE SET role_id=EXCLUDED.role_id",
                     (str(guild_id), str(message_id), emoji, str(role_id)))
        conn.commit()
        cur.close()
    finally:
        release_conn(conn)


def db_delete_reaction_role(guild_id, message_id, emoji):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM reaction_roles WHERE guild_id=%s AND message_id=%s AND emoji=%s",
                     (str(guild_id), str(message_id), emoji))
        conn.commit()
        cur.close()
    finally:
        release_conn(conn)


# ==================== 计数器 ====================
def db_get_counter(guild_id, counter_type):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT channel_id, message_template, current_value FROM counters WHERE guild_id=%s AND counter_type=%s",
                     (str(guild_id), counter_type))
        row = cur.fetchone()
        cur.close()
        if row:
            return {"channel_id": row[0], "message_template": row[1], "current_value": row[2]}
        return None
    finally:
        release_conn(conn)


def db_set_counter(guild_id, counter_type, channel_id, message_template):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO counters (guild_id, counter_type, channel_id, message_template) VALUES (%s, %s, %s, %s) ON CONFLICT (guild_id, counter_type) DO UPDATE SET channel_id=EXCLUDED.channel_id, message_template=EXCLUDED.message_template",
                     (str(guild_id), counter_type, str(channel_id), message_template))
        conn.commit()
        cur.close()
    finally:
        release_conn(conn)


def db_update_counter_value(guild_id, counter_type, value):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE counters SET current_value=%s WHERE guild_id=%s AND counter_type=%s",
                     (value, str(guild_id), counter_type))
        conn.commit()
        cur.close()
    finally:
        release_conn(conn)


def db_delete_counter(guild_id, counter_type):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM counters WHERE guild_id=%s AND counter_type=%s", (str(guild_id), counter_type))
        conn.commit()
        cur.close()
    finally:
        release_conn(conn)


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
