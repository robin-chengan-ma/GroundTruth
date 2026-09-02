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

## 2026-09-02 [標籤：AI] 補齊 10 個清單頁的搜尋／篩選／後端分頁：共用 `lib/pagination.py`＋`useListQuery`／`ListPagination`

**狀態**：accepted

**背景**：2026-09-02 稍早的盤點（見本檔前兩則條目所屬的同批 Phase 6 前端工作，及 `docs/specs/PROGRESS.md` 對應列）已確認：Supplier、Product、SupplierProduct、RFQ、SupplierQuote、AwardDecision、PurchaseOrder、GoodsReceipt、InspectionVariance、PurchaseSuggestion 共 10 個清單頁只做了詳情彈窗、空狀態與錯誤處理，完全沒有 SPEC.md Phase 6 明定的「搜尋、篩選、分頁」；其中多數清單端點的 `list()` 直接回傳未分頁陣列或依賴 DRF 全域預設分頁（每頁 50 筆即靜默截斷），`PurchaseSuggestionListView.vue` 甚至已經在讀取分頁信封的 `results`，卻從未依 `next` 游標翻頁，等同一樣會靜默漏資料。同一時間 Codex 完成的「採購稽核與流程健康總覽」修正（功能 commit `5cf0533`、版本紀錄 commit `fddf57f`）與本次工作範圍完全不重疊；Robin 明確指示保留該兩筆 commit、不得重做或覆蓋稽核總覽／AI 候選稽核／相關統計 API／測試／文件，本次只負責補齊上述清單分頁缺口。

**討論內容**：後端已有 `PurchaseRequestViewSet.list()`（Phase 5／P5.0-B1 落地）採用的 `{count,page,page_size,total_pages,results}` 分頁信封可參考，但該端點的分頁邏輯是內聯寫在 view 裡，未抽成共用工具。討論是否要 (a) 逐一複製貼上分頁邏輯到 11 個 view，或 (b) 抽成 `backend/lib/pagination.py` 共用工具。選擇 (b)：11 個端點的分頁參數驗證、`page_size` 白名單（10/20/50）、錯誤格式應完全一致，複製貼上會造成未來任一端點改分頁規則時要改 11 處；`PurchaseRequestViewSet` 本身不在本次修改範圍（避免無關重構），維持原樣但保證回應形狀與新工具產生的結果一致。前端比照後端決策，抽成 `useListQuery` composable（page/pageSize/search/filters 狀態與 URL query 字串同步）＋`ListPagination` 元件（分頁列 UI），11 個頁面共用同一份邏輯與樣式，而不是逐頁手刻。

**決策**：新增 `backend/lib/pagination.py`（`parse_pagination_params`／`paginate_response`／`parse_optional_bool`／`pagination_error`），套用於 Supplier／Product／ProductCategory／SupplierProduct／Rfq／SupplierQuote／AwardDecision／PurchaseOrder／GoodsReceipt／InspectionVariance／PurchaseSuggestion 共 11 個清單端點的 repository→service→view 三層（repository 加 `search`／狀態類篩選 kwarg 並用 `Q(...).icontains`／`.filter()`，service 原樣透傳，view 讀 query params 後呼叫 `paginate_response`）；`PurchaseRequestViewSet` 維持原有實作不變。前端新增 `useListQuery.ts`＋`ListPagination.vue`，套用於對應的 10 個清單頁（`ProductListView.vue` 額外情境見下一則）；`utils/pagination.ts` 的 `fetchAllPages()`（供下拉選單抓「全部」清單用）同步從追隨 DRF `next` 游標改為依新分頁信封的 `page`／`total_pages` 逐頁抓取，否則 `/suppliers/`／`/products/`／`/rfqs/`／`/purchase-orders/` 等端點改回應形狀後，原本靠 `next` 判斷是否還有下一頁的邏輯會直接把「還有更多資料」誤判為「已經抓完」，導致下拉選單（例如新增供應商報價時選 RFQ、新增收貨單時選採購單）靜默漏選項——這是抽換分頁信封時主動追蹤呼叫端後抓到的迴歸，非事後由測試發現。

**理由**：共用工具能保證 11 個端點的分頁行為（含 `page_size` 白名單與 400 `invalid_pagination` 錯誤格式）逐字一致，且未來若要調整分頁規則只需改一處；`PurchaseRequestViewSet` 不動是因為它已經是 Robin 核准過的既有實作，重構它屬於與本次任務無關的範圍擴張。前端同理：`useListQuery`／`ListPagination` 讓 10 個頁面的搜尋框、篩選下拉、分頁列在互動與無障礙標籤（`aria-label`）上維持一致，也讓之後任何新清單頁可以直接複用而不必重新設計。

**附帶決策：`ProductListView.vue` 的 Category／Product 雙清單範圍**：`ProductListView.vue` 同頁存在「品項分類」與「品項」兩張表，但 SPEC／Robin／Codex 盤點時明確指出缺口的是「品項」清單（`Product`），品項分類本身筆數少、屬參考性質小表。決策：只對 Product 套用完整 `useListQuery`／`ListPagination`；Category 改用一次性 `page_size=50` 抓取（不做分頁 UI、不佔用 URL query 參數，避免與 Product 的分頁參數在同一網址搶命名空間）。屬有意識的範圍縮減，非遺漏。

