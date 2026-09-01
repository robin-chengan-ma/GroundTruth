---
updated: 2026-09-01
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
| 2026-08-28 | Phase 4 測試 | Backend pytest/coverage、Ruff、Migration check；Frontend lint/test/type-check/build | Codex | 完成 | Backend 166 tests、整體 95%；JWT／Refresh／簽核路由與 inquiry service 100%。Frontend 4 tests；lint、type-check、build 全通過 |
| 2026-08-28 | Phase 4 實測修復 | 修正權限收斂後 n8n 查詢 suppliers/products 回 401，以及空／非 JSON 上游回應造成 500 | Codex | 完成 | 內部 API Key 僅開放唯讀；workflow 主流程／續傳共 4 節點補 header；Robin 由 Vue 建立 Quote #7（9,000 TWD）成功，主流程與簽核路由通過 |
| 2026-08-28 | Phase 4 人工驗收 | Quote #7 小額簽核完整流程 | Robin | 完成 | Alice 採購清單可見、Carol 角色可見、認領、核准均成功；Alice 最終看到 approved，撤回操作不再提供 |
| 2026-08-28 | Phase 4 資料修復 | 回填既有 pending_approval 但缺少 Approval 的簽核路由 | Codex | 完成 | Migration `procurement/0003` 已套用：#4→David、#5→Carol；#6/#7 未重複或變更。Backend 156 tests、Ruff、Migration check 通過，待 Robin 頁面複驗 |
| 2026-08-28 | FR-2b 實測修復 | 阻止 LLM 將「一些／幾個」等模糊數量自行猜成 1 | Codex／Robin | 完成 | Django 與 n8n 雙層驗證；模糊量詞拒絕，並支援「五個／十五件／兩百個」等中文明確整數；Robin 已由 Vue 實測通過，既有簽核路由回填與認領防衝突情境亦確認正常 |
| 2026-08-28 | Phase 4.1 規格 | 企業採購核心升級：多品項、多供應商 RFQ、規格品質評選、逐項得標、RBAC、採購單、收貨驗收與庫存流水 | Codex／Robin | 架構與 Migration 施工契約已定案 | ERD、狀態機、RBAC、Migration 分包、欄位／約束契約、舊 Quote 轉換、風險與回滾方案已記錄；實際套用 Migration 保留獨立核准點 |
| 2026-08-28 | Phase 4.1 A1～A3 | 多角色 RBAC、供應商／品項主檔骨架、版本價格與核准政策 | Codex／Robin | 完成；Migration 已套用開發 DB | 新增 15 tests（含 temporary DB reverse／forward rehearsal）；RBAC／核准政策 Service coverage 100%；Backend 181 passed、Ruff、Migration check 通過；Demo seed 重跑及 RBAC／政策對帳正常，現有 API 尚未切換 |
| 2026-08-28 | Phase 4.1 B1 | 採購需求、多品項明細、必要條件、RFQ 與受邀供應商 Schema | Codex／Robin | 完成；Migration 已套用開發 DB | 新增 6 個 Model／DB 約束測試與 1 個 temporary DB reverse／forward rehearsal；Backend 188 passed、Ruff、Migration check 通過；5 張新表均為 0 筆，未回填舊 Quote、未切換 API |
| 2026-08-28 | Phase 4.1 B2 | 供應商報價版本、報價明細、必要條件結果與評分快照 Schema | Codex／Robin | 完成；Migration 已套用開發 DB | 新增 8 個 Model／DB 約束測試與 B2 reverse／forward rehearsal；Backend 197 passed、Ruff、Migration check、`git diff --check` 通過；5 張新表均為 0 筆，未回填舊 Quote、未切換 API |
| 2026-08-28 | Phase 4.1 B3 | 得標方案／拆量、簽核案件／關卡與採購單快照 Schema | Codex／Robin | 完成；Migration 已套用開發 DB | 新增 5 個 Model／DB 約束測試與 B3 reverse／forward rehearsal；Backend 203 passed、Ruff 通過；6 張新表均為 0 筆，未回填舊 Quote、未切換 API／UI |
| 2026-08-29 | Phase 4.1 B4 | 分批收貨、品質驗收三分法、庫存流水與餘額 Schema | Codex／Robin | 完成；Migration 已套用開發 DB | `erp/0003_receiving_inventory_ledger` 新增 5 表；合格／瑕疵／拒收數量守恆、跨批防超收、合格入庫核對及 append-only 流水由 DB 約束；套用後 Backend 210 passed、Ruff、Migration check、reverse／forward rehearsal、`git diff --check` 通過；5 張新表均為 0 筆，未回填、未切換 API／UI |
| 2026-08-29 | Phase 4.1 B5 | 高流量查詢索引以 PostgreSQL concurrent migration 建立 | Codex／Robin | 完成；Migration 已套用開發 DB | procurement `0008_concurrent_indexes` 採 `atomic=False`＋`SeparateDatabaseAndState`，涵蓋需求狀態、RFQ 到期、供應商邀請、有效報價、簽核佇列與供應商 PO；六條索引均為 valid／ready，套用後 Backend 211 passed、6 項 migration rehearsal、Ruff、Migration check、`git diff --check` 通過；未回填、未切換 API／UI |
| 2026-08-29 | Phase 4.1 C1 | legacy Quote 可逆回填與稽核真實性例外 | Codex／Robin | 完成；Migrations 已套用開發 DB | erp `0004` 僅允許 legacy 收貨／驗收 actor 為空；procurement `0009` 已回填 9 Quotes、9 cases、6 個有真實來源的 steps 與 4 組 approved 收貨鏈。逐筆關聯／金額錯誤 0；4 movements 皆 `affects_balance=false`，legacy 庫存總量套用前後均 82，新 balance 仍 0 筆。六狀態、重跑、reverse 演練與套用後 Backend 214 passed、Ruff、Migration check 通過；未切換 API／UI |
| 2026-08-29 | Phase 4.1 C2／FR-3／FR-17 | 多品項、多候選供應商採購草稿、結構化試算與確認提交 API | Codex／Robin | 後端完成；未切換 UI／n8n | 新增本人 RBAC 草稿 CRUD、draft RFQ 候選供應商、樂觀鎖 version、參考價格／歷史偏離、提交 idempotency；TDD RED 5 failed／GREEN 18 passed，完整 Backend 232 passed、草稿 Service／Repository 合計 coverage 83%、Ruff、Migration check、`git diff --check` 通過；不新增 Migration、不建立 legacy Quote／正式供應商報價／簽核／採購單 |
| 2026-08-29 | Phase 4.1 C3／FR-13／FR-15／FR-17 | 正式 RFQ、版本化供應商報價、期限與必要條件判定 API | Codex／Robin | 後端完成；綜合評分／UI／n8n 尚未切換 | RFQ issue 固定六項權重與回覆期限；報價支援部分品項、後端 Decimal 重算、提交、逾期及 revision；必要條件依宣告型別與固定運算子判斷，waiver 使用獨立權限。TDD RED 6 failed／GREEN 22 passed，完整 Backend 254 passed、C3 Service coverage 86%、Ruff、Migration check、`git diff --check` 通過；不新增 Migration、不建立得標／簽核／採購單 |
| 2026-08-30 | Phase 4.1 C4／FR-15 | 同品項逐項比較、整體彙總與可解釋推薦 API | Codex／Robin | 後端完成；得標／UI／n8n 尚未切換 | 稅額／運費／折扣按明細占比分攤，成本與交期同品項正規化，必要條件阻擋推薦；部分報價只可逐項建議、整單不推薦，同分並列。無正式供應商表現／永續資料時不造假分數，顯示資料完整度。TDD RED 6 failed／GREEN 6 passed，目標回歸 36 passed，C4 Service coverage 91%；完整 Backend 260 passed、Ruff、Migration check、`git diff --check` 通過；不新增 Migration |
| 2026-08-30 | Phase 4.1 C5-1／FR-14／FR-15／FR-17／FR-18 | 人工選商、逐項／拆量分配與得標方案提交 API | Codex／Robin | 後端完成；簽核案件與 PO 留待 C5-2／C5-3 | 支援整單、逐項及同品項拆量；依 C4 分攤後 TWD 成本保存金額快照，阻擋過期／非現行／必要條件未通過報價，非推薦選商強制理由，提交前重驗與 DB trigger 防少配／超配。TDD RED 6 failed／GREEN 7 passed，C4＋C5 目標回歸 18 passed，C5-1 Service coverage 86%；完整 Backend 267 passed、Ruff、Migration check、`git diff --check` 通過；不新增 Migration |
| 2026-08-30 | Phase 4.1 C5-2／FR-15／FR-18 | waiver 雙人覆核、正式金額簽核與佇列 API | Codex／Robin | 後端完成；Migrations 已套用開發 DB；Vue／n8n 尚未切換 | `0010` 建立 waiver 角色、關卡類型與正規化對照；`0011` 加入獨立 rejected 狀態。Award submit 現會原子化建立政策快照與依序關卡；完成角色佇列／稽核唯讀、row lock 認領、申請人禁止自簽、原 waiver 人禁止再審、跳關阻擋、理由必填、核准／駁回轉態與 Audit Log。TDD RED 8 failed／GREEN／REFACTOR 13 passed，C5-2 Service coverage 90%，C5-1／C5-2／Migration 目標回歸 29 passed，完整 Backend 282 passed；Ruff、Migration check、`git diff --check` 通過；PO 留待 C5-3 |
| 2026-08-30 | Phase 4.1 C5-3／FR-10／FR-17／FR-18 | 依得標供應商拆分正式採購單、快照與發單 API | Codex／Robin | 後端完成；Vue／n8n 尚未切換；收貨驗收 Service 留待後續 | 最終簽核於同一 transaction 建立每供應商一張 draft PO，並將 Request 轉為 ordered；PO item 保存需求規格與得標 TWD 金額快照，既有 PO 不完整或金額快照漂移時整筆回滾。提供本人／管理／稽核可視範圍及 `purchase_order.manage`＋version 發單；建單與發單不增加現有庫存或建立入庫 movement，在途快照後由 C6-1 接管。TDD RED 6 failed／GREEN／REFACTOR 8 passed，PO Service coverage 81%，C5 目標回歸 42 passed，完整 Backend 290 passed；Ruff、Migration check、`git diff --check` 通過；不新增 Migration |
| 2026-08-30 | Phase 4.1 C6-1／FR-10／FR-18 | 已發出 PO 的分批收貨草稿、送驗與在途快照 | Codex／Robin | 後端完成；品質決議與合格入庫留待 C6-2 | `receipt.record` 可對 issued／partially_received PO 分批建立收貨草稿；PO row lock／DB trigger 防競態超收，收貨 version 防重複送驗。發單增加在途快照，送驗扣除實收在途量，全程不增加 on-hand 且不建立 movement。TDD RED 7 failed／GREEN／REFACTOR 19 passed，Goods Receipt Service 85%／Inventory Balance Service 97%；完整 Backend 301 passed，Ruff、Migration check、`git diff --check` 通過；不新增 Migration |
| 2026-08-30 | Phase 4.1 C6-2／FR-4／FR-10／FR-18 | 品質驗收、合格入庫與 PO／需求狀態彙總 | Codex／Robin | 後端完成；退貨、補交、差異結案與採購建議留待 C6-3 | `inspection.decide` 與收貨人職責分離；整批驗收強制三分數量守恆，僅合格數量建立 append-only `receipt_accept` movement 並增加 on-hand。version＋row lock 防重複過帳，驗收／流水／餘額／狀態同 transaction；部分合格或拒收維持 partially_received。TDD RED 8 failed／GREEN／REFACTOR 10 passed，C6-2 Service 組合 coverage 94%；完整 Backend 311 passed，Ruff、Migration check、`git diff --check` 通過；不新增 Migration |
| 2026-08-30 | Phase 4.1 C6-3A／FR-4／FR-10／FR-10a | 驗收差異、補交授權與採購建議追蹤 Schema | Codex／Robin | 完成；Migrations 已套用開發 DB；業務 API 留待 C6-3B／C6-3C | erp `0005` 建立差異案件、拆量明細與補交額度防線，`0006` forward-only 補齊欄位註解；DB 阻擋一般超收、補交超額、未完整分配及正式明細覆寫。採購建議加入 in_progress、來源 movement 與轉單關聯。TDD RED 1 failed／GREEN 3 passed；完整 Backend 314 passed，Ruff、Migration check、`git diff --check` 通過；既有資料不回填 |
| 2026-08-30 | Phase 4.1 C6-3B 前置／FR-10 | 差異明細受控完成與補交案件狀態防線 | Codex／Robin | 完成；Migration 已套用開發 DB；C6-3B API 尚未開發 | erp `0007` 保持正式明細核心內容不可覆寫，只允許附完成者與時間的 `pending → completed`；補交收貨限於 open 案件的 pending replacement 明細。TDD RED 2 failed／GREEN 差異防線 4 passed，Migration reverse／forward 1 passed；完整 Backend 317 passed，Ruff、Migration check、`git diff --check` 通過 |
| 2026-08-30 | Phase 4.1 C6-3B 前置／FR-10 | 差異案件結案狀態防線 | Codex／Robin | 完成；Migration 已套用開發 DB；C6-3B API 尚未開發 | erp `0008` 限制差異案件僅能由 open 轉 closed，且全部明細必須 completed，結案人與時間必填。TDD RED 確認舊 DB 錯誤放行；GREEN 防線＋Migration reverse／forward 6 passed；完整 Backend 319 passed，Ruff、Migration check、`git diff --check` 通過 |
| 2026-08-30 | Phase 4.1 C6-3B／FR-10／FR-18 | 差異案件草稿、查詢與送出 API | Codex／Robin | 後端第一段完成；處理 command／補交／結案待下一段 | Buyer 以 `purchase_order.manage` 管理草稿並送出；Inspector／Receiver／Auditor 唯讀。實作 version、唯一案件、正數三位小數、理由必填、送出數量守恆與正式內容鎖定；TDD RED 5 failed／GREEN 5 passed，Service／Repository 組合 coverage 84%，完整 Backend 324 passed，Ruff、Migration check、`git diff --check` 通過 |
| 2026-08-30 | Phase 4.1 C6-3B／FR-10／FR-18 | 差異處理、補交複驗、結案與單據狀態回推 | Codex／Robin | 後端第二段完成；C6-3B 完成，Vue／n8n 尚未切換 | Buyer 可完成 return／credit／waive，未入庫差異不建立扣庫流水；replacement 僅能由 Receiver 依授權收貨、Inspector 複驗合格後自動完成，補交不重扣原 PO 在途量。全明細完成後 Buyer 才可結案；累計合格量不足但商務差異全數完成時 PO 轉 closed，同需求 PO 全部 received／closed 後 Request completed。TDD RED 3 failed／GREEN 8 passed；C6-3B 第二段相關 Service／Repository 組合 coverage 80%，目標回歸 34 passed，完整 Backend 327 passed；Ruff、Migration check、`git diff --check` 通過；不新增 Migration |
| 2026-08-30 | Phase 4.1 C6-3C／FR-10a／FR-10b | 低庫存採購建議、轉需求與狀態追蹤 | Codex／Robin | 後端完成；Vue 尚未切換 | 庫存過帳後以 on-hand－reserved＋in-transit 比對門檻，pending／in_progress 去重並保留來源 movement。具建單權限者可指定候選供應商轉為本人草稿；提交後 in_progress，需求完成後 processed，admin 可 dismissed 未轉單建議。TDD RED 4 failed／GREEN 4 passed，整合回歸 40 passed，C6-3C／庫存 Service 組合 coverage 90%；完整 Backend 331 passed，Ruff、Migration check、`git diff --check` 通過；不新增 Migration |
| 2026-08-30 | Phase 4.1 D1／FR-1a／FR-16a／FR-18 | 多角色權限導覽、垂直 App Shell 與前端共用基礎 | Codex／Robin | 程式與自動測試完成；待 Robin 登入後桌面／390px 目視 | login／auth-me 回傳生效多角色 permission codes；route guard 與可收合垂直導覽共用同一權限定義，780px 以下改為背景／Escape 可關閉抽屜。新增 PageHeader、API 錯誤與金額／數量／日期格式基礎。TDD RED Backend 3 failed／Frontend 3 failed，GREEN Backend auth 12 passed，Frontend 11 passed；完整 Backend 332 passed，Frontend type-check／ESLint／production build、Ruff、Migration check 通過；不新增 Migration |
| 2026-08-31 | Phase 4.1 D2／FR-3／FR-4a／FR-9b／FR-16b | 自然語言候選結構、可編輯確認、多供應商試算與本人需求清單 | Codex／Robin | 完成；Robin 真實環境主流程與修復後瀏覽器驗收通過 | 新增 `inquiries/parse/` 只回候選資料且不建單；n8n v2 已由 Robin 完成 Header Auth、Gemini 結構化輸出、空值分流、重試與 production webhook 發佈，正常多供應商／多品項、缺數量 null、空輸入 400 均實測通過。Vue 完成「解析 → 確認／修正 → 儲存草稿並試算 → 提交」；實測後補上提交成功重置、5 秒可關閉提示與查看入口、無有效價格顯示「尚無報價」，並將「我的採購需求」切換為本人 `purchase_requests`、建立時間與新到舊排序；Robin 已逐項確認修復結果正常。TDD RED：新清單 API 404、舊畫面未重置／顯示零元；GREEN：目標 Backend 1 passed、Frontend 4 passed；完整 Backend 338 passed、Frontend 15 passed，type-check／ESLint／production build、Ruff、Django check、Migration check 通過。n8n workflow JSON 依 ignore／敏感資料規則不由 AI 讀取或提交；不新增 Migration |

