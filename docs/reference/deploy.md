---
title: 部署 Reference
updated: 2026-09-03
---

# 部署 Reference

> 只記現況，不保存敘事歷史；歷史與理由放 ADR。

## 執行平台

本機開發，非公開上線（見 `docs/specs/DRAFT.md` 已擱置的雲端部署討論）。

## Django 後端

| 項目 | 內容 |
| --- | --- |
| 入口 | `backend/manage.py runserver` |
| 必要環境變數 | `DJANGO_SECRET_KEY`、`DJANGO_DEBUG`、`DJANGO_ALLOWED_HOSTS`、`POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_HOST`、`POSTGRES_PORT`、`INTERNAL_API_KEY`、`N8N_INQUIRY_WEBHOOK_URL`、`N8N_INQUIRY_PARSE_WEBHOOK_URL`、`N8N_NOTIFY_WEBHOOK_URL`（FR-6b／FR-8 Gmail 通知，見 `services/notification_service.py`）、`FRONTEND_BASE_URL`（FR-8 通知信附的簽核頁面連結所用，須填使用者瀏覽器可開的前端網址，預設 `http://localhost:5173`，不是容器內部 service 名稱）、`LOAD_DEMO_DATA`（預設 `true`，容器啟動時是否自動跑 `seed_demo_data`，冪等）；`REFRESH_COOKIE_SECURE` 控制本機 HTTP／HTTPS Cookie Secure 屬性。`N8N_RESUME_WEBHOOK_URL` 有預設值但現況（2026-09-02 起）已無程式碼呼叫，屬死設定，見下方 n8n 區塊說明 |
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
| 身分驗證（2026-09-03 起） | `purchase-request-candidate-flow.json`、`notification-flow.json` 的 webhook 節點後方各加了「IF：Internal API Key 正確？」節點，比對呼叫端送來的 `X-Internal-Api-Key` header 是否等於 `INTERNAL_API_KEY` 環境變數，不符合回 401、不繼續執行。修復前這兩支 webhook 沒有任何驗證，任何人連得到 5678 port 就能直接觸發寄信／呼叫 Gemini，詳見 `docs/ADR/debug/phase7-integration.md` |
| Workflow 檔案 | `n8n/workflows/purchase-request-candidate-flow.json`（現行正式流程，2026-09-02 起）：接收 Django 已遮罩好的文字，呼叫 Gemini 純解析成候選結構後原樣回傳（不查詢／不試算），對外路徑 `POST http://localhost:5678/webhook/purchase-request-candidate`，服務 `N8N_INQUIRY_PARSE_WEBHOOK_URL`。`n8n/workflows/notification-flow.json`（FR-6b／FR-8 通知，2026-09-02 新增）：接收 Django 組好的 `{subject, body, recipients, link}` 呼叫 Gmail 節點寄出，對外路徑 `POST http://localhost:5678/webhook/notify`，服務 `N8N_NOTIFY_WEBHOOK_URL`；匯入後需在「寄送 Gmail」節點手動完成一次 Google 帳號 OAuth 授權，無法自動化。`n8n/workflows/inquiry-flow.json` 為 Phase 3 舊版，兩條分支呼叫的 Django 端點皆已於 Phase 5.0-B3A 退場回 `410 Gone`，現況已無任何正式程式碼呼叫，檔案內已加 sticky note 標記，僅供歷史對照。**以上匯入自動化（`n8n-init`／`init-workflows.sh`）只存在於根目錄 `docker-compose.yml`；本節的獨立 `n8n/docker-compose.yml` 沒有對應的自動匯入服務，仍須依上方舊版說明手動匯入。** |
| 對外埠 | `5678` |
| Health Check | `GET http://localhost:5678/healthz` |
| 目前無基礎設施 | 沒有另外的 basic auth／對外網址；只在本機 Docker 跑，正式對外使用前應補上驗證 |
| 與根目錄 Docker Compose 的衝突 | `n8n/docker-compose.yml` 與根目錄 `docker-compose.yml` 的 n8n 服務皆寫死 `container_name: groundtruth-n8n` 且都綁 `5678` port，兩者使用不同 volume（`n8n_data` vs `groundtruth_n8n_data`）；若其中一份啟動過，另一份會在容器建立階段撞名（先啟動者仍在跑則還會先撞 port）。不要交錯或同時啟動這兩份 compose，見 `docs/ADR/debug/phase7-integration.md` 2026-09-03 條目 |

## Docker Compose（根目錄，Phase 7）

