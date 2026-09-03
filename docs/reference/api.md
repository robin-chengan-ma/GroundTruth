---
title: API Reference
updated: 2026-09-03
---

# API Reference

> 技術參考文件，跟著程式碼異動更新，不是決策紀錄（決策放 `docs/ADR/discuss/`）也不是產品規格
> （放 `docs/specs/SPEC.md`）。Phase 4 起 API 已依資源套用 JWT 與角色權限；工作流程資源改為
> 唯讀清單／明確 action，不再允許用通用 CRUD 任意改寫正式狀態。

## Phase 6 清單分頁／搜尋／篩選共用慣例

SPEC「搜尋、篩選、分頁」缺口補齊：`suppliers`、`products`、`product-categories`、`supplier-products`、
`rfqs`、`supplier-quotes`、`award-decisions`、`purchase-orders`、`goods-receipts`、
`inspection-variances`、`purchase-suggestions` 共 11 個清單端點（`GET` list，不含 `retrieve`）統一改用
`backend/lib/pagination.py` 的分頁工具，回應形狀與既有 `GET /api/v1/purchase-requests/`
（見下方「本人採購需求清單 API」）一致：

```json
{ "count": 21, "page": 2, "page_size": 10, "total_pages": 3, "results": [ /* ... */ ] }
```

`page`（預設 1）、`page_size`（只允許 `10`／`20`／`50`，預設 `20`）為共用 Query Parameter，格式或範圍
不合法回 400 `invalid_pagination`。各端點另支援 `?search=<關鍵字>`（對應資源的名稱／單號等文字欄位
`icontains`，見各端點小節）與至少一個精確比對篩選（多為 `?status=<狀態>`，個別端點另有
`quality_status`／`is_active`／`tier`／`category`），兩者皆可與 `page`／`page_size` 併用，皆為選填、不填
則不套用該條件。此慣例只套用於清單端點；單筆 `retrieve`、`POST`／`PATCH`／`PUT` 等寫入 action 不受影響。
其中 `?category=<id>` 是外鍵 id 篩選，帶非整數值（如 `?category=abc`）會在建立查詢條件前先驗證，
回 400 `invalid_pagination`，不會讓資料庫查詢求值時噴未處理的例外。

## 認證方式

| 呼叫方 | 端點範圍 | 認證方式 |
| --- | --- | --- |
| Vue 前端 | `/auth/*`、一般資源、`inquiries/parse/`、簽核／複核 action | Access Token 放記憶體並以 `Authorization: Bearer <token>` 傳送；Refresh Token 僅存 HttpOnly、SameSite=Lax Cookie，refresh/logout 另驗證 `X-CSRFToken` |
| n8n | suppliers/products 唯讀查詢、`masking/mask/`、`masking/mask-amounts-only/`、`masking/unmask/` | 固定 API Key，自訂 header `X-Internal-Api-Key`，需與 `INTERNAL_API_KEY` 環境變數一致（FR-1a）；legacy `quotes/calculate/` 與 `quotes/verify-hallucination/` 已停用 |
| Django（主動呼叫方） | n8n 的 `POST .../webhook/purchase-request-candidate`、`POST .../webhook/notify` | 固定 API Key，同上 header，`n8n/workflows/purchase-request-candidate-flow.json`、`notification-flow.json` 的 webhook 節點後方各有一個「IF：Internal API Key 正確？」節點比對 `X-Internal-Api-Key` 是否等於 n8n 容器的 `INTERNAL_API_KEY` 環境變數（2026-09-03 起；修復前 n8n 端從未驗證這個 header，任何人都能直接打這兩支 webhook，見 `docs/ADR/debug/phase7-integration.md`）。`N8N_RESUME_WEBHOOK_URL`（`webhook/inquiry/resume`）現況已無程式碼呼叫，屬死設定，見 `docs/reference/deploy.md` |

## Vue 登入與 Session

| Method / Route | 認證 | Request | Response／規則 |
| --- | --- | --- | --- |
| `POST /api/v1/auth/login/` | 無 | `{"email":"employee@example.com","password":"example-only"}` | 200 回 `{"access": "...", "user": {"id","name","email","role","permissions"}}`（使用者欄位包在 `user` 物件內，不是攤平在頂層）；`permissions` 為所有生效 UserRole 合併、去重且排序的權限碼。設定 Refresh HttpOnly Cookie 與 CSRF Cookie。帳號不存在或密碼錯誤統一回 401 `帳號或密碼錯誤` |
| `POST /api/v1/auth/refresh/` | Refresh Cookie + `X-CSRFToken` | 無 | 200 回新 `access` 並 rotation Refresh Cookie；舊 Token 立即撤銷。CSRF 錯誤回 403，Token 缺漏／失效／重放回 401 |
| `POST /api/v1/auth/logout/` | Refresh Cookie + `X-CSRFToken` | 無 | 撤銷目前 Refresh Session、刪除 Cookie，回 204；無 Cookie 時維持冪等 |
| `GET /api/v1/auth/me/` | Bearer Access Token | 無 | 200 回 `id/name/email/role/permissions`；權限來自目前有效的多角色 RBAC；無效或過期 Token 回 401 |

