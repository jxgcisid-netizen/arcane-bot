from flask import Flask, jsonify, request
from flask_cors import CORS
from database import get_conn, release_conn, db_get_guild_settings, db_update_guild_setting
from main import logger

app = Flask(__name__)
CORS(app)  # 允许前端跨域请求

# ==================== 仪表盘 ====================
@app.route("/api/stats")
def api_stats():
    """Bot 总体统计"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        # 总用户数
        cur.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]
        
        # 总服务器数（有用户数据的服务器）
        cur.execute("SELECT COUNT(DISTINCT guild_id) FROM users")
        guild_count = cur.fetchone()[0]
        
        # 最高等级
        cur.execute("SELECT MAX(level) FROM users")
        max_level = cur.fetchone()[0] or 0
        
        cur.close()
        release_conn(conn)
        
        return jsonify({
            "success": True,
            "data": {
                "total_users": user_count,
                "total_guilds": guild_count,
                "max_level": max_level
            }
        })
    except Exception as e:
        logger.error(f"API stats 错误: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 排行榜 ====================
@app.route("/api/leaderboard/<guild_id>")
def api_leaderboard(guild_id):
    """指定服务器的排行榜"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, level, xp, voice_xp 
            FROM users 
            WHERE guild_id = %s 
            ORDER BY level DESC, xp DESC 
            LIMIT 100
        """, (str(guild_id),))
        rows = cur.fetchall()
        cur.close()
        release_conn(conn)
        
        data = []
        for i, row in enumerate(rows):
            data.append({
                "rank": i + 1,
                "user_id": row[0],
                "level": row[1],
                "xp": row[2],
                "voice_xp": row[3]
            })
        
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"API leaderboard 错误: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 服务器设置 ====================
@app.route("/api/settings/<guild_id>", methods=["GET", "POST"])
def api_settings(guild_id):
    """获取或更新服务器设置"""
    if request.method == "GET":
        try:
            settings = db_get_guild_settings(guild_id)
            return jsonify({"success": True, "data": settings})
        except Exception as e:
            logger.error(f"API settings GET 错误: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
    
    elif request.method == "POST":
        try:
            data = request.json
            if "xp_rate" in data:
                rate = max(0.1, min(float(data["xp_rate"]), 10.0))
                db_update_guild_setting(guild_id, "xp_rate", rate)
            if "voice_xp_rate" in data:
                rate = max(0.1, min(float(data["voice_xp_rate"]), 10.0))
                db_update_guild_setting(guild_id, "voice_xp_rate", rate)
            return jsonify({"success": True, "message": "设置已更新"})
        except Exception as e:
            logger.error(f"API settings POST 错误: {e}")
            return jsonify({"success": False, "error": str(e)}), 500


# ==================== 服务器列表 ====================
@app.route("/api/guilds")
def api_guilds():
    """返回所有有数据的服务器"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT guild_id, COUNT(*) as user_count, MAX(level) as max_level
            FROM users 
            GROUP BY guild_id 
            ORDER BY user_count DESC
        """)
        rows = cur.fetchall()
        cur.close()
        release_conn(conn)
        
        data = []
        for row in rows:
            data.append({
                "guild_id": row[0],
                "user_count": row[1],
                "max_level": row[2]
            })
        
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"API guilds 错误: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 健康检查 ====================
@app.route("/api/health")
def api_health():
    return jsonify({"success": True, "status": "running"})


# ==================== 启动 ====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