| 2026-08-31 | Phase 5.0／FR-1a／FR-2／FR-6a／FR-16～FR-19／NFR-1 | 應用切換與安全收斂 | Codex／Robin | P5.0-A 與 P5.0-B1／B2 支援切片完成；P5.0-B command 主切換及 P5.0-C～E 尚未開發 | 新版候選解析改為 Django 先遮罩多間已知供應商與金額、n8n 回傳後於單次請求遞迴還原；未知、混合已知／未知及模糊供應商不得把原始名稱送至 n8n。TDD RED 4 failed；GREEN 目標 44 passed、遮罩 Service coverage 100%、候選解析 Service 87%、兩者合計 94%；完整 Backend 344 passed，Ruff、Django check、Migration check、`git diff --check` 通過；不新增 Migration。Robin 從 Vue 輸入兩間供應商、兩品項與預算，確認 LLM Input 僅含 `SUP_001`／`SUP_002`／`AMOUNT_001`，LLM Output 保留供應商 Token，Django 正確還原兩間候選供應商。本人需求分頁與唯讀詳情屬於 P5.0-B 的支援切片；下一步仍須完成 legacy command 主切換，後續依 `docs/ADR/discuss/phase5.md` 執行 P5.0-C～E |
| 2026-08-31 | P5.0-A2／FR-3 | 未匹配品項提示、刪除確認與最後一項重設 | Codex／Robin | 完成；功能、資訊層級與必填紅框均通過 Robin 瀏覽器驗收 | 每項顯示 AI 辨識摘要；未匹配正式品項時顯示警告與試算停用原因。移除任何品項均先確認，移除後清除試算；最後一項移除時同步刪除已存後端草稿並回到自然語言輸入畫面。依實測畫面將匹配狀態、辨識摘要、單筆警告與按鈕停用原因分層，並依後端規則將缺少的候選供應商、正式品項與正數數量以紅框及文字說明標示；Robin 已確認最終畫面正常。TDD RED 先後 3 failed、1 failed；GREEN 目標 7 passed；完整 Frontend 19 passed，type-check、ESLint、production build 通過；不修改 n8n、不新增 Migration |
| 2026-08-31 | P5.0-A3／FR-3 | 原句正式品項安全補回與供應能力矩陣 | Codex／Robin | 完成；通過 Robin 真實 n8n／瀏覽器驗收 | 修復 LLM 將 `A產品-辦公椅` 簡化為 `辦公椅` 後無法媒合：只有原句明確包含生效正式品名且候選唯一時才補回，歧義情境維持未匹配。新增受 `purchase_request.create` 控制的供應能力查詢，Vue 逐品項顯示候選供應商的有效價格、無價格、未建關係、停用、品質禁止或條件式合格狀態，選項變更時重新查詢；矩陣僅供確認、不阻擋草稿。TDD RED：品項 1 failed、矩陣 API 2 failed；GREEN 目標 Backend 26 passed、Frontend 8 passed；完整 Backend 349 passed、Frontend 20 passed，Ruff、Django check、Migration check、type-check、ESLint、production build 通過；Robin 已以指定自然語言完成實測；不修改 n8n、不新增 Migration |
| 2026-09-01 | P5.0-B1／B2／FR-9b | 本人需求伺服器分頁與唯讀詳情彈窗 | Codex／Robin | 程式與自動測試完成；待 Robin 瀏覽器驗收 | 本人清單支援每頁 10／20／50 筆、預設 20 筆，頁碼與每頁筆數保存在 URL；申請編號以保留清單背景的彈窗顯示本人需求、候選供應商與完整品項快照，支援凸出右上角的紅底白色關閉圖示、背景遮罩及 `Esc` 關閉，長內容只捲動彈窗；詳情網址可重新整理，非本人與不存在資源統一 404。開發前依 Robin 確認清空本機採購交易測試資料並重設流水號，保留 7 個帳號、8 個角色、5 間供應商、6 個品項、6 筆庫存及 3 筆簽核政策；資料庫內容未提交 Git。TDD RED：Backend 3 個功能失敗、Frontend 2 個清單失敗、1 個詳情缺檔及 1 個彈窗行為失敗；GREEN 目標 Backend 4 passed、Frontend 4 passed；完整 Backend 352 passed、Frontend 23 passed，Ruff、Django check、Migration check、type-check、ESLint、production build、`git diff --check` 通過；不新增 Migration、不修改 n8n |
| 2026-09-01 | P5.0-B3A／FR-16b | 停止 legacy inquiry／Quote 建單鏈 | Codex／Robin | 完成；Robin API 與新版流程驗收通過 | `POST /inquiries/trigger/`、`POST /quotes/calculate/`、`POST /quotes/verify-hallucination/` 通過既有認證後統一回 410／`legacy_command_retired`，不再呼叫 n8n、建立或推進 legacy Quote。未認證請求仍回 401；新版候選解析與 Purchase Request 流程不受影響。TDD RED 3 failed；GREEN 目標與受影響 Phase 2～4 API 共 28 passed；完整 Backend 343 passed，Ruff、Django check、Migration check 通過；Robin 已確認 legacy command 認證後回 410／`legacy_command_retired`，且新版採購需求主流程正常。不新增 Migration、不修改 n8n。舊簽核及人工複核 action 待 P5.0-C 切換後再封鎖 |

