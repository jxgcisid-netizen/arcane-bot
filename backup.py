import os
import subprocess
import datetime
import requests
import base64
from main import logger

# 从环境变量读取
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_BACKUP_REPO")  # 格式: 用户名/仓库名
BACKUP_PATH = "backups"  # 仓库里的备份文件夹

async def scheduled_backup():
    """每日备份数据库到 GitHub 私有仓库"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        logger.warning("⚠️ GitHub 备份未配置 (缺少 GITHUB_TOKEN 或 GITHUB_BACKUP_REPO)")
        return

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("❌ 备份失败: 未找到 DATABASE_URL")
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"/tmp/backup_{timestamp}.sql"

    try:
        # 1. 导出数据库
        logger.info("🔄 正在导出数据库...")
        result = subprocess.run(
            ["pg_dump", db_url, "-f", backup_file],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            logger.error(f"❌ pg_dump 失败: {result.stderr}")
            return

        # 2. 读取文件内容
        with open(backup_file, "r") as f:
            content = f.read()

        # 3. 推送到 GitHub
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{BACKUP_PATH}/backup_{timestamp}.sql"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        data = {
            "message": f"📦 数据库备份 {timestamp}",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": "main"
        }

        resp = requests.put(url, headers=headers, json=data)
        if resp.status_code in [200, 201]:
            logger.info(f"✅ 备份已上传到 GitHub: backup_{timestamp}.sql")
        else:
            logger.error(f"❌ 上传失败: {resp.status_code} - {resp.text}")

        # 4. 清理本地文件
        os.remove(backup_file)

    except Exception as e:
        logger.error(f"❌ 备份任务失败: {e}")
