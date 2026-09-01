---
title: API Reference
updated: 2026-09-01
---

# API Reference

> 技術參考文件，跟著程式碼異動更新，不是決策紀錄（決策放 `docs/ADR/discuss/`）也不是產品規格
> （放 `docs/specs/SPEC.md`）。Phase 4 起 API 已依資源套用 JWT 與角色權限；工作流程資源改為
> 唯讀清單／明確 action，不再允許用通用 CRUD 任意改寫正式狀態。

## 認證方式

| 呼叫方 | 端點範圍 | 認證方式 |
| --- | --- | --- |
| Vue 前端 | `/auth/*`、一般資源、`inquiries/trigger/`、簽核／複核 action | Access Token 放記憶體並以 `Authorization: Bearer <token>` 傳送；Refresh Token 僅存 HttpOnly、SameSite=Lax Cookie，refresh/logout 另驗證 `X-CSRFToken` |
| n8n | suppliers/products 唯讀查詢、`quotes/calculate/`、`masking/mask/`、`masking/mask-amounts-only/`、`masking/unmask/`、`quotes/verify-hallucination/` | 固定 API Key，自訂 header `X-Internal-Api-Key`，需與 `INTERNAL_API_KEY` 環境變數一致（FR-1a） |
| Django（主動呼叫方） | n8n 的 `N8N_RESUME_WEBHOOK_URL`（`POST .../webhook/inquiry/resume`） | 固定 API Key，同上 header；由 Django 主動發起，不是被呼叫端，見 `docs/ADR/discuss/main-flow.md` |

## Vue 登入與 Session

| Method / Route | 認證 | Request | Response／規則 |
| --- | --- | --- | --- |
| `POST /api/v1/auth/login/` | 無 | `{"email":"employee@example.com","password":"example-only"}` | 200 回 `access` 與 `id/name/email/role/permissions`；`permissions` 為所有生效 UserRole 合併、去重且排序的權限碼。設定 Refresh HttpOnly Cookie 與 CSRF Cookie。帳號不存在或密碼錯誤統一回 401 `帳號或密碼錯誤` |
| `POST /api/v1/auth/refresh/` | Refresh Cookie + `X-CSRFToken` | 無 | 200 回新 `access` 並 rotation Refresh Cookie；舊 Token 立即撤銷。CSRF 錯誤回 403，Token 缺漏／失效／重放回 401 |
| `POST /api/v1/auth/logout/` | Refresh Cookie + `X-CSRFToken` | 無 | 撤銷目前 Refresh Session、刪除 Cookie，回 204；無 Cookie 時維持冪等 |
| `GET /api/v1/auth/me/` | Bearer Access Token | 無 | 200 回 `id/name/email/role/permissions`；權限來自目前有效的多角色 RBAC；無效或過期 Token 回 401 |

Access Token 有效 15 分鐘，Refresh Token 有效 1 天。資料庫只保存 Refresh Token 的 SHA-256 雜湊與
rotation／撤銷狀態，不保存 Token 明文。

## 前端資源權限

| 資源 | 可視範圍 | 可寫入範圍 |
| --- | --- | --- |
| roles、users | admin | admin CRUD；密碼寫入時由後端雜湊 |
| suppliers、products | 已登入使用者；n8n 可用內部 API Key 唯讀查詢 | 僅 admin 可用通用 CRUD 寫入；內部服務不可寫入 |
| inventory | 已登入使用者 | 僅 admin 可用通用 CRUD 寫入 |
| purchase-suggestions | 已登入使用者 | 通用 API 唯讀；具 `purchase_request.create` 可轉單，僅 admin 可忽略未轉單建議 |
| quotes | employee 僅本人；簽核人可見路由至其角色的案件；admin 可見全部 | 通用 API 唯讀；本人僅能呼叫 `withdraw` 撤回待簽核案件 |
| approvals | 簽核人可見路由至其角色及本人認領案件；admin 可見全部 | 通用 API 唯讀；只能用 `claim`／`decide` action，且不得跨角色代簽 |
| purchase-request-drafts | 具 `purchase_request.read_own` 者只見本人草稿 | create／edit_draft／submit 分別檢查對應 RBAC；只有 draft 可修改或刪除 |
| purchase-requests | 具 `purchase_request.read_own` 者只見本人全部需求 | 唯讀清單；正式狀態異動必須使用各流程明確 action，不提供通用 CRUD |
| rfqs、supplier-quotes | 具 `rfq.manage`／`supplier_quote.manage` 的採購人員 | RFQ 只能由明確 issue action 發出；報價只能建立草稿、提交或建立 revision，不提供通用更新／刪除 |
| quote-requirement-results | 採購人員於報價提交後讀取評估結果 | 只有 `requirement.waive` 可對 fail／not_provided 填理由例外核准 |
| goods-receipts | 申請人只見自己需求；`receipt.record`、`inspection.decide`、`audit.read` 可見全部 | 只有 `receipt.record` 可建立草稿與送驗；不開放通用更新／刪除 |
| inspection-variances | `purchase_order.manage`、`receipt.record`、`inspection.decide`、`audit.read` 可唯讀全部 | 只有 `purchase_order.manage` 可建立、修改／刪除草稿與送出；正式案件不可以通用 CRUD 改寫 |
| manual-review-queue、audit-logs | admin | 複核僅 `claim`／`decide`；audit logs 全部唯讀 |