| 項目 | 內容 |
| --- | --- |
| 檔案 | 根目錄 `docker-compose.yml`；`backend/Dockerfile`＋`backend/docker-entrypoint.sh`、`frontend/Dockerfile`（build 階段基底映像 `node:22-slim`，因 `frontend/package.json` `packageManager` 釘死 `pnpm@11.25.0` 要求 Node >= 22.13，2026-09-03 起，見 `docs/ADR/debug/phase7-integration.md`）、`n8n/scripts/init-workflows.sh`（`n8n/docker-compose.yml` 仍保留供只需單獨啟動 n8n 的情境使用，不是根目錄 compose 的一部分） |
| 服務 | `postgres`（`postgres:16-alpine`）、`backend`（`docker-entrypoint.sh`：`manage.py migrate` → 視 `LOAD_DEMO_DATA` 決定是否 `seed_demo_data` → `runserver 0.0.0.0:8000`）、`frontend`（Node 建置＋nginx 提供 `dist/` 並反向代理 `/api` 給 `backend` 服務）、`n8n`（`n8nio/n8n:latest`，已加 `/healthz/readiness` healthcheck）、`n8n-init`（一次性服務，等 `n8n` healthcheck 通過後跑 `init-workflows.sh`） |
| 一鍵啟動涵蓋範圍（2026-09-02 起，Codex 建議、Robin 核准） | ①`LOAD_DEMO_DATA=true`（`.env.example` 預設值）時 backend 啟動自動跑 `seed_demo_data`，全用 `get_or_create`，冪等、不清空不覆蓋既有資料；②`n8n-init` 服務自動 `import:workflow` 現行必要的 `purchase-request-candidate-flow.json`／`notification-flow.json`（皆內建固定 `id`，重複匯入是覆寫非新增，冪等），並嘗試自動啟用前者；③Gmail 通知流程刻意只匯入不啟用，Google OAuth 授權與啟用仍須 Robin 手動完成一次（無法自動化）；④legacy `inquiry-flow.json` 不在自動匯入清單內，不會被碰到或啟用 |
| 使用方式 | 複製根目錄 `.env.example` 為 `.env` 填入必要值，於根目錄執行 `docker compose up --build` |
| 對外埠 | backend `8000`、frontend `5173`（對應容器內 nginx `80`）、n8n `5678`、postgres `5432` |
| 容器間連線 | 全部服務在同一個 compose 網路內，彼此以 service 名稱互連（例如 backend 呼叫 n8n 用 `http://n8n:5678`），不是 `host.docker.internal` |
| 已知限制 | Robin 已於 2026-09-03 在真實機器上執行 `docker compose up --build` 完整驗證五服務可一起成功啟動（migration／demo seed／n8n workflow 匯入皆自動完成），過程中修復3 個 Docker 建置問題（Node 版本、pnpm build script 核准、Dockerfile 漏 COPY `pnpm-workspace.yaml`），詳見 `docs/ADR/debug/phase7-integration.md`；`n8n-init` 的自動啟用已改用 `publish:workflow`（取代 deprecated 的 `n8n update:workflow`，2026-09-03 起）；已在真實環境驗證，**跟 `update:workflow` 一樣不可靠**（服務已在跑、CLI 改資料庫但不會通知服務重新註冊 webhook），仍需人工在畫面上切換一次 Active 開關才會真的生效——換指令只是移除 deprecated 警告，沒有解決根本問題；是否投資改用 n8n Public API 做到完全自動化仍待 Robin 決定 |

## 已知限制

- **`docker compose up --build` 已於 2026-09-03 完成真實環境驗證**：見上方 Docker Compose 區塊；demo 種子資料自動建立、n8n workflow 匯入自動完成，唯自動啟用需人工介入一次，詳見 `docs/ADR/debug/phase7-integration.md`
- Phase 4／6 的瀏覽器驗證使用 Vite 本機頁面，未串接 Docker Compose 一起啟動的 Django／n8n 做完整真實環境 E2E；API 流程由 pytest integration tests 驗證
- n8n Gmail 通知（FR-6b／FR-8）：2026-09-03 已用真實 Gmail OAuth 帳號直打 `webhook/notify` 驗證成功收信（recipients 轉換、IF 分流、Gmail 寄送、webhook 回應皆驗證過），但這只證實「n8n 內部這段鏈路」；正式業務路徑「Django 事件（人工複核建立／簽核關卡啟動）→ `notification_service.py`→ n8n → Gmail」尚未端到端驗證過，且 n8n 編輯器裡「Execute step」手動單節點測試目前會卡住無回應（根因未確認，webhook 觸發不受影響）。另外驗證過程發現並修復兩支 n8n webhook 原本完全沒有驗證`X-Internal-Api-Key` 的安全缺口（詳見 `docs/ADR/debug/phase7-integration.md`），修復後已在真實環境驗證：notify／candidate-parse 兩支 webhook 各三種情況（正確 key／錯誤 key／缺少 header）共 6 次請求，結果皆符合預期
