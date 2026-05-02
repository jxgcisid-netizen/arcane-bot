FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    fonts-dejavu \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    tzdata \
    gcc \
    libpq-dev \
    ffmpeg \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data

# 下载并安装 cloudflared
RUN curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared \
    && chmod +x /usr/local/bin/cloudflared

EXPOSE 8080

CMD ["python", "main.py"]