## 採購需求草稿 API

全部端點使用 Bearer Access Token。候選供應商保存於 `status=draft` 的 RFQ；尚未正式邀價，不建立 legacy
Quote、Supplier Quote、簽核或採購單。

| Method / Route | 必要權限 | Request／規則 | 成功回應 |
| --- | --- | --- | --- |
| `GET /api/v1/purchase-request-drafts/` | `purchase_request.read_own` | 無；只列本人 draft | 200 草稿陣列 |
| `GET /api/v1/purchase-request-drafts/{id}/` | `purchase_request.read_own` | 非本人或非 draft 統一回 404 | 200 完整草稿 |
| `POST /api/v1/purchase-request-drafts/` | `purchase_request.create` | `purpose`、`currency`、一至多筆 `items`、一至多個 `supplier_ids` | 201 完整草稿 |
| `PATCH /api/v1/purchase-request-drafts/{id}/` | `purchase_request.edit_draft` | 必帶目前 `version`；可更新目的、日期、幣別、完整明細或候選供應商 | 200 新版本草稿 |
| `DELETE /api/v1/purchase-request-drafts/{id}/` | `purchase_request.edit_draft` | 只允許本人 draft；先移除 draft RFQ 再刪除草稿 | 204 |
| `POST /api/v1/purchase-request-drafts/{id}/preview/` | `purchase_request.read_own` | `{"version":1}`；不寫入正式單據 | 200 結構化供應商／品項試算 |
| `POST /api/v1/purchase-request-drafts/{id}/submit/` | `purchase_request.submit` | `version` 與唯一 `idempotency_key` 必填 | 200；狀態轉 `submitted`，相同 key 重送回相同結果 |

建立範例（假資料）：

```json
{
  "purpose": "辦公設備汰換",
  "currency": "TWD",
  "supplier_ids": [101, 102],
  "items": [
    {"product_id": 201, "quantity": "5", "specifications": {"material": "網布"}},
    {"product_id": 202, "quantity": "3"}
  ]
}
```

數量必須大於 0、最多三位小數；`currency` 為 ISO 4217 三碼幣別，`needed_by` 為 `YYYY-MM-DD`；品項與
供應商必須存在、啟用且允許新交易。一般使用者建立的 `source` 固定為 `manual`，不信任 Request 傳入值。
缺少可由使用者補充的欄位時
回 400：

```json
{
  "detail": "採購需求資料不完整，請補充標示欄位",
  "code": "clarification_required",
  "missing_fields": ["supplier_ids", "items.0.quantity"]
}
```

版本落後回 409 `version_conflict`；無 RBAC 回 403 `permission_denied`；非本人資源回 404。Preview 的
`status=estimate_only` 明確表示參考試算；有效價格取符合供應商、品項、幣別、數量級距與有效期間的最新版本。
歷史偏離基準只採 `issued/partially_received/received/closed` 採購單明細；無有效價格或歷史資料時回傳可讀提示。

## 本人採購需求清單 API

### GET `/api/v1/purchase-requests/`

**認證／權限**：Bearer Access Token；需 `purchase_request.read_own`。只回傳 JWT 使用者本人建立的 Purchase Request，依 `created_at`、`id` 新到舊排序；不混入 legacy Quote。

**Query Parameters**：

| 名稱 | 必填 | 規則 |
| --- | --- | --- |
| `page` | 否 | 正整數，預設 `1` |
| `page_size` | 否 | 只允許 `10`、`20`、`50`，預設 `20` |

**Response（200，假資料）**：

```json
{
  "count": 21,
  "page": 2,
  "page_size": 10,
  "total_pages": 3,
  "results": [
    {
      "id": 1201,
      "request_no": "PR-EXAMPLE-001",
      "purpose": "辦公設備汰換",
      "item_summary": "辦公椅、升降桌",
      "supplier_summary": "範例科技、示例物產",
      "requester_name": "範例使用者",
      "created_at": "2026-08-31T08:00:00+08:00",
      "status": "submitted"
    }
  ]
}
```

`page` 或 `page_size` 格式／範圍不合法回 400 `invalid_pagination`；沒有權限回 403；Token 缺漏或失效回 401。此端點只提供本人清單，不接受 POST。

### GET `/api/v1/purchase-requests/{id}/`

**認證／權限**：Bearer Access Token；需 `purchase_request.read_own`。只允許查看本人建立的 Purchase Request；非本人與不存在資源統一回 404。

**Response（200，假資料）**：

