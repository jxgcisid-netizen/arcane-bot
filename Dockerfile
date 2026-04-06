FROM python:3.11-slim

WORKDIR /app

# 安装系统字体（让图片更好看）
RUN apt-get update && apt-get install -y \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

RUN mkdir -p /app/data

CMD ["python", "bot.py"]
