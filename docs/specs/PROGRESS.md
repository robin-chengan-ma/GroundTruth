---
updated: 2026-08-26
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

## 已知待補（非本次 Phase 1 範圍，記錄避免遺漏）

- JWT 認證（FR-1a）、n8n 串接、遮罩/幻覺驗證邏輯：Phase 2～3 範圍
- API 目前僅測試 CRUD 正確性，尚未針對 FR 業務規則（如金額門檻、狀態機轉換限制）撰寫驗證測試，將於對應 Phase 補上
- Django 版本：SPEC.md 標註 6.x，但目前 PyPI 最新穩定版為 5.2.x（6.0 尚未釋出），本次以 5.2 落地，待 Django 6.0 正式發布後再評估升級

## 推版紀錄

| 日期 | 版本 / commit | 異動摘要 | 開發者 |
| --- | --- | --- | --- |
| 2026-08-26 | 0fc63ae | Phase 1：Django 專案初始化、DB Schema、seed 假資料、完整 CRUD API（commit，尚未 push） | Claude |
| YYYY-MM-DD | | | Claude / Codex / <負責人> |