```json
{
  "id": 1201,
  "request_no": "PR-EXAMPLE-001",
  "status": "submitted",
  "purpose": "辦公設備汰換",
  "needed_by": "2026-09-30",
  "currency": "TWD",
  "source": "manual",
  "requester_name": "範例使用者",
  "candidate_suppliers": [
    {"supplier_id": 101, "supplier_name": "範例科技"}
  ],
  "items": [
    {
      "id": 1301,
      "line_no": 1,
      "product_id": 201,
      "product_name": "辦公椅",
      "description_snapshot": "網布辦公椅",
      "specifications": {"material": "網布"},
      "quantity": "5.000",
      "unit_of_measure": "EA"
    }
  ],
  "created_at": "2026-08-31T08:00:00+08:00",
  "updated_at": "2026-08-31T08:05:00+08:00"
}
```

詳情包含需求欄位、候選供應商與完整品項快照，僅供唯讀追溯；PATCH／PUT／DELETE 回 405。

## 採購建議 API

| Method / Route | 必要權限 | Request／規則 | 成功回應 |
| --- | --- | --- | --- |
| `GET /api/v1/purchase-suggestions/` | 已登入 | 無；回傳品項、建議數量、狀態、來源 movement 與轉成的 request | 200 建議陣列 |
| `GET /api/v1/purchase-suggestions/{id}/` | 已登入 | 通用資源唯讀 | 200 建議詳情 |
| `POST /api/v1/purchase-suggestions/{id}/convert/` | `purchase_request.create` | `supplier_ids` 為非空、不重複的有效供應商 ID；可傳 `purpose`、`needed_by`、`currency`；僅 pending 且尚未轉單可執行 | 201；建立本人 Purchase Request draft 並回傳 `purchase_request_id` |
| `POST /api/v1/purchase-suggestions/{id}/dismiss/` | admin | 無；僅 pending 且尚未轉單可執行 | 200；狀態轉 dismissed |

轉單與忽略都使用 transaction 及 row lock；競態、重複轉單、非 pending 或已綁定草稿回 409，無權限回 403，資源不存在回 404，供應商或格式無效回 400。轉成的草稿提交後建議轉 in_progress；對應需求 completed 後轉 processed。

## 正式 RFQ 與版本化供應商報價 API

全部端點使用 Bearer Access Token。正式 RFQ 及報價只提供明確 command，不開放通用 PATCH／DELETE。

| Method / Route | 必要權限 | Request／規則 | 成功回應 |
| --- | --- | --- | --- |
| `POST /api/v1/rfqs/{id}/issue/` | `rfq.manage` | `version`、未來的 ISO 8601 `response_due_at`；只允許 submitted Purchase Request 的 draft RFQ | 200；RFQ 轉 issued、需求轉 sourcing、RFQ version +1 |
| `POST /api/v1/supplier-quotes/` | `supplier_quote.manage` | `rfq_supplier_id`、幣別、匯率及一至多筆報價明細；RFQ 必須仍在收件期限內 | 201 報價草稿 |
| `POST /api/v1/supplier-quotes/{id}/submit/` | `supplier_quote.manage` | 無 Body；後端重新檢查 RFQ／報價期限並產生條件結果 | 200；報價轉 submitted、邀請轉 responded |
| `POST /api/v1/supplier-quotes/{id}/revise/` | `supplier_quote.manage` | 新版完整 `items`，其他商務欄位可覆寫；只允許 submitted／accepted_for_evaluation | 201 新 draft revision，舊版轉 revised |
| `POST /api/v1/quote-requirement-results/{id}/waive/` | `requirement.waive` | `{"reason":"具體例外核准理由"}`；只允許 fail／not_provided | 200；保存 waived、核准人、時間與理由 |

RFQ 發出時建立六項案件快照：實際總成本 30%、規格與品質 30%、交期 15%、付款條件 10%、供應商
表現 10%、永續與風險 5%。本階段只固定規則，綜合分數計算尚未切換。

建立報價範例（假資料）：

```json
{
  "rfq_supplier_id": 301,
  "currency": "TWD",
  "exchange_rate_to_twd": "1.000000",
  "tax_amount": "250.00",
  "shipping_amount": "100.00",
  "discount_amount": "50.00",
  "payment_terms": "月結 30 天",
  "valid_until": "2026-09-15T17:00:00+08:00",
  "items": [
    {
      "request_item_id": 401,
      "quantity": "5.000",
      "unit_price": "1500.00",
      "lead_time_days": 7,
      "warranty_months": 24,
      "specifications": {"material": "網布"}
    }
  ]
}
```

明細 `subtotal`、表頭 `items_subtotal` 與 `landed_total_twd` 全由後端 Decimal 固定公式計算，忽略呼叫端
提供的總額。數量必須大於 0、最多三位小數且不可超過需求量；單價及各項金額不可為負數、最多兩位
小數；匯率必須大於 0、最多六位小數。報價可以只包含供應商可回覆的部分需求品項，未列品項不建立
零元明細。

