FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（字体、编译工具、数据库客户端、音视频处理）
RUN apt-get update && apt-get install -y \
    fonts-dejavu \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    tzdata \
    gcc \
    libpq-dev \
    ffmpeg \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建数据目录
RUN mkdir -p /app/data

# 暴露端口（保留以备健康检查）
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import psycopg2; print('OK')" || exit 1

# 启动命令
CMD ["python", "main.py"]