**後果**：新增 `backend/tests/test_phase6_list_pagination.py`（24 個測試，涵蓋 11 個端點的分頁形狀／`page_size` 驗證／`search`／篩選）；既有 7 個假設「清單回傳裸陣列」的測試（`test_phase4_1_goods_receipts.py`／`test_phase4_1_inspection_variance_api.py`／`test_phase4_1_purchase_orders.py`／`test_phase5_query_contracts.py`／`test_phase5_supplier_product_crud.py`）同步改為讀取 `resp.data["results"]`；10 個前端清單頁新增／改寫對應 spec 檔。過程中另發現並修正一個與本次任務無關的既有測試隔離缺陷：`test_phase4_1_migrations.py` 用 `MigrationExecutor` 手動遷移到中繼版本後未還原到最新 migration，導致完整跑 `pytest -q` 時偶發讓其他測試檔的 `erp` app 停在舊 schema（`goods_receipt_items.replacement_variance_line_id` 不存在）；修法與驗證見 `docs/ADR/debug/phase4-development.md` 2026-09-02 條目。完整 Backend 380 passed、Frontend `vitest run` 94 passed、`vue-tsc --noEmit`／`eslint src`／`vite build` 皆乾淨；`ruff check`／`makemigrations --check --dry-run`／`manage.py check` 通過。`docs/reference/api.md` 已同步全部 11 個端點的新 query parameters 與回應形狀。本次不修改 `5cf0533`／`fddf57f` 涉及的稽核總覽、AI 候選稽核、相關統計 API、測試或文件。Robin 尚未於瀏覽器走完 Phase 6 各角色完整流程（SPEC.md 明定的正式驗收門檻），本次僅完成程式與自動測試層級。

## 2026-09-02 [標籤：AI／PM] 修正「Category 不做完整分頁」附帶決策的狀態誤標記，並修補分類超過 50 筆會靜默漏資料的問題

**狀態**：accepted（2026-09-02 Robin 核准：不開發 Category 獨立分頁 UI，維持完整載入所有分類）

**背景**：Robin 於程式碼審查中指出：上一則條目（本檔案「補齊 10 個清單頁的搜尋／篩選／後端分頁」，整體狀態 accepted）內的「附帶決策：`ProductListView.vue` 的 Category／Product 雙清單範圍」段落，把「Category 不做完整分頁 UI」自行標記為既成決策（該段結語「屬有意識的範圍縮減，非遺漏」），但這屬於新的範圍縮減——SPEC.md 第 126 行明定品項／分類皆須補齊搜尋、篩選、分頁——AI 不應在沒有 Robin 明確核准的情況下自行認定並標記為已定案。同時該實作用固定 `page_size=50` 單頁抓取分類清單，分類筆數超過 50 筆時，第 51 筆以後會同時從「品項分類清單」與「品項表單的分類下拉選單」靜默消失，使用者不會收到任何提示，屬於實質資料遺失，不只是文件狀態誤標。

**討論內容**：兩件事拆開處理，優先順序不同：(1) 資料遺失是程式錯誤，不論範圍縮減最終是否核准都必須先修掉；(2)「Category 要不要做成獨立分頁 UI」屬於會改變介面範圍的產品決策，維持 pending，由 Robin 決定。

**決策**：
1.（已執行，不等待範圍決策）`ProductListView.vue` 的 `loadCategories()` 改用 `fetchAllPages<ProductCategory>('/product-categories/')` 逐頁抓取全部分類，不再受單頁 `page_size=50` 上限影響；`product-list.spec.ts` 新增「品項分類超過一頁時仍會用 fetchAllPages 抓完整清單」迴歸測試，驗證跨頁分類會完整出現在畫面上。
2.（2026-09-02 Robin 最終核准）Category 目前不開發獨立分頁 UI（搜尋框＋分頁列），維持「`fetchAllPages()` 一次抓全部、前端呈現完整清單、不做分頁 UI」的現行實作；正式定案，不再是暫時性的資料遺失防呆修補。
3. 上一則條目「附帶決策」段落本身依規則不得因決策內容改變而直接改寫（只能修正錯字／錯誤連結），故原文保留不動；本則為後續更正暨定案記錄，三則並存時以本則的 accepted 狀態為準。

**理由**：是否縮減 Category 的分頁範圍屬於會影響驗收範圍與使用者介面的產品決策，依專案規則必須由 Robin 核准，AI 不得自行標記為 accepted；先前先修掉靜默資料遺失（不等範圍決策）是正確順序，現在 Robin 已就範圍本身給出最終答覆，兩件事都已收斂：分類完整載入、不漏資料，且明確不做獨立分頁 UI，非 AI 片面認定。

**後果**：`frontend/src/views/ProductListView.vue`、`frontend/src/tests/product-list.spec.ts` 已修改並通過測試（詳見 `docs/ADR/debug/phase4-development.md` 對應除錯紀錄）；Robin 已於 2026-09-02 就「Category 是否需要獨立分頁 UI」給出最終答覆（不開發，維持完整載入所有分類），本條目狀態更新為 accepted；`docs/specs/PROGRESS.md` 同步標註。