必要條件取報價明細 `specifications` 中與 requirement code 同名的值，以後端固定
`equals/not_equals/gte/lte/in/contains` 運算子判斷；缺值記為 `not_provided`。無權限回 403
`permission_denied`、資源不存在回 404 `not_found`、狀態或 revision 衝突回 409；RFQ／報價逾期回 409
`quote_expired`。錯誤訊息不回傳 Stack Trace、SQL 或內部路徑。

### POST `/api/v1/rfqs/{id}/evaluate/`

**認證／權限**：Bearer Access Token；需 `rfq.manage`。Request Body 為空 object。

**行為**：鎖定 RFQ 後，只納入 `submitted`／`accepted_for_evaluation` 且報價未失效的版本。成本與交期以同一需求品項正規化，表頭稅額、運費與折扣按明細小計占比分攤；必要條件失敗者不列入建議。各品項評分再彙總為整張報價，只有覆蓋所有需求品項且條件合格者可成為整單建議。同分者並列，不自動得標。

**Response 200** 使用者可讀結構包含：

- `comparison_basis`：比較方式說明。
- `items[]`：品項、需求數量、各供應商報價、分項分數、資格原因與逐項建議。
- `quote_summaries[]`：報價覆蓋度、整體分數、資料完整度與整單建議。
- `recommendations[]`：每個品項的合格最高分供應商；`tie=true` 表示並列。

簡化回應範例（假資料）：

```json
{
  "rfq_id": 101,
  "rfq_no": "RFQ-DEMO-001",
  "status": "evaluating",
  "comparison_basis": "同一需求品項逐項比較，再彙總整張報價",
  "items": [
    {
      "request_item_id": 201,
      "description": "辦公椅",
      "recommended_supplier_names": ["範例供應商 A"]
    }
  ],
  "quote_summaries": [
    {
      "quote_id": 301,
      "supplier_name": "範例供應商 A",
      "covers_all_items": true,
      "total_score": "86.67",
      "data_completeness_pct": "45.00",
      "whole_request_recommended": true
    }
  ],
  "recommendations": [
    {
      "request_item_id": 201,
      "supplier_names": ["範例供應商 A"],
      "tie": false
    }
  ]
}
```

缺少可驗證的供應商表現或永續資料時，該項返回 `status=unavailable`，不寫入假分數。重複呼叫會取代該報價舊評分快照，不產生重複列。無權限回 403，RFQ 不存在回 404，狀態不允許或沒有有效報價回 409，規則快照不完整回 400。

### POST `/api/v1/award-decisions/`

**認證／權限**：Bearer Access Token；需 `award.recommend`。

建立人工選商草稿。`lines` 可讓不同需求品項選擇不同供應商，也可將同一需求品項拆量給多間供應商；同一報價品項不可重複。後端重新執行 C4 固定公式，只接受同一 RFQ 目前有效、未過期且必要條件合格或已 waiver 的報價。呼叫端不得提供正式金額；單位成本及金額由後端按稅額、運費、折扣與匯率重算為 TWD 快照。

```json
{
  "rfq_id": 101,
  "selection_reason": "第二來源可降低交期風險",
  "lines": [
    {
      "request_item_id": 201,
      "supplier_quote_item_id": 501,
      "quantity": "3.000",
      "reason": "主要供應量"
    },
    {
      "request_item_id": 201,
      "supplier_quote_item_id": 502,
      "quantity": "2.000",
      "reason": "備援供應量"
    }
  ]
}
```

選擇非該品項合格最高分報價時，`selection_reason` 必填；同分並列皆視為推薦。成功回 201 與得標草稿、分攤後 TWD 金額快照；格式錯誤或缺理由回 400，無權限回 403，RFQ／報價不存在回 404，狀態、期限或有效版本衝突回 409。

### PATCH `/api/v1/award-decisions/{id}/`

**認證／權限**：Bearer Access Token；需 `award.recommend`。

只允許完整替換 `draft` 得標方案的 `selection_reason` 與 `lines`；驗證規則與建立草稿相同。正式提交後不得原地修改。成功回 200；非草稿回 409。

### POST `/api/v1/award-decisions/{id}/submit/`

**認證／權限**：Bearer Access Token；需 `award.recommend`。Request Body 為空 object。

後端鎖定得標方案並重新驗證報價期限、目前版本、必要條件、推薦理由與數量。每個需求品項的得標數量加總必須精確等於需求數量；成功後在同一 transaction 將 Award 轉為 `submitted`、Purchase Request 轉為 `approval`，並依得標 TWD 總額建立 Approval Case 與政策快照。有 waiver 時先建立例外覆核關卡，再建立金額關卡。政策缺失、重疊或使用尚未支援的 `all` 模式時回 409，且整筆提交回滾。PO 由 C5-3 接續。

簡化回應範例（假資料）：

```json
{
  "id": 701,
  "rfq_id": 101,
  "revision": 1,
  "status": "submitted",
  "selection_reason": "第二來源可降低交期風險",
  "approval_case_id": 801,
  "total_amount_twd": "9900.00",
  "lines": [
    {
      "request_item_id": 201,
      "supplier_id": 31,
      "supplier_name": "範例供應商 A",
      "quantity": "3.000",
      "unit_cost_twd": "1500.00",
      "amount_twd": "4500.00"
    }
  ]
}
```

