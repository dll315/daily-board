FROM python:3.12-slim

# 时区：定时推送按本地时间（Asia/Shanghai）触发
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    NO_OPEN=1 \
    PORT=3000

WORKDIR /app
COPY server.py push.py ./
COPY public ./public

# 配置 / 提醒 / 缓存持久化：挂载卷到宿主机 ./data
VOLUME ["/app/data"]

EXPOSE 3000

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:3000/api/health', timeout=4)"

CMD ["python", "server.py"]
