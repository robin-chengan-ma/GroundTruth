# Phase 7：根目錄 Docker Compose 一鍵啟動用。非公開上線，維持與
# docs/reference/deploy.md 記錄的本機開發入口一致（manage.py runserver），
# 不額外引入 gunicorn／wsgi 正式部署工具鏈。
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# psycopg2-binary 用 wheel，不需要額外裝 libpq-dev／gcc；保留 curl 供
# docker-compose healthcheck 使用。
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 防呆：不依賴 host 檔案系統／git 是否保留執行位元（跨平台 COPY 有時會遺失），
# build 時明確補上執行權限。
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

# migrate／demo seed 失敗（例如 DB 尚未就緒、seed 撞到資料問題）直接讓容器結束，
# 交給 docker-compose 的 restart 與 depends_on healthcheck 處理重試，不在這裡
# 自行寫重試迴圈；實際流程（migrate → 視 LOAD_DEMO_DATA 決定是否 seed → 啟動）
# 見 docker-entrypoint.sh。
CMD ["/app/docker-entrypoint.sh"]