### GET `/api/v1/approval-cases/`

**認證／權限**：Bearer Access Token。具 `approval.read_all` 者只可看到關卡角色與自己有效角色相符的案件；具 `audit.read` 者可唯讀查看全部案件。

成功回 200 與案件陣列，包含需求單號、申請人、政策、總額、狀態及依序關卡。無讀取權限回 403。

### GET `/api/v1/approval-cases/{id}/`

可視範圍與佇列相同。成功回 200；案件不存在或不在可視範圍回 404。

簡化回應（假資料）：

```json
{
  "id": 801,
  "award_id": 701,
  "request_no": "PR-DEMO-001",
  "requester": {"id": 11, "name": "範例申請人"},
  "policy": {"id": 3, "name": "TWD 中額 Demo"},
  "total_amount": "9900.00",
  "currency": "TWD",
  "status": "pending",
  "steps": [
    {
      "id": 901,
      "sequence": 1,
      "step_type": "waiver_exception",
      "role": {"id": 8, "code": "procurement_exception_reviewer"},
      "status": "pending",
      "claimed_by": null
    },
    {
      "id": 902,
      "sequence": 2,
      "step_type": "amount_approval",
      "role": {"id": 3, "code": "approver_10k"},
      "status": "pending",
      "claimed_by": null
    }
  ]
}
```

### POST `/api/v1/approval-steps/{id}/claim/`

**認證／權限**：Bearer Access Token；需同時具有效目標角色、`approval.claim` 與 `approval.decide`。Waiver 關卡另需 `requirement.waive`。Request Body 為空 object。

申請人不得認領自己的案件；原 waiver 核准人不得認領同一例外；前一關未通過時不可跳關。後端以 row lock 保證兩人同時認領時只有一人成功。成功回 200，權限／職責分離不符回 403，已認領、已結案或跳關回 409。

### POST `/api/v1/approval-steps/{id}/decide/`

**認證／權限**：Bearer Access Token；需 `approval.decide` 且必須是該關認領人。

```json
{
  "decision": "approved",
  "reason": "金額、預算與例外證據均已確認"
}
```

`decision` 僅允許 `approved` 或 `rejected`，`reason` 必須為非空字串。核准後才開放下一關；最後一關通過時，後端在同一 transaction 將 Approval Case 與 Award 轉為 `approved`、依得標供應商建立 `draft` PO，再將 Purchase Request 轉為 `ordered`；建單不完整或得標金額與簽核快照不一致時整筆決議回滾。任一關駁回時 Case／Award 轉為 `rejected`、Purchase Request 轉為 `rejected`。每次認領、決議與 PO 建立均寫入 Audit Log。成功回 200，輸入錯誤回 400，非認領人或案件狀態衝突回 409。

### GET `/api/v1/purchase-orders/`

**認證／權限**：Bearer Access Token。具 `purchase_request.read_own` 者只能查看自己需求產生的 PO；具 `purchase_order.manage` 或 `audit.read` 者可唯讀查看全部。其他使用者回 403。

成功回 200 與 PO 陣列，包含單號、需求、得標方案、供應商、狀態、幣別、總額、版本及不可變明細快照。

### GET `/api/v1/purchase-orders/{id}/`

可視範圍與清單相同。成功回 200；PO 不存在或不在可視範圍回 404。

簡化回應（假資料）：

```json
{
  "id": 1001,
  "po_no": "PO-000701-000031",
  "award_id": 701,
  "request_no": "PR-DEMO-001",
  "supplier": {"id": 31, "name": "範例供應商 A"},
  "status": "draft",
  "currency": "TWD",
  "total_amount": "4500.00",
  "issued_at": null,
  "version": 1,
  "items": [
    {
      "line_no": 1,
      "product_name": "企業用辦公椅",
      "specifications": {"material": "網布"},
      "quantity": "3.000",
      "unit_price": "1500.00",
      "amount": "4500.00"
    }
  ]
}
```

### POST `/api/v1/purchase-orders/{id}/issue/`

**認證／權限**：Bearer Access Token；需 `purchase_order.manage`。

```json
{"version": 1}
```

只允許含有明細的 `draft` PO 發單。成功後狀態轉為 `issued`、寫入 `issued_at`、version +1，並在同一 transaction 將訂購數量加入 `InventoryBalance.in_transit_quantity`。發單不增加 on-hand，也不產生 InventoryMovement。無權限回 403，版本過期或非草稿回 409，無效 version 回 400。

## 分批收貨 API

### GET `/api/v1/goods-receipts/`／GET `/api/v1/goods-receipts/{id}/`

**認證／權限**：Bearer Access Token。具 `purchase_request.read_own` 者只能查看自己需求的收貨單；具 `receipt.record`、`inspection.decide` 或 `audit.read` 者可唯讀查看全部。無讀取權限回 403，資源不存在或不在可視範圍回 404。

### POST `/api/v1/goods-receipts/`

