# DB Schema 討論紀錄

> 同一功能的多次討論都寫在同一個檔案，依時間往下附加新段落，不要開新檔案。

## 2026-08-24 [標籤：使用者] 資料表初版設計、欄位命名與角色正規化

**狀態**：accepted

**背景**：`docs/reference/db_schema.md` 尚未建立，需要把先前各功能討論（遮罩、複核佇列、簽核金額門檻、認證機制）隱含需要的欄位落地成正式表格設計，並依使用者指示調整欄位命名與角色模型。

**討論內容**：
- 初版草案提出後，使用者要求多項欄位改名，統一風格（如 `unit_price`→`price`、`decided_at`→`created_at`/`updated_at` 慣例、外鍵一律用 `user_id`/`supplier_id` 這種簡短命名）。
- 使用者要求把 `users.role`、`users.approval_amount_limit` 移到新的 `roles` 表（欄位：`id`、`role`、`approval_amount_limit`），`users` 改用 `role_id` 外鍵參照。
- 這項異動與 2026-08-24「簽核金額門檻與層級設計」（見 `docs/ADR/discuss/main-flow.md`）決策 2「不新增子角色，於使用者資料表加簽核金額上限欄位，同角色不同人可有不同上限」直接衝突——若金額上限改放 `roles` 表，同一角色底下所有使用者的上限會變成一致。
- 針對此衝突提出兩個選項請使用者決定：(a) 角色不再限於 3 種固定值，改成多種細分角色（如 `approver_50k`、`approver_100k`），每種角色自帶固定金額上限，用「角色種類變多」取代「同角色不同人不同上限」；(b) 放棄個人化上限，同角色一律同上限。使用者選擇 (a)。
- `suppliers.tier`、`inventory.stock_qty`、`purchase_suggestions.suggested_qty` 三個欄位使用者提出「看不懂用途」，已說明：`tier` 是合作等級的資訊呈現標籤（不驅動流程邏輯）；`stock_qty` 是目前庫存數量，用來跟 `threshold` 比較；`suggested_qty` 是系統建議的補貨數量。使用者未要求移除，維持保留。

**決策**：
1. 新增 `roles` 表（`id`、`role`、`approval_amount_limit`）取代 `users.role` 與 `users.approval_amount_limit`；`users` 新增 `role_id` 外鍵。角色不再限於 employee/approver/admin 三種固定值：`employee`、`admin` 為保留角色代碼，其餘可依需要新增多種簽核相關角色，各自帶固定金額上限，藉此達成「不同簽核人不同金額上限」的效果。
2. **此決策取代** `docs/ADR/discuss/main-flow.md` 中 2026-08-24「簽核金額門檻與層級設計」的決策 2（原決策：不新增子角色、於使用者資料表加欄位）。原決策已於該檔案標記 superseded 並連結回本篇。FR-7a 的路由邏輯調整為：依 `roles.approval_amount_limit` 找出上限 ≥ 採購金額中上限最低的角色，取該角色底下的使用者作為對應簽核人。
3. 全面欄位命名調整：
   - `users`：`password_hash`→`password`
   - `products`：`unit_cost`→`price`
   - `quotes`：`requested_by_id`→`user_id`、`unit_price`→`price`
   - `approvals`：`decided_at`→`created_at`，新增 `updated_at`
   - `inventory`：`reorder_threshold`→`threshold`
   - `manual_review_queue`：`fuzzy_matched_supplier_id`→`supplier_id`、`claimed_by_id`→`user_id`、`decided_at`→`updated_at`
   - `audit_logs`：`actor_id`→`user_id`、`related_quote_id`→`quote_id`
4. `suppliers.tier`、`inventory.stock_qty`、`purchase_suggestions.suggested_qty` 維持保留，用途已於本篇說明。

**理由**：角色正規化成獨立資料表，比在 `users` 上直接存金額上限更符合關聯式資料庫設計慣例，也讓「新增一種簽核額度層級」變成新增一筆角色資料、不需要改 schema；欄位命名統一風格降低後續開發時的認知負擔。

**後果**：
- Django models／migrations 需依此設計建立（Phase 1），`roles` 表需要至少的種子資料（如 `employee`、`approver_50k`、`approver_100k`、`admin`）。
- SPEC.md 的 FR-7a、權限管理模組 FR-4 需同步更新為「角色正規化＋roles 表」的描述，`main-flow.md` 對應決策標記 superseded。
- JWT payload（見 `docs/ADR/discuss/permissions.md`）原本規劃放「角色」，現在對應到 `roles.role`（角色代碼字串），內容決策不變，僅底層資料來源改變。
