---
title: API Reference
updated: 2026-08-27
---

# API Reference

> 技術參考文件，跟著程式碼異動更新，不是決策紀錄（決策放 `docs/ADR/discuss/`）也不是產品規格
> （放 `docs/specs/SPEC.md`）。Phase 1 的 10 個 CRUD 資源（roles/users/suppliers/products/
> inventory/purchase-suggestions/quotes/approvals/manual-review-queue/audit-logs）為標準 DRF
> ModelViewSet CRUD，不逐一列出；這裡只記錄 Phase 2、Phase 3 新增、行為不是單純 CRUD 的端點。

## 認證方式

| 呼叫方 | 端點範圍 | 認證方式 |
| --- | --- | --- |
| Vue 前端 | 一般 CRUD、`inquiries/trigger/`、`manual-review-queue/{id}/claim/decide/` | Phase 1-3 暫開放 `AllowAny`；JWT 認證於 Phase 4 套用（FR-1a） |
| n8n | `quotes/calculate/`、`masking/mask/`、`masking/mask-amounts-only/`、`masking/unmask/`、`quotes/verify-hallucination/` | 固定 API Key，自訂 header `X-Internal-Api-Key`，需與 `INTERNAL_API_KEY` 環境變數一致（FR-1a） |
| Django（主動呼叫方） | n8n 的 `N8N_RESUME_WEBHOOK_URL`（`POST .../webhook/inquiry/resume`） | 固定 API Key，同上 header；由 Django 主動發起，不是被呼叫端，見 `docs/ADR/discuss/main-flow.md` |

## POST /api/v1/inquiries/trigger/

FR-1：接收自然語言詢價文字，同步呼叫 n8n Webhook（`N8N_INQUIRY_WEBHOOK_URL`），把 n8n 最終回應原樣回傳。

`user_id`：詢價發起人。Vue＋JWT 使用者驗證留待 Phase 4，Phase 3 起先由呼叫端明確帶入（見
`docs/ADR/discuss/main-flow.md`），一路傳給 n8n → `quotes/calculate/` 用來建立 `Quote` 資料列。

**Request**
```json
{ "raw_text": "幫我訂20個A產品，跟優品科技拿貨", "user_id": 1 }
```

**Response（200）**：原樣透傳 n8n workflow 的最終輸出。

**Response（400）**：`user_id` 缺漏。

**Response（502）**：n8n 連線失敗、逾時或回傳非 2xx。
```json
{ "detail": "詢價流程觸發失敗，請稍後再試" }
```

## POST /api/v1/quotes/calculate/

FR-4／FR-4a：固定程式邏輯試算報價金額，比對該供應商＋產品的歷史已核准均價，**並正式建立 `Quote` 資料列**（Phase 3 起：幻覺驗證 `quotes/verify-hallucination/` 需要一個真實存在的 `quote_id` 才能運作，Phase 2 當時只做試算，這裡補上建單）。只給 n8n 呼叫（需要 `X-Internal-Api-Key`），不開放給前端使用者。

**Request Headers**
```
X-Internal-Api-Key: <INTERNAL_API_KEY>
```

**Request Body**
```json
{ "user_id": 1, "product_id": 1, "supplier_id": 1, "quantity": 20 }
```
`user_id`、`product_id`、`supplier_id`、`quantity` 皆為必填（`supplier_id` 在 Phase 2 曾經可省略，Phase 3 起因為要建立 Quote 而改為必填）。

**Response（200）**
```json
{
  "product_id": 1,
  "supplier_id": 1,
  "quantity": 20,
  "unit_price": "1500.00",
  "total_amount": "30000.00",
  "currency": "TWD",
  "price_deviation_pct": "2.39",
  "price_deviation_flag": false,
  "quote_id": 42
}
```
`price_deviation_pct` 為 `null` 代表該供應商＋產品組合過去無已核准紀錄可比較（不視為異常）。
`price_deviation_flag` 為 `true` 代表偏離超過門檻（20%，`services/quote_calculation_service.py` 寫死）。
新建立的 `Quote` 狀態為 `pending_verification`。

**Response（400）**：`user_id`／`product_id`／`supplier_id` 缺漏、`quantity` 非正整數、找不到指定使用者、或找不到指定產品。

**Response（401）**：`X-Internal-Api-Key` 缺漏或錯誤。

## GET /api/v1/suppliers/?search=<name> 、 GET /api/v1/products/?search=<name>

