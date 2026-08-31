---
title: 部署 Reference
updated: 2026-08-31
---

# 部署 Reference

> 只記現況，不保存敘事歷史；歷史與理由放 ADR。Docker Compose 一鍵啟動全服務是 Phase 7 範圍，
> 這裡記錄 Phase 4 為止各服務目前各自怎麼跑起來。

## 執行平台

本機開發，非公開上線（見 `docs/specs/DRAFT.md` 已擱置的雲端部署討論）。

## Django 後端

| 項目 | 內容 |
| --- | --- |
| 入口 | `backend/manage.py runserver` |
| 必要環境變數 | `DJANGO_SECRET_KEY`、`DJANGO_DEBUG`、`DJANGO_ALLOWED_HOSTS`、`POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_HOST`、`POSTGRES_PORT`、`INTERNAL_API_KEY`、`N8N_INQUIRY_WEBHOOK_URL`、`N8N_INQUIRY_PARSE_WEBHOOK_URL`、`N8N_RESUME_WEBHOOK_URL`；`REFRESH_COOKIE_SECURE` 控制本機 HTTP／HTTPS Cookie Secure 屬性 |
| 外部依賴 | 本機 PostgreSQL（Phase 1 起） |
| Health Check | 尚未建立專用端點；未帶 Token 呼叫 `GET /api/v1/auth/me/` 回 401 可確認 Django 路由存活，不代表 DB 與外部依賴完整健康 |
| 已知限制 | 尚無專用健康檢查；Refresh Cookie 正式 HTTPS 環境必須設定 `REFRESH_COOKIE_SECURE=true` |

## Vue 前端

| 項目 | 內容 |
| --- | --- |
| 入口 | `frontend/src/main.ts`；本機開發於 `frontend/` 執行 `pnpm install`、`pnpm dev` |
| Build／檢查 | `pnpm lint`、`pnpm test`、`pnpm type-check`、`pnpm build`；輸出位於 `frontend/dist/`，不提交 Git |
| API 連線 | 開發環境由 Vite 將 `/api` 代理至 `http://127.0.0.1:8000`；瀏覽器請求攜帶 Refresh Cookie |
| 外部依賴 | Django API；未連後端時登入頁仍可顯示，但無法完成登入與資料流程 |

## n8n

| 項目 | 內容 |
| --- | --- |
| 執行方式 | `n8n/docker-compose.yml`（`docker compose up`，於 `n8n/` 目錄執行） |
| 必要環境變數 | 複製 `n8n/.env.example` 為 `n8n/.env`：`DJANGO_API_BASE_URL`（容器內存取本機 Django 用 `http://host.docker.internal:8000`）、`INTERNAL_API_KEY`（需與 `backend/.env` 一致）、`GEMINI_API_KEY` |
| 已知限制／踩坑 | n8n 2.x 預設擋 Code/Expression node 存取 `$env`，`docker-compose.yml` 已加 `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` 開放，不然 workflow 裡的 `{{$env.xxx}}` 全部會失敗（`access to env vars denied`），本機驗證時發現並記錄，詳見 `docs/ADR/debug/n8n-env-access.md` |
| Webhook 端點 | 匯入 `n8n/workflows/inquiry-flow.json` 後啟用（active），對外路徑 `POST http://localhost:5678/webhook/inquiry`；另有續傳子流程（FR-6a）路徑 `POST http://localhost:5678/webhook/inquiry/resume`，供 Django 核准供應商模糊比對案件後主動呼叫 |
| 對外埠 | `5678` |
| Health Check | `GET http://localhost:5678/healthz` |
| 目前無基礎設施 | 沒有另外的 basic auth／對外網址；只在本機 Docker 跑，正式對外使用前應補上驗證 |

## 已知限制（Phase 4 為止）

- 沒有 Docker Compose 統一一鍵啟動 Django + n8n + PostgreSQL + Vue（Phase 7）
- Phase 4 的瀏覽器驗證使用 Vite 本機頁面，未串接同時啟動的 Django/n8n 做完整真實環境 E2E；API 流程由 pytest integration tests 驗證。
