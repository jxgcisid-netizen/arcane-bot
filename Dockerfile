FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    lsb-release \
    fonts-dejavu \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    tzdata \
    gcc \
    libpq-dev \
    ffmpeg \
    curl \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# 添加 PostgreSQL 官方仓库（获取最新版 pg_dump）
RUN sh -c 'echo "deb https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list' \
    && wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg \
    && apt-get update \
    && apt-get install -y postgresql-client-18 \
    && rm -rf /var/lib/apt/lists/*

# 设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 强制重新构建
RUN echo "rebuild v3"

COPY . .

# 复制项目文件
COPY . .

# 创建数据目录
RUN mkdir -p /app/data

# 启动命令
CMD ["python", "main.py"]
