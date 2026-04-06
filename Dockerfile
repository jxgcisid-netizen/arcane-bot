FROM python:3.10-slim

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 如果 requirements.txt 安装失败，单独安装
RUN pip install git+https://github.com/krishsharma0413/DiscordLevelingCard.git

COPY . .

CMD ["python", "bot.py"]
