FROM python:3.11-slim

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

# 安装系统依赖 (包括用于添加 PostgreSQL 仓库的 lsb-release)
RUN apt-get update && apt-get install -y lsb-release wget gnupg \
    && echo "deb https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg \
    && apt-get update \
    && apt-get install -y postgresql-client-18 \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data

EXPOSE 8080

CMD ["python", "main.py"]
