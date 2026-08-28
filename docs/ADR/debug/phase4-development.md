---
title: Phase 4 開發環境與安全收尾紀錄
updated: 2026-08-28
---

# Phase 4 開發環境與安全收尾紀錄

## 2026-08-28 測試基線與認證資料完整性

**現象**：專案沒有獨立且可重現的開發測試依賴，既有 Ruff baseline 無法作為乾淨門檻；Phase 4
初版管理員使用者 CRUD 會直接保存輸入密碼，Refresh Session 建立時間也不是資料庫 default。

**排查過程**：建立隔離測試設定後跑完整 Ruff、Migration dry-run 與 coverage；逐項檢查 User serializer、
JWT session model、登入／rotation／重放與簽核路由的未覆蓋分支。

**根因**：Phase 1 的通用 ModelSerializer 沿用明碼欄位寫入行為；新 Session model 初版沿用
`auto_now_add`；舊專案尚未固定 dev dependencies 與 lint 排除範圍。

**修復方式**：新增 `requirements-dev.txt`、`pyproject.toml`、`config/test_settings.py`；User serializer
在 create/update 統一呼叫 Django 密碼雜湊；`refresh_sessions.created_at` 改為 DB `now()` default；
補上錯誤憑證、Token rotation／重放、JWT 使用者失效、簽核門檻與角色限制測試。

**驗證方式**：執行 backend Ruff、Migration check、pytest coverage，以及 frontend lint、test、type-check、build。

**未驗證範圍**：未以同時啟動的 Django、n8n、PostgreSQL 執行瀏覽器真實環境 E2E。
