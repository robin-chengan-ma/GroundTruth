# ERP 模組 討論紀錄

> 同一功能的多次討論都寫在同一個檔案，依時間往下附加新段落，不要開新檔案。

## 2026-08-26 [標籤：AI 提案／使用者確認] CRM/ERP 聯動細節：供應商狀態更新、庫存/採購建議串接方式

**狀態**：accepted

**背景**：SPEC.md 通讀檢查時發現，舊版 FR-10「簽核核准後，更新 CRM 供應商狀態、ERP 庫存/採購建議」寫得過於籠統，實際上無法落地：(1) `suppliers` 表沒有「狀態」欄位可更新，也沒定義要更新成什麼；(2) 沒有定義「入庫」的具體機制（是否要有入庫確認步驟、由誰執行）；(3) `quotes` 與 `purchase_suggestions` 之間沒有任何關聯欄位，無法知道一筆核准的採購單是否在回應某筆庫存不足產生的採購建議。使用者請 AI 提出具體建議，AI 提案後經使用者確認採用。

**討論內容**：
- 供應商狀態：討論後決定不新增欄位，因為「最後成交時間」等狀態本質上是可以從 `quotes` 表即時查詢算出的衍生資訊，額外存欄位會有跟來源資料不同步的風險（呼應 AGENTS.md 資料庫設計原則第 7 條：不重複儲存可由既有欄位衍生的資料）。
- 入庫機制：考量這是 demo 系統，範圍原則是「深度夠用即可」，決定不另外設計完整的入庫確認流程（如「已出貨／已到貨／已驗收」多階段狀態機），改用最簡化版本：核准即視同入庫，直接在核准當下把 `inventory.stock_qty` 增加該筆的 `quantity`。
- 庫存門檻檢查時機：討論「排程輪詢」vs「事件驅動即時檢查」，因為本專案已在先前決策中排除所有排程類工具（見 `docs/ADR/discuss/main-flow.md` 部署方式討論的延伸原則），決定採用事件驅動：任何造成 `inventory.stock_qty` 異動的操作（不論是核准增加庫存，或未來管理員手動調整），都在異動當下立即檢查是否低於 `threshold`。
- 採購單與採購建議的關聯：新增 `quotes.source_suggestion_id`（nullable 外鍵），讓「回應某筆庫存不足建議而發起的詢價」可以被追蹤，核准後連動把該建議標記為 `processed`，避免同一個庫存缺口被重複建議。

**決策**：
1. 移除「更新 CRM 供應商狀態」這項籠統敘述；供應商相關狀態一律即時查詢 `quotes` 表，不新增欄位。
2. 簽核核准後，Django 直接將 `inventory.stock_qty` 增加該筆採購的 `quantity`，視同貨物已入庫，不另做入庫確認步驟；ERP 模組 FR-4 據此簡化為「`quotes.status` 本身即為簡化版入庫狀態」。
3. 新增系統主流程 FR-10a：`inventory.stock_qty` 異動後即時檢查是否低於 `threshold`；低於門檻且該產品目前沒有 `pending` 狀態的 `purchase_suggestions` 時，自動新增一筆。明確排除排程輪詢方式。
4. 新增系統主流程 FR-10b：`quotes` 表新增 `source_suggestion_id`（nullable，外鍵 → `purchase_suggestions.id`）；若該筆詢價回應某筆採購建議，核准後連動將對應建議標記為 `processed`。

**理由**：demo 系統的目標是展示「事件觸發自動化」與「跨模組資料聯動」的設計能力，不需要做到企業級的完整入庫審核流程；事件驅動符合專案已定案的「不使用排程工具」原則，也比排程輪詢更即時、更容易在流程圖中清楚展示因果關係。

**後果**：
- `docs/specs/SPEC.md` 系統主流程新增 FR-10a、FR-10b，FR-10 改寫；ERP 模組 FR-2～FR-4 同步改寫；CRM 模組 FR-2 同步移除供應商狀態欄位相關敘述。
- `docs/reference/db_schema.md` 的 `quotes` 表新增 `source_suggestion_id`（bigint，nullable，外鍵 → `purchase_suggestions.id`）欄位。
- Django service 需實作「庫存異動後即時檢查門檻並產生採購建議」與「核准時連動標記來源建議為 processed」兩段邏輯，屬於實作階段任務，記入 PROGRESS.md 追蹤。

## 2026-08-26 [標籤：使用者] 補上 `purchase_suggestions.dismissed` 狀態的對應功能規格

**背景**：SPEC.md 通讀檢查時發現，`purchase_suggestions.status` 欄位定義了 `pending／processed／dismissed` 三種值，`processed` 已有 FR-10b 說明（核准時連動標記），但 `dismissed` 完全沒有對應的功能規格描述誰、在什麼情況下會用到，等於資料庫留了一個沒人使用的狀態值。

**討論內容**：確認情境是「系統依庫存門檻自動產生的採購建議，管理員判斷是誤判或暫時不需要補貨」，此時需要一個「關閉建議、但不產生詢價」的操作，跟「核准後轉為 processed」是兩條不同路徑。權限範圍比照複核佇列（僅管理員），避免為此又新增一組權限規則。

**決策**：
1. ERP 模組新增 FR-5：管理員可在採購建議列表，將 `pending` 狀態的建議手動標記為 `dismissed`（不產生詢價），用於系統誤判或暫不需要補貨的情況。
2. 權限限管理員角色操作，一般員工/簽核人看不到此操作。

**理由**：`dismissed` 狀態值既然已存在於 schema，就必須有對應的產品規格說明其觸發條件，避免規格與資料庫定義不一致；限管理員操作維持跟複核佇列一致的權限收斂原則。

**後果**：
- `docs/specs/SPEC.md` ERP 模組新增 FR-5。
- `docs/reference/db_schema.md` 的 `purchase_suggestions.status` 欄位說明維持原樣（三種狀態值本來就都在），不需新增欄位，僅補齊功能規格文件。
