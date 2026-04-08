import sqlite3
import threading
import os
from datetime import datetime
from config import logger

# ==================== 数据库配置 ====================

# 数据库路径（优先使用环境变量，否则使用默认路径）
DB_PATH = os.environ.get("DB_PATH", "/app/data/bot_data.db")

# 数据库连接（单例模式）
_db_connection = None
_db_lock = threading.Lock()

# 排行榜缓存
_leaderboard_cache = {}
_LB_CACHE_TTL = 60  # 60 秒

# 头像缓存（LRU）
_avatar_cache = {}
_AVATAR_CACHE_SIZE = 100
_AVATAR_CACHE_TTL = 3600  # 1 小时


# ==================== 数据库连接 ====================

def get_conn():
    """获取数据库连接（单例模式）"""
    global _db_connection
    with _db_lock:
        if _db_connection is None:
            # 确保数据目录存在
            db_dir = os.path.dirname(DB_PATH)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            
            _db_connection = sqlite3.connect(DB_PATH, check_same_thread=False)
            _db_connection.row_factory = sqlite3.Row
            # 启用 WAL 模式提高并发性能
            _db_connection.execute("PRAGMA journal_mode=WAL")
            logger.info(f"数据库连接已创建: {DB_PATH}")
        return _db_connection


def init_db():
    """初始化数据库表"""
    with get_conn() as conn:
        c = conn.cursor()
        
        # 用户表
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            guild_id TEXT, 
            user_id TEXT,
            xp INTEGER DEFAULT 0, 
            level INTEGER DEFAULT 1, 
            voice_xp INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )''')
        
        # 等级奖励角色表
        c.execute('''CREATE TABLE IF NOT EXISTS level_roles (
            guild_id TEXT, 
            level INTEGER, 
            role_id TEXT,
            PRIMARY KEY (guild_id, level)
        )''')
        
        # 反应角色表
        c.execute('''CREATE TABLE IF NOT EXISTS reaction_roles (
            guild_id TEXT, 
            message_id TEXT, 
            emoji TEXT, 
            role_id TEXT,
            PRIMARY KEY (guild_id, message_id, emoji)
        )''')
        
        # 计数器表
        c.execute('''CREATE TABLE IF NOT EXISTS counters (
            guild_id TEXT, 
            counter_type TEXT, 
            channel_id TEXT,
            message_template TEXT, 
            current_value INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, counter_type)
        )''')
        
        # 欢迎设置表
        c.execute('''CREATE TABLE IF NOT EXISTS welcome_settings (
            guild_id TEXT PRIMARY KEY, 
            channel_id TEXT, 
            message TEXT, 
            color TEXT
        )''')
        
        # 服务器设置表
        c.execute('''CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id TEXT PRIMARY KEY, 
            xp_rate REAL DEFAULT 1.0, 
            voice_xp_rate REAL DEFAULT 1.0
        )''')
        
        # 日志设置表
        c.execute('''CREATE TABLE IF NOT EXISTS log_settings (
            guild_id TEXT PRIMARY KEY,
            message_log_channel TEXT, 
            voice_log_channel TEXT, 
            mod_log_channel TEXT
        )''')
        
        conn.commit()
        logger.info("数据库表初始化完成")


def close_db():
    """关闭数据库连接"""
    global _db_connection
    with _db_lock:
        if _db_connection:
            _db_connection.close()
            _db_connection = None
            logger.info("数据库连接已关闭")


# ==================== 缓存管理 ====================

def invalidate_leaderboard_cache(guild_id):
    """清除服务器的排行榜缓存"""
    cache_key_xp = f"{guild_id}_xp"
    cache_key_voice = f"{guild_id}_voice"
    
    if cache_key_xp in _leaderboard_cache:
        del _leaderboard_cache[cache_key_xp]
    if cache_key_voice in _leaderboard_cache:
        del _leaderboard_cache[cache_key_voice]
    
    logger.debug(f"已清除 {guild_id} 的排行榜缓存")


def get_cached_avatar(member_id, avatar_url, size):
    """获取缓存的头像"""
    url_hash = hash(avatar_url) if avatar_url else 0
    cache_key = f"{member_id}_{url_hash}_{size}"
    
    if cache_key in _avatar_cache:
        cache_data, timestamp = _avatar_cache[cache_key]
        if datetime.now().timestamp() - timestamp < _AVATAR_CACHE_TTL:
            return cache_data
        else:
            del _avatar_cache[cache_key]
    return None


def set_cached_avatar(member_id, avatar_url, size, img):
    """缓存头像"""
    url_hash = hash(avatar_url) if avatar_url else 0
    cache_key = f"{member_id}_{url_hash}_{size}"
    
    # LRU：超出大小时删除最旧的
    if len(_avatar_cache) >= _AVATAR_CACHE_SIZE:
        _avatar_cache.popitem(last=False)
    
    _avatar_cache[cache_key] = (img, datetime.now().timestamp())


# ==================== 用户数据操作 ====================

def db_get_user(guild_id, user_id):
    """获取用户数据"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE guild_id=? AND user_id=?",
            (str(guild_id), str(user_id))
        ).fetchone()
        
        if not row:
            conn.execute(
                "INSERT INTO users (guild_id, user_id) VALUES (?, ?)",
                (str(guild_id), str(user_id))
            )
            conn.commit()
            return {"xp": 0, "level": 1, "voice_xp": 0}
        
        return {
            "xp": row["xp"], 
            "level": row["level"], 
            "voice_xp": row["voice_xp"]
        }


def db_update_user(guild_id, user_id, data):
    """更新用户数据"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET xp=?, level=?, voice_xp=? WHERE guild_id=? AND user_id=?",
            (data["xp"], data["level"], data["voice_xp"], str(guild_id), str(user_id))
        )
        conn.commit()
    
    # 清除排行榜缓存
    invalidate_leaderboard_cache(guild_id)


# ==================== 服务器设置 ====================

def db_get_guild_settings(guild_id):
    """获取服务器设置"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM guild_settings WHERE guild_id=?", 
            (str(guild_id),)
        ).fetchone()
        
        if not row:
            return {"xp_rate": 1.0, "voice_xp_rate": 1.0}
        
        return {
            "xp_rate": row["xp_rate"], 
            "voice_xp_rate": row["voice_xp_rate"]
        }


def db_update_guild_setting(guild_id, key, value):
    """更新服务器设置"""
    with get_conn() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO guild_settings (guild_id, {key}) VALUES (?, ?)",
            (str(guild_id), value)
        )
        conn.commit()


# ==================== 排行榜 ====================

def db_get_rank(guild_id, user_id):
    """获取用户排名（基于等级和经验）"""
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
    """获取排行榜数据（带缓存）
    
    mode: "xp" - 经验排行榜, "voice" - 语音排行榜
    """
    cache_key = f"{guild_id}_{mode}"
    
    # 检查缓存
    if cache_key in _leaderboard_cache:
        cache_data, timestamp = _leaderboard_cache[cache_key]
        if datetime.now().timestamp() - timestamp < _LB_CACHE_TTL:
            return cache_data
        else:
            del _leaderboard_cache[cache_key]
    
    # 查询数据库
    if mode == "xp":
        order = "level DESC, xp DESC"
    else:
        order = "voice_xp DESC"
    
    with get_conn() as conn:
        data = conn.execute(
            f"SELECT user_id, level, xp, voice_xp FROM users WHERE guild_id=? ORDER BY {order} LIMIT ?",
            (str(guild_id), limit)
        ).fetchall()
    
    # 存入缓存
    _leaderboard_cache[cache_key] = (data, datetime.now().timestamp())
    return data


# ==================== 等级奖励 ====================

def db_get_level_role(guild_id, level):
    """获取等级对应的奖励角色"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT role_id FROM level_roles WHERE guild_id=? AND level=?",
            (str(guild_id), level)
        ).fetchone()
        return row["role_id"] if row else None


def db_set_level_role(guild_id, level, role_id):
    """设置等级奖励角色"""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?)",
            (str(guild_id), level, str(role_id))
        )
        conn.commit()


def db_remove_level_role(guild_id, level):
    """移除等级奖励角色"""
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM level_roles WHERE guild_id=? AND level=?",
            (str(guild_id), level)
        )
        conn.commit()


# ==================== 日志设置 ====================

def db_get_log_channel(guild_id, channel_type):
    """获取日志频道
    
    channel_type: "message_log_channel", "voice_log_channel", "mod_log_channel"
    """
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {channel_type} FROM log_settings WHERE guild_id=?",
            (str(guild_id),)
        ).fetchone()
        return row[channel_type] if row else None


def db_set_log_channel(guild_id, col, channel_id):
    """设置日志频道"""
    with get_conn() as conn:
        conn.execute(
            f"INSERT INTO log_settings (guild_id, {col}) VALUES (?,?) "
            f"ON CONFLICT(guild_id) DO UPDATE SET {col}=excluded.{col}",
            (str(guild_id), str(channel_id))
        )
        conn.commit()


# ==================== 欢迎设置 ====================

def db_get_welcome_channel(guild_id):
    """获取欢迎频道"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT channel_id FROM welcome_settings WHERE guild_id=?",
            (str(guild_id),)
        ).fetchone()
        return row["channel_id"] if row else None


def db_set_welcome_channel(guild_id, channel_id):
    """设置欢迎频道"""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO welcome_settings (guild_id, channel_id, message, color) VALUES (?,?,?,?)",
            (str(guild_id), str(channel_id), "Welcome!", "#5865F2")
        )
        conn.commit()


# ==================== 反应角色 ====================

def db_get_reaction_role(guild_id, message_id, emoji):
    """获取反应角色"""
    with get_conn() as conn:
        return conn.execute(
            "SELECT role_id FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?",
            (str(guild_id), str(message_id), emoji)
        ).fetchone()


def db_set_reaction_role(guild_id, message_id, emoji, role_id):
    """设置反应角色"""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?,?,?,?)",
            (str(guild_id), str(message_id), emoji, str(role_id))
        )
        conn.commit()


def db_delete_reaction_role(guild_id, message_id, emoji):
    """删除反应角色"""
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?",
            (str(guild_id), str(message_id), emoji)
        )
        conn.commit()


# ==================== 计数器 ====================

def db_get_counter(guild_id, counter_type):
    """获取计数器"""
    with get_conn() as conn:
        return conn.execute(
            "SELECT channel_id, message_template, current_value FROM counters WHERE guild_id=? AND counter_type=?",
            (str(guild_id), counter_type)
        ).fetchone()


def db_set_counter(guild_id, counter_type, channel_id, message_template):
    """设置计数器"""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO counters (guild_id, counter_type, channel_id, message_template) VALUES (?,?,?,?)",
            (str(guild_id), counter_type, str(channel_id), message_template)
        )
        conn.commit()


def db_update_counter_value(guild_id, counter_type, value):
    """更新计数器数值"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE counters SET current_value=? WHERE guild_id=? AND counter_type=?",
            (value, str(guild_id), counter_type)
        )
        conn.commit()


def db_delete_counter(guild_id, counter_type):
    """删除计数器"""
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM counters WHERE guild_id=? AND counter_type=?",
            (str(guild_id), counter_type)
        )
        conn.commit()


# ==================== 等级计算辅助函数 ====================

def xp_needed(level):
    """计算升级所需经验"""
    return level * 125


def process_level_up(user_data):
    """处理升级逻辑，返回(新数据, 升了几级)"""
    levels_gained = 0
    while user_data["xp"] >= xp_needed(user_data["level"]):
        user_data["xp"] -= xp_needed(user_data["level"])
        user_data["level"] += 1
        levels_gained += 1
    return user_data, levels_gained
