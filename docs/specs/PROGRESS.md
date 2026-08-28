---
updated: 2026-08-28
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
| 2026-08-27 | Phase 3 | schema 修正：`manual_review_queue.quote_id` 改為 nullable（migration `0002_alter_manualreviewqueue_quote`） | Claude | 完成 | 開工前發現與 `docs/ADR/discuss/main-flow.md` 定案矛盾，修正並記錄新 ADR 條目 |
| 2026-08-27 | FR-2 | `services/masking_service.py`：供應商名稱／金額 Token 化遮罩（精確比對→模糊比對 fallback） | Claude | 完成 | 100% 覆蓋率；模糊比對加「最長連續相符子字串長度」保險（LENGTH_SAFETY_RATIO 60%），避免「生技」對到「保生技術」這類巧合命中被誤判為高可信度候選（使用者提出） |
| 2026-08-27 | FR-6 | `services/hallucination_check_service.py`：幻覺驗證（金額零容忍＋供應商/產品核心字串比對） | Claude | 完成 | 100% 覆蓋率；驗證失敗時 `quotes.status` 轉為 `pending_review` 並寫入複核佇列 |
| 2026-08-27 | FR-6a | `services/quote_summary_template.py`：核准後取代 LLM 摘要的固定樣板 | Claude | 完成 | 100% 覆蓋率 |
| 2026-08-27 | FR-6a／FR-6b／FR-6c | `services/manual_review_service.py`：複核案件認領／決議（含衝突防呆、稽核 log） | Claude | 完成 | 100% 覆蓋率；認領/決議限定 `admin` 角色（FR-6a） |
| 2026-08-27 | Phase 3 | 新端點：`POST /masking/mask/`、`POST /masking/unmask/`、`POST /quotes/verify-hallucination/`、`POST /manual-review-queue/{id}/claim/`、`POST /manual-review-queue/{id}/decide/` | Claude | 完成 | 前三者僅供 n8n（API Key）；claim/decide 暫 `AllowAny`（JWT 認證留待 Phase 4），已補 `docs/reference/api.md` |
| 2026-08-27 | Phase 3 | 測試：masking_service／hallucination_check_service／manual_review_service／新端點 | Claude | 完成 | 103 個測試全過，整體覆蓋率 98%；Phase 3 安全關鍵模組（masking/hallucination/manual_review/quote_summary_template/lib.authentication）皆 100% |
| 2026-08-27 | Phase 3 | `quotes/calculate/` 改為正式建立 `Quote` 資料列（新增 `create_quote()`），`inquiries/trigger/` 改為必填 `user_id` 並一路往下傳 | Claude | 完成 | 110 個測試全過，整體覆蓋率 98%；`docs/reference/api.md` 已同步 |
| 2026-08-27 | Phase 3 | n8n workflow 全面改版（`groundtruth-inquiry-flow-phase3`，19 個節點）：Mask/Unmask 節點、Gemini 摘要生成（FR-5）、幻覺驗證節點、兩層 IF 分流 | Claude | 完成 | 本機用 mock Django + Gemini 驗證 4 種分支（成功／查無供應商／模糊比對／幻覺驗證失敗）皆通過，詳見 `docs/ADR/debug/n8n-workflow-authoring-issues.md` |
| 2026-08-27 | FR-6a | 供應商模糊比對案件核准後「交還 n8n 重新走遮罩→解析流程」串接：新增 `manual_review_queue.requester` 欄位（migration `0003_manualreviewqueue_requester`）、`services/inquiry_resume_service.py`（Django 主動呼叫 n8n 續傳 Webhook）、`services/masking_service.mask_amounts_only()`、`POST /api/v1/masking/mask-amounts-only/`、`decide_review()` 核准 supplier_fuzzy_match 後觸發 `trigger_resume()` | Claude | 完成 | 架構決策（Django 主動呼叫 n8n webhook，而非 n8n 輪詢）由使用者確認後採用，見 `docs/ADR/discuss/main-flow.md` 新增條目；`inquiry_resume_service.py` 100% 覆蓋率；n8n 呼叫失敗不影響核准決議本身（DB 交易已提交），僅 `resume_triggered` 回傳 `false` |
| 2026-08-27 | FR-6a | n8n workflow 新增「續傳子流程」14 個節點（`Webhook 續傳詢價` → Mask 金額 → Gemini 解析 → 查詢供應商/產品 → Django 試算 → Gemini 摘要 → 幻覺驗證 → 分流回覆），workflow 節點數 19→33 | Claude | 完成 | 本機用 mock Django + Gemini 驗證整段串接（webhook 接收→...→幻覺驗證分流回覆）通過；過程中發現並修正一個 bug：`查詢產品（續傳）` 節點誤用 `$json.item`（前一節點已改為查詢供應商，`$json` 已非解析節點輸出），改用 `$('解析 LLM 輸出（續傳）').first().json.item` 明確引用；詳見 `docs/ADR/debug/n8n-workflow-authoring-issues.md` |
| 2026-08-27 | Phase 3 | 測試：`inquiry_resume_service`／`masking_service`（`mask_amounts_only`、`requester` 相關）／`manual_review_service`（resume 觸發與失敗容錯） | Claude | 完成 | 121 個測試全過，整體覆蓋率 98%；Phase 3 安全關鍵模組皆 100% |
| 2026-08-27 | FR-2b | 補上 FR-2b 第三種遮罩失敗情境（供應商比對成功但其他欄位如金額/數量格式無法解析→即時回覆請求修正格式，不進複核佇列）：主流程與續傳子流程的「解析 LLM 輸出」節點皆改為 try/catch＋`quantity` 數字格式驗證，不再對格式錯誤直接 throw；各新增一個 IF 分流節點與對應回覆節點 | Claude | 完成 | 這段原本重讀 SPEC.md 才發現漏做（FR-2b 三個分支只做了前兩個），補齊後 workflow 節點數 33→37；本機用 mock 驗證主流程與續傳流程的格式錯誤分支皆正確回覆「詢價內容格式無法解析，請確認數量/金額等欄位後重新輸入」，且不寫入複核佇列，其餘 5 種既有分支重新跑過一遍確認未受影響；詳見 `docs/ADR/debug/n8n-workflow-authoring-issues.md` |
| 2026-08-27 | 使用者 | 真實 `GEMINI_API_KEY` 端到端實測（Django + Docker n8n + 真實 Gemini + seed 資料）：正常成功／查無供應商／模糊比對／格式無法解析 4 種分支皆通過，真實摘要文字格式與 mock 假設一致 | Robin | 完成 | 續傳流程實測時發現一個 bug：主流程「Mask 遮罩」節點沒有把 `user_id` 轉傳給 `masking/mask/`，導致 `manual_review_queue.requester` 恆為 `null`，核准後續傳流程的 `quotes/calculate/` 因此收到空的 `user_id` 回 400；已修正並重新推送 workflow，詳見 `docs/ADR/debug/n8n-workflow-authoring-issues.md` |
| 2026-08-27 | 使用者 | 修正後重新實測供應商模糊比對→核准→續傳完整流程 | Robin | 完成 | `manual_review_queue.requester` 正確帶值（不再是 `null`），claim/decide/續傳皆成功，n8n Executions 顯示續傳子流程完整跑到「回覆：成功（續傳）」分支（真實 Gemini 摘要通過幻覺驗證），確認修復生效 |
| 2026-08-28 | Phase 4 基線 | 建立可重現測試環境與 Ruff baseline（`requirements-dev.txt`、`pyproject.toml`、隔離測試設定） | Codex | 完成 | 測試原始碼提交；`node_modules`、coverage、build、cache 等產物排除於 Git |
| 2026-08-28 | FR-1a | email/password 登入、Access/Refresh JWT rotation、撤銷、登出、CSRF 與角色授權 | Codex | 完成 | Access 15 分鐘僅存前端記憶體；Refresh 1 天 HttpOnly SameSite Cookie；資料庫只存雜湊；管理員建立／更新帳號會雜湊密碼 |
| 2026-08-28 | FR-7／FR-7a／FR-8／FR-8a | 金額路由、角色認領、核准／駁回、admin 禁止跨角色代簽 | Codex | 完成 | 小額 ≤10,000；中額 >10,000 且 ≤100,000；大額 >100,000 路由 admin；狀態與 Audit Log 同步 |
| 2026-08-28 | Phase 4 權限 | 工作流程 API 改為唯讀清單＋明確 action，套用本人／路由角色／admin 可視範圍 | Codex | 完成 | employee 僅見本人 Quote；申請人可撤回 pending_approval，正式案件不可通用修改／刪除 |
| 2026-08-28 | Phase 4 前端 | Vue 登入、詢價、採購清單、簽核佇列、人工複核頁與共用狀態呈現 | Codex | 完成 | 響應式桌面／390px 畫面與 browser console 已檢查；當次未啟動 Django，因此屬 UI 驗證，不宣稱真實環境 E2E |
| 2026-08-28 | Phase 4 測試 | Backend pytest/coverage、Ruff、Migration check；Frontend lint/test/type-check/build | Codex | 完成 | Backend 153 tests、整體 95%；JWT／Refresh／簽核路由 100%。Frontend 4 tests；lint、type-check、build 全通過 |