## 已知待補（非本次 Phase 範圍，記錄避免遺漏）

- Django 版本：SPEC.md 標註 6.x，但目前 PyPI 最新穩定版為 5.2.x（6.0 尚未釋出），本次以 5.2 落地，待 Django 6.0 正式發布後再評估升級
- 以下情境的邏輯本身皆有 100% 單元測試覆蓋，但尚未在真實環境（真實 Gemini + 真實 n8n + 真實 Django）端到端跑過一次，原因是這些情境較難用真實 LLM 刻意觸發，非阻擋 Phase 3 完成的問題，記錄供未來需要更完整實測時參考：
  - 幻覺驗證失敗分支（`hallucination_mismatch`）——真實 Gemini 至今每次摘要都準確，未曾實際觸發過
  - 幻覺驗證失敗案件的 claim/decide 核准（套用系統樣板）／駁回（Quote 轉 `cancelled`）
  - 供應商模糊比對案件的駁回（rejected）路徑
- Phase 4 已完成 Vue + Django + n8n + PostgreSQL 的小額詢價真實環境 E2E；中額／大額簽核、撤回與人工複核各分支仍待 Robin 逐項驗收。

## Commit 紀錄

| 日期 | 版本 / commit | 異動摘要 | 開發者 |
| --- | --- | --- | --- |
| 2026-08-26 | 0fc63ae | Phase 1：Django 專案初始化、DB Schema、seed 假資料、完整 CRUD API | Claude |
| 2026-08-27 | e5ece91 | Phase 2：n8n 環境架設、內部 API Key 認證、詢價試算主流程閉環 | Claude |
| 2026-08-27 | d94e932 | fix：Gemini 模型過期改用 gemini-3.6-flash，真實端到端驗證通過 | Claude |
| 2026-08-27 | 933c7c4 | Phase 3：供應商模糊比對案件核准後的 n8n 續傳串接、FR-2b 格式錯誤分流 | Claude |
| 2026-08-27 | d9898e2 | docs：補上 933c7c4 推版紀錄 | Robin |
| 2026-08-27 | d4fa4b2 | fix：修正 n8n Mask 遮罩節點未轉傳 user_id 導致續傳流程試算報價失敗 | Robin |
| 2026-08-27 | 0a2edef | docs：補上 d4fa4b2 紀錄並修正 push 狀態 | Robin |
| 2026-08-28 | 1624b1a | Phase 4：企業式 JWT、權限收斂、簽核流程與 Vue 核心頁面 | Codex |
| 2026-08-28 | da90800 | docs：補記 Phase 4 commit 版號 | Robin |
| 2026-08-28 | cc39aba | fix：完善詢價防呆與企業採購規格 | Robin |
| 2026-08-31 | fc0d9e9 | Phase 4.1：企業採購閉環、自然語言需求確認與本人採購需求清單 | Codex／Robin |
| 2026-08-31 | 80362dd | P5.0-A：修復新版需求解析敏感資料遮罩 | Codex／Robin |
| 2026-08-31 | 180a517 | P5.0-A2／A3：完善候選品項媒合與供應能力矩陣 | Codex／Robin |
| 2026-09-01 | e2f8296 | P5.0-B1／B2：需求分頁與唯讀詳情彈窗 | Codex／Robin |
| YYYY-MM-DD | | | Claude / Codex / <負責人> |

## Push／部署狀態

| 日期 | 版本 | Push 狀態 | 部署狀態 |
| --- | --- | --- | --- |
| 2026-08-28 | da90800 | Robin 已推版（`origin/main`） | 尚未部署 |
| 2026-08-28 | ec5d0d5 | Robin 已推版（包含 `cc39aba`） | 尚未部署 |
| 2026-08-31 | 9689540 | Robin 已推版（`origin/main`，包含 `fc0d9e9`） | 尚未部署 |
| 2026-09-01 | 80362dd | Robin 已推版（`origin/main`） | 尚未部署 |
| 2026-09-01 | 180a517 | Robin 已推版（`origin/main`） | 尚未部署 |
| 2026-09-01 | e2f8296 | Robin 已推版（`origin/main`，文件紀錄至 `be9e525`） | 尚未部署 |