**認證／權限**：Bearer Access Token；需 `receipt.record`。

```json
{
  "purchase_order_id": 1001,
  "items": [
    {
      "purchase_order_item_id": 1101,
      "received_quantity": "2.000",
      "lot_no": "LOT-DEMO-001"
    }
  ]
}
```

只允許 `issued`／`partially_received` PO。`items` 至少一筆，同一 PO item 不得重複；數量必須大於 0 且最多三位小數。一般收貨不傳 `replacement_variance_line_id`；補交收貨必須傳有效 replacement 明細 ID，且同 PO 品項跨批補交不得超過授權數量。後端鎖定 PO，並由 DB trigger 阻擋一般跨批超收或補交超額。成功回 201 草稿收貨單；輸入格式錯誤回 400，PO 狀態不符、無效補交授權或數量競態回 409。

### POST `/api/v1/goods-receipts/{id}/submit/`

**認證／權限**：Bearer Access Token；需 `receipt.record`。Request Body 為 `{"version":1}`。

只允許有明細的 `draft` 收貨單送驗。成功時轉為 `inspecting`、寫入 `received_at`、version +1；一般收貨在同一 transaction 將本批實收數量自在途快照扣除，補交收貨不重複扣除原 PO 在途量。送驗不增加 on-hand，不產生 InventoryMovement。版本過期、重複送驗、非草稿或在途快照不足回 409。

成功回應包含 `id`、`receipt_no`、PO／供應商、`status`、收貨人／時間、`version` 與逐項實收數量／批號。所有範例資料均為假資料，不使用實際帳號或憑證。

### POST `/api/v1/goods-receipts/{id}/inspect/`

**認證／權限**：Bearer Access Token；需 `inspection.decide`，且驗收人不得是該批收貨人。

```json
{
  "version": 2,
  "items": [
    {
      "receipt_item_id": 1201,
      "accepted_quantity": "1.000",
      "defective_quantity": "1.000",
      "rejected_quantity": "0.000",
      "defect_details": "椅背表面刮傷",
      "notes": "合格品可先入庫"
    }
  ]
}
```

只允許 `inspecting` 收貨單，且必須一次提交該收貨單所有明細。各數量必須為非負、最多三位小數，合格＋瑕疵＋拒收必須等於實收；瑕疵數量大於 0 時 `defect_details` 必填。全數合格時收貨單轉 `posted`，部分合格轉 `partially_accepted`，無合格數量轉 `rejected`。只有合格數量會建立唯一、不可覆寫的 `receipt_accept` movement 並增加 on-hand；replacement 跨批累計合格量達授權量後，對應差異明細自動完成並保存本次 Inspector。驗收、流水、餘額及 PO／需求狀態彙總使用同一 transaction。

成功回 200，回應的每筆收貨明細新增 `inspection` 結果。輸入或數量錯誤回 400，無權限或收貨／驗收為同一人回 403，資源不存在回 404，版本過期、重複驗收或過帳衝突回 409。

## 驗收差異案件 API

### GET `/api/v1/inspection-variances/`／GET `/api/v1/inspection-variances/{id}/`

**認證／權限**：Bearer Access Token；具 `purchase_order.manage`、`receipt.record`、`inspection.decide` 或 `audit.read` 可唯讀全部。回應包含驗收、收貨、PO、供應商、品項、差異總數、案件狀態／version／actor/time 及處理明細。無讀取權限回 403，不存在回 404。

### POST `/api/v1/inspection-variances/`

**認證／權限**：Bearer Access Token；需 `purchase_order.manage`。

```json
{
  "quality_inspection_id": 1301,
  "lines": [
    {"action_type": "replacement", "quantity": "1.000", "reason": "要求供應商補交"},
    {"action_type": "credit", "quantity": "1.000", "reason": "供應商同意折讓"}
  ]
}
```

只能對瑕疵或拒收數量大於 0 的品質驗收建立唯一差異案件。`action_type` 限 `replacement`、`return`、`credit`、`waive`；數量必須大於 0、最多三位小數，理由必填，草稿明細總數不得超過驗收差異數量。成功回 201；格式錯誤回 400，無權限回 403，驗收不存在回 404，重複案件回 409。

### PUT／DELETE `/api/v1/inspection-variances/{id}/`

**認證／權限**：Bearer Access Token；需 `purchase_order.manage`。僅 `draft` 可修改或刪除，Request 必須帶目前 `version`；修改成功後 version +1，刪除成功回 204。版本過期或案件已送出回 409。

### POST `/api/v1/inspection-variances/{id}/submit/`

**認證／權限**：Bearer Access Token；需 `purchase_order.manage`。Request Body 為 `{"version":1}`。送出時處理明細總數必須精確等於 defective＋rejected；成功後案件轉 `open`、保存 submitted actor/time、version +1 並寫入 Audit Log。格式或數量不完整回 400，無權限回 403，不存在回 404，版本過期或非草稿回 409。

### POST `/api/v1/inspection-variances/{id}/complete-line/`