## 已知待補（非本次 Phase 範圍，記錄避免遺漏）

- Django 版本：SPEC.md 標註 6.x，但目前 PyPI 最新穩定版為 5.2.x（6.0 尚未釋出），本次以 5.2 落地，待 Django 6.0 正式發布後再評估升級
- 以下情境的邏輯本身皆有 100% 單元測試覆蓋，但尚未在真實環境（真實 Gemini + 真實 n8n + 真實 Django）端到端跑過一次，原因是這些情境較難用真實 LLM 刻意觸發，非阻擋 Phase 3 完成的問題，記錄供未來需要更完整實測時參考：
  - 幻覺驗證失敗分支（`hallucination_mismatch`）——真實 Gemini 至今每次摘要都準確，未曾實際觸發過
  - 幻覺驗證失敗案件的 claim/decide 核准（套用系統樣板）／駁回（Quote 轉 `cancelled`）
  - 供應商模糊比對案件的駁回（rejected）路徑
- Phase 4 尚未與同時啟動的 Django + n8n + PostgreSQL 做瀏覽器真實環境 E2E；目前以後端 API integration tests、前端元件測試及 Vite 瀏覽器 UI 檢查分別驗證。

## 推版紀錄

| 日期 | 版本 / commit | 異動摘要 | 開發者 |
| --- | --- | --- | --- |
| 2026-08-26 | 0fc63ae | Phase 1：Django 專案初始化、DB Schema、seed 假資料、完整 CRUD API（已 push） | Claude |
| 2026-08-27 | e5ece91 | Phase 2：n8n 環境架設、內部 API Key 認證、詢價試算主流程閉環（已 push） | Claude |
| 2026-08-27 | d94e932 | fix：Gemini 模型過期改用 gemini-3.6-flash，真實端到端驗證通過（已 push） | Claude |
| 2026-08-27 | 933c7c4 | Phase 3：供應商模糊比對案件核准後的 n8n 續傳串接、FR-2b 格式錯誤分流（已 push） | Claude |
| 2026-08-27 | d9898e2 | docs：補上 933c7c4 推版紀錄（已 push） | Robin |
| 2026-08-27 | d4fa4b2 | fix：修正 n8n Mask 遮罩節點未轉傳 user_id 導致續傳流程試算報價失敗（commit，尚未 push） | Robin |
| YYYY-MM-DD | | | Claude / Codex / <負責人> |