Phase 2 新增 `SearchFilter`（`search_fields=["name"]`），供 n8n 依 LLM 解析出的供應商/產品名稱做查詢，屬既有 CRUD 端點的行為擴充，不是新端點。

## POST /api/v1/masking/mask/

FR-2：n8n Mask 節點呼叫，把使用者原始輸入中的供應商名稱／有金額語境的數字換成 Token（如 `SUP_001`、`AMOUNT_001`），送 LLM 前先脫敏。只給 n8n 呼叫，不開放給前端使用者。對照表只在這次回應中回傳，依 NFR-1 絕不落地寫入 DB。

**Request Headers**
```
X-Internal-Api-Key: <INTERNAL_API_KEY>
```

**Request Body**
```json
{ "raw_text": "跟優品科技採購20個A產品，總金額NT$30,000元", "user_id": 1 }
```
`user_id`：選填，詢價發起人。有帶入時，若結果為 `supplier_fuzzy_match`（寫入複核佇列），會存進 `manual_review_queue.requester`，供核准後 n8n 續傳流程（見下方 `masking/mask-amounts-only/`）帶回原始發起人身分。

**Response（200，`outcome: "masked"`）**：精確比對到剛好 1 間供應商，遮罩成功。
```json
{
  "outcome": "masked",
  "masked_text": "跟SUP_001採購20個A產品，總金額AMOUNT_001",
  "mapping": { "SUP_001": "優品科技", "AMOUNT_001": "NT$30,000元" }
}
```

**Response（200，`outcome: "supplier_fuzzy_match"`）**：精確比對 0 筆但模糊比對有候選，或精確／模糊比對命中 2 筆以上（歧義）。寫入 `manual_review_queue`（`quote_id` 為 null），流程中止，等待人工複核（FR-2b）。
```json
{ "outcome": "supplier_fuzzy_match", "review_id": 12, "candidates": ["優品科技"] }
```
`candidates` 只有剛好 1 筆、且比對到的片段夠長（見 `services/masking_service.py` 的 `LENGTH_SAFETY_RATIO` 長度保險）時，`manual_review_queue.supplier_id` 才會預填系統建議值；其餘情況一律留空，交由人工從 `candidates` 挑選（不猜測、不自動判定）。

**Response（200，`outcome: "supplier_not_found"`）**：精確與模糊比對皆無命中，不寫入 DB，直接回覆使用者。
```json
{ "outcome": "supplier_not_found", "masked_text": null, "mapping": {} }
```

**Response（400）**：`raw_text` 為空。

**Response（401）**：`X-Internal-Api-Key` 缺漏或錯誤。

## POST /api/v1/masking/mask-amounts-only/

FR-6a：供應商模糊比對案件核准後，n8n 續傳流程專用。此時供應商身分已由人工確認，不需要再猜測或比對供應商名稱，只需要重新遮罩金額後送 LLM 解析品項/數量。只給 n8n 呼叫。

**Request Headers**
```
X-Internal-Api-Key: <INTERNAL_API_KEY>
```

**Request Body**
```json
{ "raw_text": "跟優品科採購A產品，數量20，單價1500元" }
```

**Response（200）**
```json
{ "masked_text": "跟優品科採購A產品，數量20，單價AMOUNT_001", "mapping": { "AMOUNT_001": "1500元" } }
```
沒有金額語境數字時 `mapping` 回傳空物件，`masked_text` 等於原文。

**Response（400）**：`raw_text` 為空。

**Response（401）**：`X-Internal-Api-Key` 缺漏或錯誤。

## POST /api/v1/masking/unmask/

FR-2a：n8n Unmask 節點呼叫，LLM 解析完成後立即用對照表還原真實值。只給 n8n 呼叫。

**Request Body**
```json
{ "masked_text": "跟SUP_001採購", "mapping": { "SUP_001": "優品科技" } }
```

**Response（200）**
```json
{ "text": "跟優品科技採購" }
```

## POST /api/v1/quotes/verify-hallucination/

FR-6：比對 LLM 生成的報價摘要文字中的數字與名稱，是否忠實反映真實查詢值；不一致時寫入 `manual_review_queue`（`review_type=hallucination_mismatch`）並中止流程。真實數字／名稱一律從 `quote_id` 指向的 Quote 資料列本身讀取，不信任呼叫端傳入的數字——唯一信任呼叫端傳入的是 `summary_text`（LLM 生成內容，正是這支端點要驗證的對象）。只給 n8n 呼叫。

