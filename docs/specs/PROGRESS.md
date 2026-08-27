---
updated: 2026-08-27
---

# 開發進度

## 時程與任務狀態

| 日期 | 對應 FR | 任務內容 | 開發者 | 狀態 | 備註 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-26 | Phase 1 | Django 專案初始化（`backend/config`、`apps/`、`api/`、`services/`、`repositories/`、`schemas/` 分層目錄） | Claude | 完成 | 依 AGENTS.md 目錄結構慣例 |
| 2026-08-26 | Phase 1 | 建立 9 張表 Migration（roles/users/suppliers/products/inventory/purchase_suggestions/quotes/approvals/manual_review_queue/audit_logs） | Claude | 完成 | Migration 檔為各 app 的 `0001_initial`；`docs/reference/db_schema.md` 已補上編號 |
| 2026-08-26 | Phase 1 | `seed_demo_data` management command 灌入假資料 | Claude | 完成 | 可重複執行（get_or_create），已驗證兩次執行不產生重複資料 |
| 2026-08-26 | Phase 1 | 10 個資源的完整 CRUD REST API（DRF ViewSet + Router，`/api/v1/...`） | Claude | 完成 | Phase 1 暫用 `AllowAny`，JWT 認證（FR-1a）留待後續 Phase |
| 2026-08-26 | Phase 1 | 測試：models、repositories、API CRUD 全流程（pytest + pytest-django） | Claude | 完成 | 19 個測試全過，覆蓋率 83%（`pytest --cov`）；`ruff check` 通過 |
| 2026-08-27 | FR-1a | `lib/authentication.py`：n8n↔Django 內部 API Key 認證（`InternalApiKeyAuthentication`） | Claude | 完成 | 100% 覆蓋率（AGENTS.md 安全邏輯要求），含 401 語意（`authenticate_header`） |
| 2026-08-27 | FR-1 | `POST /api/v1/inquiries/trigger/`：接收自然語言詢價文字，觸發 n8n Webhook | Claude | 完成 | Phase 4 前先 `AllowAny`；n8n 連線失敗回 502 |
| 2026-08-27 | FR-4 | `services/quote_calculation_service.py`：固定程式邏輯試算報價金額 | Claude | 完成 | `POST /api/v1/quotes/calculate/`，只給 n8n 呼叫（API Key 保護），只回傳結果不落地寫入 Quote |
| 2026-08-27 | FR-4a | 歷史均價偏離比對（門檻 20%，寫死於 service） | Claude | 完成 | 無歷史已核准紀錄回傳 `null`，不視為異常 |
| 2026-08-27 | Phase 2 | Suppliers／Products CRUD 加 `SearchFilter`（依名稱查詢） | Claude | 完成 | 供 n8n workflow 依 LLM 解析出的名稱查詢用 |
| 2026-08-27 | Phase 2 | n8n 環境（`n8n/docker-compose.yml`）與主流程 workflow（`n8n/workflows/inquiry-flow.json`） | Claude | 完成 | Webhook → Gemini 解析 → 查供應商/產品 → Django 試算 → 回傳；不含遮罩/幻覺驗證（Phase 3 範圍） |
| 2026-08-27 | Phase 2 | 測試：authentication／quote_calculation_service／inquiry_service／API 端點 | Claude | 完成 | 43 個測試全過，覆蓋率 86%；`ruff check` 通過 |
| 2026-08-27 | Phase 2 | 本機端到端驗證（mock Gemini + 真實 n8n + Django + seed 資料） | Claude | 完成 | 詳見 `docs/ADR/debug/n8n-workflow-authoring-issues.md`；後續使用者用真實 GEMINI_API_KEY 再驗證一次同樣通過（原本的 gemini-2.0-flash 模型已下架，改用 gemini-3.6-flash） |

## 已知待補（非本次 Phase 範圍，記錄避免遺漏）

- JWT 認證（FR-1a 前半，使用者對 Vue 前端）、遮罩/幻覺驗證邏輯（FR-2/FR-2a/FR-2b/FR-6）：Phase 3～4 範圍
- API 目前僅測試 CRUD 正確性，尚未針對 FR 業務規則（如金額門檻、狀態機轉換限制）撰寫驗證測試，將於對應 Phase 補上
- Django 版本：SPEC.md 標註 6.x，但目前 PyPI 最新穩定版為 5.2.x（6.0 尚未釋出），本次以 5.2 落地，待 Django 6.0 正式發布後再評估升級
- `quotes/calculate/` 只回傳計算結果、不落地寫入 `Quote` 資料列；正式建單邏輯待 Phase 3 幻覺驗證通過後補上
- n8n workflow 目前用「名稱精確比對」查供應商/產品，還沒有 Phase 3 的 Token 化遮罩與模糊比對 fallback（FR-2b）

## 推版紀錄

| 日期 | 版本 / commit | 異動摘要 | 開發者 |
| --- | --- | --- | --- |
| 2026-08-26 | 0fc63ae | Phase 1：Django 專案初始化、DB Schema、seed 假資料、完整 CRUD API（commit，尚未 push） | Claude |
| 2026-08-27 | e5ece91 | Phase 2：n8n 環境架設、內部 API Key 認證、詢價試算主流程閉環（commit，尚未 push） | Claude |
| YYYY-MM-DD | | | Claude / Codex / <負責人> |