Access Token 有效 15 分鐘，Refresh Token 有效 1 天。資料庫只保存 Refresh Token 的 SHA-256 雜湊與
rotation／撤銷狀態，不保存 Token 明文。

## 前端資源權限

| 資源 | 可視範圍 | 可寫入範圍 |
| --- | --- | --- |
| roles、users | admin | admin CRUD；密碼寫入時由後端雜湊 |
| suppliers、products、product-categories | 已登入使用者；n8n 可用內部 API Key 唯讀查詢 suppliers／products | 讀取需 `master_data.read`、寫入需 `master_data.manage`（`AuthenticatedReadAdminWrite`）；主檔不提供實體刪除，一律回 409 `physical_delete_forbidden`，改用 `is_active` 停用 |
| inventory | 具 `inventory.read`（不可用 `master_data.read` 代替） | 唯讀端點（`ReadOnlyModelViewSet`）；Phase 1 舊 `Inventory` model（`stock_qty`／`threshold`），`stock_qty` 已停止由正式收貨驗收流程更新，僅供歷史查閱 |
| inventory-balances、inventory-movements | 具 `inventory.read` | 唯讀端點；FR-10a 真正庫存來源（`InventoryBalance` 查詢快照／`InventoryMovement` 不可覆寫流水帳），Phase 6 起取代舊 `inventory` 端點作為庫存頁面資料來源 |
| purchase-suggestions | 具 `purchase_suggestion.read`（list／retrieve 專用；convert／dismiss 不套用此權限碼，各自的授權見下方 API 表） | 通用 API 唯讀；具 `purchase_request.create` 可轉單，忽略未轉單建議須具 `purchase_suggestion.dismiss`（不綁定角色字串，見 `docs/ADR/discuss/erp.md`） |
| quotes | legacy 歷史查詢改用 permission code（Phase 5 修復，見 `docs/ADR/debug/phase5-security.md` 2026-09-02 條目）：`audit.read` 見全部；`approval.read_all` 見自己角色曾經手簽核的詢價＋本人；僅 `purchase_request.read_own` 只見本人；三者皆無回 403 | 通用 API 唯讀；legacy 建單、驗證與撤回 command 皆已回 410 `legacy_command_retired`，不再接受正式寫入 |
| approval-cases、approval-steps | `approval.read_all` 只見有效角色對應案件；`audit.read` 可唯讀全部 | 僅符合目標角色及 permission codes 者可認領／決議；決議理由必填，禁止申請人自簽與跨角色代簽 |
| approvals | legacy 歷史查詢改用 permission code（同上）：`audit.read` 見全部；`approval.read_all` 只見自己角色的歷史簽核紀錄；兩者皆無回 403 | `claim`／`decide` 已停用並回 410；不再接受正式寫入 |
| purchase-request-drafts | 具 `purchase_request.read_own` 者只見本人草稿 | create／edit_draft／submit 分別檢查對應 RBAC；只有 draft 可修改或刪除 |
| purchase-requests | 具 `purchase_request.read_own` 者只見本人全部需求 | 唯讀清單；正式狀態異動必須使用各流程明確 action，不提供通用 CRUD |
| rfqs、supplier-quotes | 具 `rfq.manage`／`supplier_quote.manage` 或 `audit.read`（唯讀）；一般申請人不開放 | RFQ 只能由明確 issue action 發出；報價只能建立草稿、提交或建立 revision，不提供通用更新／刪除 |
| award-decisions | 具 `award.recommend` 或 `audit.read`（唯讀） | 只能由明確 command 建立草稿、PATCH 草稿、submit；不提供通用刪除 |
| supplier-products | 具 `master_data.read` | 僅 `master_data.manage` 可建立／更新／新增價格版本；不提供實體刪除，只能 `is_active` 停用 |
| quote-requirement-results | 採購人員於報價提交後讀取評估結果 | 只有 `requirement.waive` 可對 fail／not_provided 填理由例外核准 |
| goods-receipts | 申請人只見自己需求；`receipt.record`、`inspection.decide`、`audit.read` 可見全部 | 只有 `receipt.record` 可建立草稿與送驗；不開放通用更新／刪除 |
| inspection-variances | `purchase_order.manage`、`receipt.record`、`inspection.decide`、`audit.read` 可唯讀全部 | 只有 `purchase_order.manage` 可建立、修改／刪除草稿與送出；正式案件不可以通用 CRUD 改寫 |
| manual-review-queue | 具 `manual_review.decide`（含 list／retrieve；未套用 `admin` 角色字串判斷） | list／retrieve 為標準 DRF `PageNumberPagination`（`count／next／previous／results`，`?page=`），與下方共用分頁信封不同；`claim`／`decide`／`retry-resume` 見對應章節 |
| audit-logs | 具 `audit.read` | 唯讀；同樣是標準 DRF `PageNumberPagination`（`count／next／previous／results`），不是下方共用分頁信封 |
| audit-dashboard/stats | 具 `audit.read` | 統計總覽，非清單端點，不分頁 |

