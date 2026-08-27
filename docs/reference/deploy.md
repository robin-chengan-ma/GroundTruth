---
title: 部署 Reference
updated: 2026-08-27
---

# 部署 Reference

> 只記現況，不保存敘事歷史；歷史與理由放 ADR。Docker Compose 一鍵啟動全服務是 Phase 7 範圍，
> 這裡先記錄 Phase 2 為止各服務目前各自怎麼跑起來。

## 執行平台

本機開發，非公開上線（見 `docs/specs/DRAFT.md` 已擱置的雲端部署討論）。

## Django 後端

| 項目 | 內容 |
| --- | --- |
| 入口 | `backend/manage.py runserver` |
| 必要環境變數 | `DJANGO_SECRET_KEY`、`DJANGO_DEBUG`、`DJANGO_ALLOWED_HOSTS`、`POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_HOST`、`POSTGRES_PORT`、`INTERNAL_API_KEY`、`N8N_INQUIRY_WEBHOOK_URL`（完整說明見 `backend/.env.example`） |
| 外部依賴 | 本機 PostgreSQL（Phase 1 起） |
| Health Check | 尚未建立專用端點；`GET /api/v1/roles/` 回 200 可視為存活 |
| 已知限制 | JWT 認證尚未套用（Phase 4）；CRUD 端點目前 `AllowAny` |

## n8n

| 項目 | 內容 |
| --- | --- |
| 執行方式 | `n8n/docker-compose.yml`（`docker compose up`，於 `n8n/` 目錄執行） |
| 必要環境變數 | 複製 `n8n/.env.example` 為 `n8n/.env`：`DJANGO_API_BASE_URL`（容器內存取本機 Django 用 `http://host.docker.internal:8000`）、`INTERNAL_API_KEY`（需與 `backend/.env` 一致）、`GEMINI_API_KEY` |
| 已知限制／踩坑 | n8n 2.x 預設擋 Code/Expression node 存取 `$env`，`docker-compose.yml` 已加 `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` 開放，不然 workflow 裡的 `{{$env.xxx}}` 全部會失敗（`access to env vars denied`），本機驗證時發現並記錄，詳見 `docs/ADR/debug/n8n-env-access.md` |
| Webhook 端點 | 匯入 `n8n/workflows/inquiry-flow.json` 後啟用（active），對外路徑 `POST http://localhost:5678/webhook/inquiry` |
| 對外埠 | `5678` |
| Health Check | `GET http://localhost:5678/healthz` |
| 目前無基礎設施 | 沒有另外的 basic auth／對外網址；只在本機 Docker 跑，正式對外使用前應補上驗證 |

## 已知限制（Phase 2 為止）

- 沒有 Docker Compose 統一一鍵啟動 Django + n8n + PostgreSQL + Vue（Phase 7）
- n8n workflow 目前查詢供應商/產品用「名稱精確比對」（`SearchFilter`），還沒有 Phase 3 的遮罩/Token 化與模糊比對 fallback
- `quotes/calculate/` 端點目前只回傳計算結果，不落地寫入 `Quote` 資料列（正式建單留待 Phase 3 幻覺驗證通過後）