**認證／權限**：Bearer Access Token；需 `purchase_order.manage`。Request Body 為 `{"version":2,"line_id":1401}`。

只允許完成 `open` 案件的 pending `return`／`credit`／`waive` 明細，成功後保存 completed actor/time、案件 version +1 與 Audit Log。這些數量原本未入庫，因此不建立 `return_out` movement。replacement 不允許人工完成，須走補交收貨與複驗。無權限回 403，不存在回 404，版本過期、非 open／pending 或 replacement 回 409。

### POST `/api/v1/inspection-variances/{id}/close/`

**認證／權限**：Bearer Access Token；需 `purchase_order.manage`。Request Body 為 `{"version":4}`。

只有全部明細 completed 的 `open` 案件可結案；成功後保存 closed actor/time、案件 version +1 與 Audit Log。若 PO 各品項累計合格量等於訂購量則為 `received`；若合格量加已完成 return／credit／waive 等於訂購量則為 `closed`。同需求所有 PO 都是 received／closed 後，Purchase Request 轉 completed。版本或狀態衝突回 409。

## POST /api/v1/inquiries/parse/

FR-3／NFR-1：Django 先以固定程式將自然語言中的已建檔供應商名稱與具金額語境的數字 Token 化，再將遮罩文字送至 n8n v2（`N8N_INQUIRY_PARSE_WEBHOOK_URL`）。n8n 回傳後由 Django 在單次請求記憶體內遞迴還原候選字串。供應商依當下生效主檔唯一精確對應；產品先精確對應，未命中時只有在原句明確包含生效正式品名且與 LLM 簡化名稱唯一相容時才安全補回。遮罩 mapping 不寫入 DB、log 或 API Response。只回傳可編輯候選結構，不建立 Purchase Request、legacy Quote 或其他正式單據。

**認證／權限**：Bearer Access Token；需 `purchase_request.create`。發起人固定取自 JWT，Request 中的 `user_id` 不採信。

**Request**
```json
{ "raw_text": "跟優品科技、大和物產詢價，辦公椅 5 張、升降桌 3 張" }
```

**n8n v2 回傳 Django 的候選契約**
```json
{
  "purpose": "辦公設備汰換",
  "needed_by": null,
  "currency": "TWD",
  "suppliers": [{"name": "優品科技"}, {"name": "大和物產"}],
  "items": [
    {"product_name": "辦公椅", "quantity": "5", "unit_of_measure": "EA", "specifications": {"material": "網布"}}
  ],
  "assistant_message": "已整理需求，請確認品項與候選供應商。"
}
```

**Response（200）**：回傳 `purpose`、`needed_by`、`currency`、`assistant_message`、`items`、`supplier_candidates`、`missing_fields`、`ready_for_draft` 與 `supplier_product_coverage`。`items[].product_id` 及 `supplier_candidates[].supplier_id` 只在上述安全規則唯一對應且主檔可用時回傳，其餘為 `null` 並列入 `missing_fields`。數量必須大於 0 且最多三位小數。`supplier_product_coverage` 使用下述矩陣列格式。

**驗證與錯誤**：

- 空白輸入回 400。
- 找不到可確認的供應商，或同一顯式供應商片段混有已建檔與未建檔名稱時回 400，且不呼叫 n8n。
- 僅模糊命中的供應商建立既有人工複核案件並回 400，不把原始名稱送往 n8n。
- 無權限回 403。
- n8n 連線、非 JSON 或候選契約錯誤回 502。
- 錯誤訊息不得顯示內部 URL、Key、原始外部錯誤或 Stack Trace。

## POST /api/v1/supplier-product-coverage/

FR-3：建立草稿前，依目前選擇的候選供應商、正式品項、數量與幣別回傳唯讀供應能力矩陣。資料取自 `supplier_products` 與當下有效的 `supplier_price_versions`；不建立或修改任何單據。

**認證／權限**：Bearer Access Token；需 `purchase_request.create`。

**Request**
```json
{
  "currency": "TWD",
  "supplier_ids": [1, 2],
  "items": [
    {"product_id": 10, "quantity": "5"},
    {"product_id": 11, "quantity": "3"}
  ]
}
```

**Response（200）**
```json
{
  "rows": [
    {
      "supplier_id": 1,
      "supplier_name": "範例供應商",
      "product_id": 10,
      "product_name": "A產品-辦公椅",
      "status": "priced",
      "label": "可供應，且有有效價格",
      "unit_price": "1500.00",
      "currency": "TWD"
    }
  ]
}
```

`status` 合法值為 `priced`、`unpriced`、`conditional`、`blocked`、`inactive`、`not_configured`。矩陣為資訊性提示，不等於供應商正式報價，也不直接阻擋草稿建立。

**錯誤狀態**：未登入回 401；無權限回 403；供應商／品項陣列格式錯誤或數量非正數回 400。

## POST /api/v1/inquiries/trigger/

FR-1：接收自然語言詢價文字，同步呼叫 n8n Webhook（`N8N_INQUIRY_WEBHOOK_URL`），把 n8n 最終回應原樣回傳。