## 主檔管理 API（供應商／品項／分類）

Phase 6 補齊：`SupplierSerializer`／`ProductSerializer` 原本只回傳極少欄位，前端主檔管理頁面
需要完整欄位才能顯示與編輯；`ProductCategory` model 早已存在（`Product.category` FK），Phase 6
起才有對應 API。

| Method / Route | 必要權限 | Request／規則 | 成功回應 |
| --- | --- | --- | --- |
| `GET／POST /api/v1/suppliers/` | 讀 `master_data.read`／寫 `master_data.manage` | GET 支援 `page`／`page_size`／`?search=<name 或 code>`／`?status=<active\|on_hold\|blocked>`／`?tier=<priority\|normal\|watch>`／`?is_active=<true\|false>`（見上方 Phase 6 分頁慣例） | GET 200 分頁清單；POST 201；欄位含 `id/name/tier/code/status/tax_id/contact/payment_terms/is_active/created_at/updated_at` |
| `PATCH／PUT /api/v1/suppliers/{id}/` | `master_data.manage` | 可局部更新任何欄位 | 200 |
| `DELETE /api/v1/suppliers/{id}/` | `master_data.manage` | 不提供實體刪除 | 409 `physical_delete_forbidden`，改用 PATCH `is_active=false` |
| `GET／POST /api/v1/products/` | 讀 `master_data.read`／寫 `master_data.manage` | GET 支援 `page`／`page_size`／`?search=<name 或 sku>`／`?category=<category_id>`／`?is_active=<true\|false>`（見上方 Phase 6 分頁慣例；`?search=` 亦供 n8n 依 LLM 解析出的品項名稱查詢，見下方「GET /api/v1/suppliers/?search=、GET /api/v1/products/?search=」） | GET 200 分頁清單；POST 201；欄位含 `id/name/category/category_name/sku/description/specifications/unit_of_measure/is_active/price/currency/updated_at`；`category` 可為 `null` |
| `PATCH／PUT /api/v1/products/{id}/` | `master_data.manage` | 可局部更新任何欄位 | 200 |
| `DELETE /api/v1/products/{id}/` | `master_data.manage` | 不提供實體刪除 | 409 `physical_delete_forbidden`，改用 PATCH `is_active=false` |
| `GET／POST /api/v1/product-categories/` | 讀 `master_data.read`／寫 `master_data.manage` | GET 支援 `page`／`page_size`／`?search=<code 或 name>`／`?is_active=<true\|false>`；POST 需 `code`（唯一）、`name`、可選 `spec_schema`（JSON object，供品項規格驗證定義用）、`is_active` | GET 200 分頁清單；POST 201 |
| `PATCH /api/v1/product-categories/{id}/` | `master_data.manage` | 可局部更新 | 200 |
| `DELETE /api/v1/product-categories/{id}/` | `master_data.manage` | 不提供實體刪除 | 409 `physical_delete_forbidden`，改用 PATCH `is_active=false` |

無權限回 403，格式錯誤回 400。`contact`／`specifications`／`spec_schema` 皆為自由格式 JSON object。

## 庫存查詢 API

FR-10a：`inventory-balances`／`inventory-movements` 取代 Phase 1 舊 `inventory`（`Inventory` model
`stock_qty`／`threshold`）作為庫存頁面資料來源——`stock_qty` 已停止由正式收貨驗收流程更新，只有
`InventoryBalance`（`on_hand_quantity`／`reserved_quantity`／`in_transit_quantity`）與
`InventoryMovement`（不可覆寫流水帳）才反映目前真實庫存；`threshold`（低於此值觸發採購建議）仍沿用
舊 `Inventory` 主檔，尚未整併。

| Method / Route | 必要權限 | Request／規則 | 成功回應 |
| --- | --- | --- | --- |
| `GET /api/v1/inventory-balances/`／`GET .../{product_id}/` | `inventory.read` | 無 | 200；欄位含 `product/product_name/on_hand_quantity/reserved_quantity/in_transit_quantity/available_quantity/threshold/version/updated_at`；`available_quantity = on_hand - reserved + in_transit`；未建檔的舊 `Inventory.threshold` 回傳 `null` |
| `GET /api/v1/inventory-movements/`／`GET .../{id}/` | `inventory.read` | 依 `-posted_at,-id` 排序 | 200；欄位含 `id/product/product_name/movement_type/quantity_delta/reference_type/reference_id/affects_balance/reason/posted_at/posted_by/posted_by_name/created_at` |

