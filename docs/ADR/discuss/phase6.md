# Phase 6 討論紀錄

> 同一功能的多次討論都寫在同一個檔案，依時間往下附加新段落，不要開新檔案。
> 本檔案記錄 Phase 6（企業採購操作介面）建置過程中，跨越前後端的架構決策；單一功能領域已有專屬
> discuss 檔案時仍以該檔案為主（例如稽核與正確率總覽見 `audit-dashboard.md`），本檔案只收跨領域或
> Phase 6 特有的介面／權限模型決策。

## 2026-09-02 [標籤：AI] RfqSerializer 附加 invited_suppliers／request_items，讓採購人員能看到他人需求明細

**狀態**：accepted

**背景**：實作「建立供應商報價」前端頁面時發現：`POST /supplier-quotes/` 需要 `rfq_supplier_id`（RfqSupplier 邀請關係本身的主鍵），但 `RfqSerializer` 原本只回傳 `supplier_ids`（純 `supplier_id` 陣列），前端無從得知要用哪個 `rfq_supplier_id` 建立報價。同時，建立報價的表單也需要知道需求的品項明細（品項、數量、單位）才能逐項填寫，但 `PurchaseRequestViewSet.retrieve()` 只開放需求本人（`get_owned_request()`），採購人員（`rfq.manage`）雖然對 RFQ 本身有更高層級的讀取權限，卻無法用既有端點查看別人送出的需求明細。

**討論內容**：兩個選項：(a) 新增獨立的 `rfq-suppliers` 查詢端點＋放寬 `PurchaseRequestViewSet.retrieve` 給 `rfq.manage`／`audit.read` 也能查任何需求；(b) 直接在 `RfqSerializer` 附加兩個唯讀欄位（`invited_suppliers[]`、`request_items[]`），複用既有的 RFQ 讀取權限（`rfq.manage` 或 `audit.read`，本就高於一般 `purchase_request.read_own`）。選擇 (b)：RFQ 詳情本來就是「已核准調用這批需求資訊的人才看得到」的場景，沒有必要為此新增一個獨立端點或放寬 PurchaseRequestViewSet 的可視範圍去觸碰另一個資源的既有授權規則；附加欄位純粹是唯讀、可加性，不影響任何既有欄位或寫入路徑。

**決策**：`RfqSerializer` 新增 `invited_suppliers`（含 `rfq_supplier_id`／`supplier_id`／`supplier_name`／`status`／`invited_at`／`responded_at`）與 `request_items`（重用既有 `PurchaseRequestItemSerializer`）兩個 `SerializerMethodField`；`request_no`／`request_purpose` 亦一併附加方便前端顯示標題。不新增端點、不修改 `PurchaseRequestViewSet` 的可視範圍。

**理由**：RFQ 讀取權限（`rfq.manage`／`audit.read`）本就是比 `purchase_request.read_own` 更高層級、更狹義授權過的角色能力，讓這個範圍內的人多看到「這張 RFQ 對應的需求明細快照」屬於同一授權範圍內的合理揭露，不是繞過權限；改動純附加、不影響其他呼叫方。

**後果**：新增 1 個測試（`test_rfq_detail_exposes_invited_suppliers_for_quote_creation`），`docs/reference/api.md` 已同步；`docs/specs/PROGRESS.md` 已記錄。

## 2026-09-02 [標籤：AI] 前端導覽／路由新增 anyPermissions（OR 語意）以正確表達「manage 權限 或 audit.read」

**狀態**：accepted

**背景**：Phase 6 多個新頁面（RFQ、供應商報價、得標方案、採購單、收貨與驗收、驗收差異）依後端 service 層實際授權邏輯（例如 `_require_rfq_read_permission`），是「持有領域 `manage` 權限 **或** `audit.read`」都可讀取，但既有前端 `navigation.ts`／`router/index.ts` 的權限模型只有 AND 語意（`hasAllPermissions`），無法正確表達 OR 條件：若沿用既有模型，只能選擇「只用 manage 權限」（會讓合法的 `audit.read` 稽核角色看不到這些頁面）或「只用 audit.read」（會讓真正負責業務操作的 manage 角色看到但可能誤判權限範圍），兩者都與後端實際授權不一致。

**決策**：在既有 `permissions`（AND）之外新增 `anyPermissions`（OR）欄位，`canAccess()` 同時檢查兩者（`passesAll && passesAny`），`navigation.ts`／`AppShell.vue`／`router/index.ts`／`env.d.ts` 一致套用；新增頁面依各自後端授權規則標註 `anyPermissions`。

**理由**：前端導覽／路由權限判斷應該如實反映後端 service 層的實際授權邏輯，而不是為了遷就既有模型簡化語意；OR 維度是通用的擴充（不是為單一頁面寫死的特例），未來其他「manage 或 audit.read」模式的頁面可直接複用。

**後果**：新增 `navigation.spec.ts`／`app-shell.spec.ts` 測試覆蓋 OR 語意；不影響既有純 AND 權限頁面的行為。