**Request Headers**
```
X-Internal-Api-Key: <INTERNAL_API_KEY>
```

**Request Body**
```json
{ "quote_id": 42, "summary_text": "優品科技採購A產品，數量20，單價1500，總金額30000元" }
```

**Response（200，通過）**：`quotes.ai_summary_text` 寫入該摘要文字，`quotes.status` 進至 `pending_approval`（FR-7 簽核路由留待後續 Phase）。
```json
{ "passed": true }
```

**Response（200，未通過）**：`quotes.status` 停在 `pending_review`，等待人工複核決議。
```json
{ "passed": false, "reasons": ["摘要文字缺少真實數字：unit_price"], "review_id": 15 }
```

**Response（400）**：`quote_id` 缺漏、或 `summary_text` 為空。

**Response（404）**：找不到指定的 Quote。

**Response（401）**：`X-Internal-Api-Key` 缺漏或錯誤。

## POST /api/v1/manual-review-queue/{id}/claim/

FR-6b：管理員認領複核案件，避免多人同時處理同一案件。認領前 Vue 前端無 JWT 身分（留待 Phase 4），暫用 `user_id` 明確指定認領人；後端仍會驗證該使用者存在且角色為 `admin`（FR-6a：待複核佇列一律指派給管理員角色處理）。

**Request Body**
```json
{ "user_id": 3 }
```

**Response（200）**：回傳更新後的 `manual_review_queue` 資料列（`status` 變為 `claimed`）。

**Response（400）**：`user_id` 缺漏、找不到該使用者、或該使用者非管理員角色。

**Response（409）**：案件已被認領或已結案。

## POST /api/v1/manual-review-queue/{id}/decide/

FR-6a／FR-6c：決議案件（核准／駁回），僅提供 SPEC 定義的有限選項，不開放自由編輯 AI 生成內容後放行；必須是該案件的認領人才能決議。每次決議都寫入 `audit_logs`（`action_type="review_decision"`）。

**Request Body**
```json
{ "user_id": 3, "decision": "approved" }
```
`review_type=supplier_fuzzy_match` 且核准時，若 `manual_review_queue.supplier_id` 尚未預填（多筆候選或長度不安全的情況），必須額外帶 `supplier_id` 明確指定：
```json
{ "user_id": 3, "decision": "approved", "supplier_id": 7 }
```

**核准（`hallucination_mismatch`）**：丟棄 LLM 生成摘要，改用 `services/quote_summary_template.py` 的固定樣板依真實數字組出文字寫回 `quotes.ai_summary_text`，`quotes.status` 進至 `pending_approval`。
**駁回（`hallucination_mismatch`）**：`quotes.status` 改為 `cancelled`（詢價作廢，通知申請人重新送出，Gmail 通知留待 n8n 串接）。
**核准（`supplier_fuzzy_match`）**：確認 `manual_review_queue.supplier_id`；DB 交易確定提交後，Django 主動呼叫 n8n 的 `N8N_RESUME_WEBHOOK_URL`（`POST .../webhook/inquiry/resume`），帶 `review_id`／`raw_input_text`／`user_id`（`manual_review_queue.requester`，原始詢價發起人）／`supplier_id`，交還 n8n 重新走一次「遮罩金額→LLM 解析→查詢→試算→摘要→幻覺驗證」流程（見 `docs/ADR/discuss/main-flow.md`）。呼叫 n8n 失敗（連線問題、逾時、非 2xx）不影響這支 API 本身的核准結果——DB 裡供應商已確認的事實不因外部呼叫失敗而回滾。
**駁回（`supplier_fuzzy_match`）**：不異動供應商欄位，不呼叫 n8n，通知申請人確認供應商全名後重新送出。

**Response（200）**：回傳更新後的 `manual_review_queue` 資料列（`status` 變為 `resolved`）。核准 `supplier_fuzzy_match` 案件時，回應多一個 `resume_triggered`（布林值，非 DB 欄位）：`true` 表示已成功通知 n8n 續傳，`false` 表示通知失敗（決議本身仍然成功，但需要人工確認 n8n 那邊是否要手動觸發）。

**Response（400）**：`user_id`／`decision` 缺漏、`decision` 非 `approved`／`rejected`、或核准模糊比對案件卻缺少可用的 `supplier_id`。

**Response（409）**：案件尚未認領、已結案，或非本人認領。