無讀取權限回 403。

## 採購需求草稿 API

全部端點使用 Bearer Access Token。候選供應商保存於 `status=draft` 的 RFQ；尚未正式邀價，不建立 legacy
Quote、Supplier Quote、簽核或採購單。

| Method / Route | 必要權限 | Request／規則 | 成功回應 |
| --- | --- | --- | --- |
| `GET /api/v1/purchase-request-drafts/` | `purchase_request.read_own` | 無；只列本人 draft | 200 草稿陣列 |
| `GET /api/v1/purchase-request-drafts/{id}/` | `purchase_request.read_own` | 非本人或非 draft 統一回 404 | 200 完整草稿 |
| `POST /api/v1/purchase-request-drafts/` | `purchase_request.create` | `purpose`、`currency`、一至多筆 `items`、一至多個 `supplier_ids`；選填 `candidate_token`（見下方「POST /api/v1/inquiries/parse/」，用於稽核統計比對，不影響草稿是否能建立） | 201 完整草稿 |
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
| `search` | 否 | 模糊比對申請編號、用途、品項名稱或候選供應商名稱（`icontains`，不分大小寫） |
| `status` | 否 | 精確比對 `PurchaseRequest.Status`；不是合法值回 400 |

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

### POST `/api/v1/purchase-requests/{id}/withdraw/`

**認證／權限**：Bearer Access Token；需 `purchase_request.withdraw`。只允許本人已建立的 Purchase Request；非本人與不存在資源回 404。

**Request Body（假資料）**：

```json
{
  "version": 3,
  "reason": "供應商臨時無法交貨，改由其他管道採購"
}
```

`reason` 為必填、去除前後空白後不得為空字串；`version` 須與目前資料列版本一致（樂觀鎖）。

**規則**：只有 `submitted`／`sourcing`／`awarding`／`approval` 狀態可撤回；`draft` 應改用刪除草稿，其他狀態不可撤回。撤回會在同一 transaction 內：取消所有尚未結束（非 `closed`／`cancelled`）的 RFQ 與受邀供應商紀錄、取消尚在 `draft`／`submitted` 的得標決議與對應簽核案件，最後把需求本身標記 `cancelled` 並記錄撤回原因。這是 legacy `POST /api/v1/quotes/{id}/withdraw/` 的正式替代端點（見下方「Legacy API」章節）。

**Response**：
- 200：回傳撤回後的 `PurchaseRequestDetailSerializer` 資料（`status` 為 `cancelled`）
- 404：找不到指定的採購需求（含非本人案件，`code: not_found`）
- 409：`version` 不一致或目前狀態不可撤回，兩種情況同樣回 `code: version_conflict`
- 400：`reason` 空白（`code: invalid_draft`）

## 採購建議 API

| Method / Route | 必要權限 | Request／規則 | 成功回應 |
| --- | --- | --- | --- |
| `GET /api/v1/purchase-suggestions/` | `purchase_suggestion.read` | 支援 `page`／`page_size`／`?search=<品項名稱>`／`?status=<pending\|in_progress\|processed\|dismissed>`（見上方 Phase 6 分頁慣例）；回傳品項、建議數量、狀態、來源 movement 與轉成的 request | 200 分頁清單（`{count,page,page_size,total_pages,results}`，Phase 6 起改用共用分頁工具，取代原本的全域 `PageNumberPagination`） |
| `GET /api/v1/purchase-suggestions/{id}/` | `purchase_suggestion.read` | 通用資源唯讀 | 200 建議詳情 |
| `POST /api/v1/purchase-suggestions/{id}/convert/` | `purchase_request.create` | `supplier_ids` 為非空、不重複的有效供應商 ID；可傳 `purpose`、`needed_by`、`currency`；僅 pending 且尚未轉單可執行 | 201；建立本人 Purchase Request draft 並回傳 `purchase_request_id` |
| `POST /api/v1/purchase-suggestions/{id}/dismiss/` | `purchase_suggestion.dismiss` | 無；僅 pending 且尚未轉單可執行 | 200；狀態轉 dismissed |

轉單與忽略都使用 transaction 及 row lock；競態、重複轉單、非 pending 或已綁定草稿回 409，無權限回 403，資源不存在回 404，供應商或格式無效回 400。轉成的草稿提交後建議轉 in_progress；對應需求 completed 後轉 processed。

## 正式 RFQ 與版本化供應商報價 API

全部端點使用 Bearer Access Token。正式 RFQ 及報價只提供明確 command，不開放通用 PATCH／DELETE。