詢價發起人固定取自 JWT 使用者，呼叫端傳入的 `user_id` 會被忽略，避免冒用其他人身分。

**Request**
```json
{ "raw_text": "幫我訂20個A產品，跟優品科技拿貨" }
```

`raw_text` 必須包含可由固定規則驗證的明確正整數數量，例如「20 個／20 件／數量：20／五個／
十五件」；支援阿拉伯、全形與中文數字。模糊量詞如「一些／幾個」不得由 LLM 自行猜值，會在
呼叫 n8n 前回 400。

**Response（200）**：原樣透傳 n8n workflow 的最終輸出。

**Response（400）**：`raw_text` 為空，或缺少明確正整數數量。

**Response（401）**：Bearer Access Token 缺漏或失效。

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

**Response（200，通過）**：`quotes.ai_summary_text` 寫入該摘要文字，`quotes.status` 進至 `pending_approval`，並建立一筆依金額門檻指派角色的 `approval`。
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

FR-6b：登入的管理員認領複核案件，避免多人同時處理同一案件；身分固定取自 JWT。

**Request Body**
無 Request Body。

**Response（200）**：回傳更新後的 `manual_review_queue` 資料列（`status` 變為 `claimed`）。

**Response（401／403）**：未登入／非管理員。

**Response（409）**：案件已被認領或已結案。

## POST /api/v1/manual-review-queue/{id}/decide/

FR-6a／FR-6c：決議案件（核准／駁回），僅提供 SPEC 定義的有限選項，不開放自由編輯 AI 生成內容後放行；必須是該案件的認領人才能決議。每次決議都寫入 `audit_logs`（`action_type="review_decision"`）。

**Request Body**
```json
{ "decision": "approved" }
```
`review_type=supplier_fuzzy_match` 且核准時，若 `manual_review_queue.supplier_id` 尚未預填（多筆候選或長度不安全的情況），必須額外帶 `supplier_id` 明確指定：
```json
{ "decision": "approved", "supplier_id": 7 }
```

**核准（`hallucination_mismatch`）**：丟棄 LLM 生成摘要，改用 `services/quote_summary_template.py` 的固定樣板依真實數字組出文字寫回 `quotes.ai_summary_text`，`quotes.status` 進至 `pending_approval`。
**駁回（`hallucination_mismatch`）**：`quotes.status` 改為 `cancelled`（詢價作廢，通知申請人重新送出，Gmail 通知留待 n8n 串接）。
**核准（`supplier_fuzzy_match`）**：確認 `manual_review_queue.supplier_id`；DB 交易確定提交後，Django 主動呼叫 n8n 的 `N8N_RESUME_WEBHOOK_URL`（`POST .../webhook/inquiry/resume`），帶 `review_id`／`raw_input_text`／`user_id`（`manual_review_queue.requester`，原始詢價發起人）／`supplier_id`，交還 n8n 重新走一次「遮罩金額→LLM 解析→查詢→試算→摘要→幻覺驗證」流程（見 `docs/ADR/discuss/main-flow.md`）。呼叫 n8n 失敗（連線問題、逾時、非 2xx）不影響這支 API 本身的核准結果——DB 裡供應商已確認的事實不因外部呼叫失敗而回滾。
**駁回（`supplier_fuzzy_match`）**：不異動供應商欄位，不呼叫 n8n，通知申請人確認供應商全名後重新送出。

**Response（200）**：回傳更新後的 `manual_review_queue` 資料列（`status` 變為 `resolved`）。核准 `supplier_fuzzy_match` 案件時，回應多一個 `resume_triggered`（布林值，非 DB 欄位）：`true` 表示已成功通知 n8n 續傳，`false` 表示通知失敗（決議本身仍然成功，但需要人工確認 n8n 那邊是否要手動觸發）。

**Response（400）**：`decision` 缺漏、`decision` 非 `approved`／`rejected`、或核准模糊比對案件卻缺少可用的 `supplier_id`。

**Response（401／403）**：未登入／非管理員。

**Response（409）**：案件尚未認領、已結案，或非本人認領。

## 採購單與簽核 Action

### POST /api/v1/quotes/{id}/withdraw/

本人可撤回狀態為 `pending_approval` 的採購單。成功時 Quote 與 Approval 同步改為 `cancelled` 並寫入
Audit Log；非本人回 400，案件不存在回 404，已結案或狀態不符回 409。

### POST /api/v1/approvals/{id}/claim/

登入使用者只能認領路由角色與自身角色相同、仍為 `pending` 且尚未被認領的案件。admin 只能認領
路由到 admin 的大額案件，不能跨角色代簽。成功回 200；資格不符回 400；已認領／結案回 409。

### POST /api/v1/approvals/{id}/decide/

只有已認領該案件的使用者可送出 `{"decision":"approved"}` 或 `{"decision":"rejected"}`。成功時
Approval 與 Quote 同步轉為 approved／rejected 並寫入 Audit Log；無效決議回 400，非認領者或已結案回 409。
