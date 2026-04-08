FROM python:3.11-slim

# 安装系统字体（让图片文字正常显示）
RUN apt-get update && apt-get install -y \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# 创建数据目录（数据库持久化）
RUN mkdir -p /app/data

# 修改代码中的数据库路径
# 注意：需要把 bot.py 里的 "bot_data.db" 改成 "/app/data/bot_data.db"

CMD ["python", "bot.py"]