| Method / Route | 必要權限 | Request／規則 | 成功回應 |
| --- | --- | --- | --- |
| `GET /api/v1/rfqs/`／`GET /api/v1/rfqs/{id}/` | `rfq.manage` 或 `audit.read` | 清單支援 `page`／`page_size`／`?search=<RFQ 編號、需求編號或受邀供應商名稱>`／`?status=<draft\|issued\|collecting\|evaluating\|closed\|cancelled>`（見上方 Phase 6 分頁慣例）；一般申請人不開放，僅採購管理與稽核角色可查 | 清單 200 分頁結果（依 `-created_at,-id` 排序）；詳情 200，含受邀供應商與評選標準快照；`invited_suppliers[]` 每筆含 `rfq_supplier_id`（建立報價需要的邀請關係主鍵，非 `supplier_id`）、`supplier_id`、`supplier_name`、`status`、`invited_at`、`responded_at`；`request_no`、`request_purpose`、`request_items[]`（需求明細快照，含 `product_name`／`quantity`／`unit_of_measure`／`specifications`）（皆為 2026-09-02 補上——`PurchaseRequestViewSet.retrieve` 只開放需求本人，採購人員需要靠 RFQ 詳情才能看到別人送出的需求明細與建立報價所需的 `rfq_supplier_id`） |
| `GET /api/v1/supplier-quotes/`／`GET /api/v1/supplier-quotes/{id}/` | `supplier_quote.manage` 或 `audit.read` | 清單支援 `page`／`page_size`／`?search=<報價單號、RFQ 編號或供應商名稱>`／`?status=<draft\|submitted\|accepted_for_evaluation\|revised\|rejected\|expired>` | 清單 200 分頁結果／詳情 200，含明細與必要條件判定結果 |
| `GET /api/v1/award-decisions/`／`GET /api/v1/award-decisions/{id}/` | `award.recommend` 或 `audit.read` | 清單支援 `page`／`page_size`／`?search=<RFQ 編號或需求編號>`／`?status=<draft\|submitted\|approved\|rejected\|cancelled>` | 清單 200 分頁結果／詳情 200，含得標分配明細 |
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

## 供應商可供應品項與版本化價格主檔 API

全部端點使用 Bearer Access Token。主檔（供應商×品項關係）只能啟用／停用，不得實體刪除；價格採版本
控制，新版本一律用新增，不得覆寫既有版本的價格內容。

| Method / Route | 必要權限 | Request／規則 | 成功回應 |
| --- | --- | --- | --- |
| `GET /api/v1/supplier-products/` | `master_data.read` | 支援 `page`／`page_size`／`?search=<供應商名稱、品項名稱或 supplier_sku>`／`?quality_status=<qualified\|conditional\|blocked>`／`?is_active=<true\|false>`（見上方 Phase 6 分頁慣例） | 200 分頁清單（依供應商／品項名稱排序），含各筆 `price_versions` |
| `GET /api/v1/supplier-products/{id}/` | `master_data.read` | 無 | 200 詳情 |
| `POST /api/v1/supplier-products/` | `master_data.manage` | `supplier`、`product`（皆須為現行啟用中）；可選 `supplier_sku`、`lead_time_days`（預設 0）、`minimum_order_quantity`（預設 1）、`quality_status`（`qualified`／`conditional`／`blocked`，預設 `qualified`） | 201；同一供應商＋品項已存在關係回 409 |
| `PATCH /api/v1/supplier-products/{id}/` | `master_data.manage` | 可局部更新 `supplier_sku`、`lead_time_days`、`minimum_order_quantity`、`quality_status`、`is_active` | 200 |
| `DELETE /api/v1/supplier-products/{id}/` | `master_data.manage` | 不提供實體刪除 | 409 `physical_delete_forbidden`，請改用 PATCH `is_active=false` |
| `POST /api/v1/supplier-products/{id}/price-versions/` | `master_data.manage` | `unit_price`（必須 >0）、`currency`（預設 `TWD`）、`minimum_quantity`（必須 >0，預設 1）、`valid_from`（ISO 8601，預設現在）、可選 `valid_until` | 201；回傳更新後的主檔（含新版本）；同幣別／數量級距若已有時間重疊的有效版本回 409 |

新增價格版本前，後端會檢查同一供應商品項、同幣別、同 `minimum_quantity` 級距是否已有時間重疊
（`valid_until` 為 `NULL` 視為無限期有效）的既有版本，避免同一時間點出現兩個有效單價；需要調整既有
價格時，先把舊版本的 `valid_until` 設為新版本的 `valid_from`（透過另一次新增動作或後續版本管理
API，目前尚未提供修改既有版本 `valid_until` 的獨立 command，屬 Phase 6 前端頁面待補的操作流程）。
無權限回 403 `permission_denied`，資源不存在回 404 `not_found`，格式或數值錯誤回 400。

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
  "request_id": 501,
  "request_no": "PR-DEMO-001",
  "purpose": "汰換會議室設備",
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
      "claimed_by": null,
      "can_claim": true,
      "can_decide": false
    },
    {
      "id": 902,
      "sequence": 2,
      "step_type": "amount_approval",
      "role": {"id": 3, "code": "approver_10k"},
      "status": "pending",
      "claimed_by": null,
      "can_claim": false,
      "can_decide": false
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

**Query Parameters**：`page`／`page_size`／`?search=<PO 單號、供應商名稱或 RFQ 編號>`／`?status=<draft\|issued\|partially_received\|received\|closed\|cancelled>`（見上方 Phase 6 分頁慣例，皆選填）。

成功回 200 分頁結果（`{count,page,page_size,total_pages,results}`），`results` 為 PO 陣列，包含單號、需求、得標方案、供應商、狀態、幣別、總額、版本及不可變明細快照。

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

**清單 Query Parameters**：`page`／`page_size`／`?search=<收貨單號、PO 單號或供應商名稱>`／`?status=<draft\|inspecting\|posted\|partially_accepted\|rejected\|voided>`（見上方 Phase 6 分頁慣例，皆選填）；清單回應為 `{count,page,page_size,total_pages,results}`。

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

**清單 Query Parameters**：`page`／`page_size`／`?search=<收貨單號、品項名稱或供應商名稱>`／`?status=<draft\|open\|closed\|cancelled>`（見上方 Phase 6 分頁慣例，皆選填）；清單回應為 `{count,page,page_size,total_pages,results}`。

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

**Response（200）**：回傳 `purpose`、`needed_by`、`currency`、`assistant_message`、`items`、`supplier_candidates`、`missing_fields`、`ready_for_draft`、`supplier_product_coverage` 與 `candidate_token`。`items[].product_id` 及 `supplier_candidates[].supplier_id` 只在上述安全規則唯一對應且主檔可用時回傳，其餘為 `null` 並列入 `missing_fields`。數量必須大於 0 且最多三位小數。`supplier_product_coverage` 使用下述矩陣列格式。`candidate_token` 是後端簽章過的候選內容憑證（「採購稽核與流程健康總覽」FR-1 直接採用／人工修正統計用），前端建立草稿時應原樣帶回 `POST /api/v1/purchase-request-drafts/` 的 `candidate_token` 欄位（選填，供比對使用者最終確認內容與 AI 原始候選的差異；憑證只在單次候選流程內有效，不落地存原始文字或欄位值）。

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

Phase 5.0 起已停用的 legacy 詢價建單入口。路徑保留供舊呼叫者取得明確相容性錯誤，不再呼叫 n8n。

**認證**：Bearer Access Token；缺漏或失效回 401。

**Response（410）**
```json
{
  "detail": "舊版詢價建單流程已停用，請改用採購需求流程",
  "code": "legacy_command_retired"
}
```

## POST /api/v1/quotes/calculate/

Phase 5.0 起已停用的 legacy Quote 建單入口。路徑與內部 API Key 認證保留，但通過認證後不再試算或建立 `Quote`。

**Request Headers**
```
X-Internal-Api-Key: <INTERNAL_API_KEY>
```

**Response（401）**：`X-Internal-Api-Key` 缺漏或錯誤。

**Response（410）**：同 `inquiries/trigger/` 的 `legacy_command_retired` 回應；Request Body 不再解析。

## GET /api/v1/suppliers/?search=<name> 、 GET /api/v1/products/?search=<name>

Phase 2 新增，供 n8n 依 LLM 解析出的供應商/產品名稱做查詢，屬既有 CRUD 端點的行為擴充，不是新端點。
Phase 6 起 `?search=` 改由上方「Phase 6 清單分頁／搜尋／篩選共用慣例」的 `backend/lib/pagination.py`
統一處理（供應商比對 `name`／`code`，品項比對 `name`／`sku`，取代原本的 DRF `SearchFilter`）；n8n
呼叫方只讀 `results[0]`，不受回應改為 `{count,page,page_size,total_pages,results}` 分頁信封影響（見
`n8n/workflows/inquiry-flow.json`）。

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
`user_id`：選填，詢價發起人。有帶入時，若結果為 `supplier_fuzzy_match`（寫入複核佇列），會存進 `manual_review_queue.requester`，供核准後 Django 直接重新解析（見 `POST /api/v1/manual-review-queue/{id}/decide/` 核准 `supplier_fuzzy_match` 段落，2026-09-02 改版）帶回原始發起人身分。

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

FR-6a：供應商模糊比對案件核准後，n8n 續傳流程專用。此時供應商身分已由人工確認，不需要再猜測或比對供應商名稱，只需要重新遮罩金額後送 LLM 解析品項/數量。只給 n8n 呼叫。**現況（2026-09-02）**：`POST /api/v1/manual-review-queue/{id}/decide/` 核准 `supplier_fuzzy_match` 案件後，主要路徑已改為 Django 直接呼叫（見該端點文件），不再經由這支端點；此端點程式碼與路由本身未刪除，若 Robin 自己維護的 n8n workflow 仍有分支呼叫它，功能維持正常。

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

Phase 5.0 起已停用的 legacy Quote 摘要驗證入口。路徑與內部 API Key 認證保留，但通過認證後不再修改 Quote、建立 Approval 或建立人工複核案件。

**Request Headers**
```
X-Internal-Api-Key: <INTERNAL_API_KEY>
```

**Response（401）**：`X-Internal-Api-Key` 缺漏或錯誤。

**Response（410）**：同 `inquiries/trigger/` 的 `legacy_command_retired` 回應；Request Body 不再解析。

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

**`hallucination_mismatch` 案件已全面退役**：`_ensure_active_review()` 一律拋出 `LegacyManualReviewRetiredError`（API 回 410 `legacy_command_retired`），核准／駁回都不會執行；`services/quote_summary_template.py` 這個舊版樣板檔案已刪除，不再有任何程式碼引用。此類案件僅供歷史查閱，不能再決議。
**核准（`supplier_fuzzy_match`）**（2026-09-02 改版，見 `docs/ADR/debug/phase5-security.md`）：確認 `manual_review_queue.supplier_id`；DB 交易確定提交（含把 `resume_status` 先落地為 `pending`）後，Django 直接在內部重新解析原始需求，不再交還 n8n 續傳 webhook（該路徑舊版會打進已退役的 `quotes/calculate/`／`quotes/verify-hallucination/`，核准後實際上無法完成）。流程：用已確認的供應商全名重新遮罩原始輸入（`mask_confirmed_supplier_text`，不重新跑模糊比對；找不到可定位的供應商片段時 fail-closed 中止，不會把真實供應商名稱未遮罩送往外部 LLM）→ 呼叫既有的候選解析 n8n webhook（與 `POST /api/v1/inquiries/parse/` 共用同一個端點；此端點仍是必要的外部 AI 呼叫，「略過 n8n」指的是不再由 n8n 負責續傳編排本身，不是不需要任何 n8n／LLM 呼叫）解析品項 → 解析成功且無缺漏欄位時，自動建立一筆 `PurchaseRequest` 草稿（`source="manual_review_resume"`，`requester` 為原始詢價發起人），可在「我的採購需求」看到並自行編輯提交。解析失敗（AI 服務連線失敗、格式錯誤、無法安全定位供應商名稱）、仍有缺漏欄位、或發起人沒有 `purchase_request.create` 權限等情況，不建立草稿——決議本身仍然成功，只是需要人工確認後續（不影響這支 API 本身的核准結果，DB 裡供應商已確認的事實不因此回滾）。**續傳結果落地保存**（2026-09-02 新增，見 `docs/ADR/discuss/main-flow.md`「持久化續傳狀態與重試」條目、Migration `audit/0004_manualreviewqueue_created_purchase_request_and_more`）：成功／失敗都寫回 `manual_review_queue.resume_status`／`resume_error_code`／`created_purchase_request_id`，失敗時可呼叫 `POST /api/v1/manual-review-queue/{id}/retry-resume/` 重試，不需要整個案件重新走一次核准流程。
**駁回（`supplier_fuzzy_match`）**：不異動供應商欄位，不觸發重新解析，通知申請人確認供應商全名後重新送出；`resume_status` 維持預設值 `not_applicable`。

**Response（200）**：回傳更新後的 `manual_review_queue` 資料列（`status` 變為 `resolved`），含 `resume_status`（`not_applicable`／`pending`／`succeeded`／`failed`）、`resume_error_code`（`resume_status=failed` 時的非敏感錯誤代碼；成功或不適用時為 `null`）、`created_purchase_request`（`resume_status=succeeded` 時為自動建立的採購需求草稿 id，可用於導去 `GET /api/v1/purchase-requests/{id}/`，否則為 `null`）。`resume_error_code` 合法值：`invalid_input`（原始輸入為空）、`unmaskable_supplier`（找不到可定位的供應商片段，fail-closed 中止）、`parse_failed`（AI 需求解析服務逾時／連線失敗／回傳格式錯誤，可重試）、`missing_fields`（解析成功但仍有缺漏欄位）、`permission_denied`（發起人沒有 `purchase_request.create` 權限）、`draft_creation_failed`（品項/供應商在建立當下被停用等）、`resume_data_error`（找不到已確認的供應商／原始發起人，理論上不該發生的資料整合性問題）。

**Response（400）**：`decision` 缺漏、`decision` 非 `approved`／`rejected`、或核准模糊比對案件卻缺少可用的 `supplier_id`。

**Response（401／403）**：未登入／非管理員。

**Response（409）**：案件尚未認領、已結案，或非本人認領。

## POST /api/v1/manual-review-queue/{id}/retry-resume/

FR-6a 續傳重試（2026-09-02 新增，見 `docs/ADR/discuss/main-flow.md`「持久化續傳狀態與重試」條目）：只有已核准的 `supplier_fuzzy_match` 案件、且上次續傳結果為 `resume_status=failed` 時才能重試，不需要整個案件重新走一次核准流程；成功／再次失敗的結果落地方式與 `decide` 核准時相同。權限與 `decide` 相同（需 `manual_review.decide`）。

**Request Body**
無 Request Body。

**Response（200）**：回傳更新後的 `manual_review_queue` 資料列（`resume_status` 依重試結果變為 `succeeded`／`failed`）。

**Response（400）**：案件不存在、非 `supplier_fuzzy_match`、尚未核准、或原始輸入/發起人/供應商資料整合性問題。

**Response（401／403）**：未登入／非管理員。

**Response（409）**：案件目前 `resume_status` 不是 `failed`（例如仍在 `pending` 或已 `succeeded`），無法重試。

## GET /api/v1/audit-dashboard/stats/

SPEC「採購稽核與流程健康總覽」FR-1～5 統計聚合，需 `audit.read`。

**認證／權限**：Bearer Access Token；需 `audit.read`。

**Query Parameters**：`date_from`、`date_to`（皆選填，`YYYY-MM-DD`，套用在各卡片各自的時間欄位；
格式不合法時視為未提供，不回錯誤）。

**Response（200，假資料）**：
```json
{
  "period": {"from": null, "to": null},
  "candidate_quality": {
    "direct_adoption_count": 12, "corrected_count": 3,
    "direct_adoption_rate_pct": "80.00", "corrections_by_field": {"items.quantity": 2}
  },
  "supplier_match": {
    "supplier_matched_count": 14, "supplier_unmatched_count": 1,
    "product_matched_count": 20, "product_unmatched_count": 2,
    "fuzzy_match_total": 5, "fuzzy_match_approved": 3, "fuzzy_match_rejected": 1, "fuzzy_match_pending": 1
  },
  "manual_review_queue": {
    "pending_count": 2, "processed_count": 10,
    "by_decision": {"approved": 7, "rejected": 3}
  },
  "price_anomaly": {
    "threshold_pct": "20.00", "checked_count": 8, "anomaly_count": 1, "anomaly_rate_pct": "12.50",
    "items": [
      {
        "supplier_quote_item_id": 501, "rfq_no": "RFQ-DEMO-001", "supplier_id": 31,
        "supplier_name": "範例供應商 A", "product_id": 10, "product_name": "A產品-辦公椅",
        "unit_price": "150.00", "historical_average": "100.00", "deviation_pct": "50.00", "currency": "TWD"
      }
    ]
  },
  "quality": {
    "inspection_count": 6, "accepted_quantity": "48.000",
    "exception_quantity": "2.000", "acceptance_rate_pct": "96.00"
  }
}
```

`candidate_quality` 只統計帶有效後端簽章候選憑證的首次草稿建立；`supplier_match` 的命中數量來自
去識別化 `candidate_parsed` 事件。`price_anomaly` 只納入
正式（`submitted`／`accepted_for_evaluation`／`revised`）`SupplierQuoteItem`，比對
`PurchaseRequestRepository.historical_average_price`（同供應商＋品項＋幣別的歷史已核准採購單均價），
門檻沿用 FR-4a 既有 20%，無歷史均價可比對的品項不計入 `checked_count`。無權限回 403。

## 採購單與簽核 Action

### POST /api/v1/quotes/{id}/withdraw/

legacy 撤回 command 已停用。任何已登入使用者呼叫皆統一回 `410 Gone`／`legacy_command_retired`（不
套用 `quotes` 唯讀查詢用的 permission code，避免把「已停用」誤呈現成「沒有權限」），Quote／Approval
狀態不會被改動。正式撤回請改用 `POST /api/v1/purchase-requests/{id}/withdraw/`。

### POST /api/v1/approvals/{id}/claim/／POST /api/v1/approvals/{id}/decide/

legacy Approval command 已停用。通過 Bearer Access Token 認證後統一回 `410 Gone`：

```json
{
  "detail": "舊版詢價建單流程已停用，請改用採購需求流程",
  "code": "legacy_command_retired"
}
```

未通過認證仍回 401。legacy Approval 的 GET 清單／詳情暫時保留歷史查詢；正式簽核一律改用
`approval-cases`／`approval-steps`。
