---
title: DB Schema
updated: 2026-09-02
---

# DB Schema

> 技術參考文件，跟著程式碼異動更新，不是決策紀錄（決策放 `docs/ADR/discuss/`）也不是產品規格（放
> `docs/specs/SPEC.md`）。內容力求簡述；設計理由與討論過程見 `docs/ADR/discuss/db-schema.md`。
>
> **開發資料庫已套用**：core `0003_permission_rolepermission_userrole`、
> crm `0002_supplier_code_supplier_contact_supplier_is_active_and_more`、
> erp `0008_variance_case_close_guard`、
> procurement `0011_purchase_request_rejected_status`、
> audit `0004_manualreviewqueue_created_purchase_request_and_more`。

## Phase 4.1 A1～A3

### permissions／user_roles／role_permissions

| Table | Column | 型別 | Nullable／Default | PK／FK／Constraint | 說明 |
| --- | --- | --- | --- | --- | --- |
| permissions | id | bigint | identity | PK | 權限 ID |
| permissions | code | varchar(100) | 否 | Unique、非空字串 | 權限代碼 |
| permissions | name／description | varchar(100)／text | description 預設空字串 | | 顯示名稱與用途 |
| permissions | created_at | timestamptz | DB now() | | 建立時間 |
| user_roles | id | bigint | identity | PK | 指派 ID |
| user_roles | user_id／role_id | bigint | 否 | → users／roles；複合 Unique | 使用者持有角色 |
| user_roles | valid_from／valid_until | timestamptz | from=DB now()；until nullable | until > from；user+until index | 有效期間 |
| user_roles | assigned_by_id | bigint | nullable | → users，刪除時 SET NULL | 授權者；migration 回填可空 |
| user_roles | created_at | timestamptz | DB now() | | 建立時間 |
| role_permissions | id | bigint | identity | PK | 對照 ID |
| role_permissions | role_id／permission_id | bigint | 否 | → roles／permissions；複合 Unique | 角色所含權限 |
| role_permissions | created_at | timestamptz | DB now() | | 建立時間 |

core `0003` 會以 `users.role_id` 回填 `user_roles`，但保留舊欄位供 dual-read；不切換現有 API 權限行為。

### product_categories 與 products 擴充

| Table | Column | 型別 | Nullable／Default | PK／FK／Constraint | 說明 |
| --- | --- | --- | --- | --- | --- |
| product_categories | id | bigint | identity | PK | 類別 ID |
| product_categories | code／name | varchar(50)／varchar(100) | 否 | code Unique | 類別代碼與名稱 |
| product_categories | spec_schema | jsonb | `{}` | JSON object check | 規格驗證定義 |
| product_categories | is_active | boolean | true | | 是否可供新產品使用 |
| product_categories | created_at／updated_at | timestamptz | DB now() | updated_at trigger | 建立／更新時間 |
| products | category_id | bigint | nullable | → product_categories，PROTECT | 舊產品可暫無類別 |
| products | sku | varchar(100) | nullable | Partial Unique | 企業品項代碼，不以假值回填 |
| products | description | text | 空字串 | | 品項描述 |
| products | specifications | jsonb | `{}` | JSON object check | 受類別規格定義驗證的值 |
| products | unit_of_measure | varchar(20) | `EA` | | 計量單位 |
| products | is_active | boolean | true | | 是否可用於新交易 |
| products | updated_at | timestamptz | DB now() | updated_at trigger | 最後更新時間 |

既有 `products.price`／`currency` 暫留供 Phase 4 legacy 流程使用；正式交易未切換前不移除。

### suppliers 擴充

| Column | 型別 | Nullable／Default | PK／FK／Constraint | 說明 |
| --- | --- | --- | --- | --- |
| code | varchar(50) | nullable | Partial Unique | 企業供應商代碼，不以假值回填 |
| status | varchar(20) | `active` | Check active/on_hold/blocked | 供應商狀態 |
| tax_id | varchar(30) | nullable | Partial Unique | 稅籍識別碼 |
| contact | jsonb | `{}` | JSON object check | 聯絡資料；API 依權限遮罩 |
| payment_terms | varchar(100) | 空字串 | | 預設付款條件 |
| is_active | boolean | true | | 是否可用於新交易 |
| updated_at | timestamptz | DB now() | updated_at trigger | 最後更新時間 |

### supplier_products／supplier_price_versions

| Table | Column | 型別 | Nullable／Default | PK／FK／Constraint | 說明 |
| --- | --- | --- | --- | --- | --- |
| supplier_products | id | bigint | identity | PK | 供應關係 ID |
| supplier_products | supplier_id／product_id | bigint | 否 | → suppliers／products；複合 Unique；PROTECT | 供應商與品項 |
| supplier_products | supplier_sku | varchar(100) | 空字串 | | 供應商品號 |
| supplier_products | lead_time_days | int | 0 | >= 0 | 預設交期 |
| supplier_products | minimum_order_quantity | numeric(14,3) | 1.000 | > 0 | 最小訂購量 |
| supplier_products | quality_status | varchar(20) | qualified | Check qualified/conditional/blocked | 品質資格 |
| supplier_products | is_active | boolean | true | | 是否可用於新 RFQ |
| supplier_products | created_at／updated_at | timestamptz | DB now() | updated_at trigger | 建立／更新時間 |
| supplier_price_versions | id | bigint | identity | PK | 價格版本 ID |
| supplier_price_versions | supplier_product_id | bigint | 否 | → supplier_products，PROTECT | 供應關係 |
| supplier_price_versions | unit_price／currency | numeric(14,2)／varchar(3) | 否／TWD | price >= 0；三碼大寫幣別 | 單價與幣別 |
| supplier_price_versions | minimum_quantity | numeric(14,3) | 1.000 | > 0 | 價格級距起點 |
| supplier_price_versions | valid_from／valid_until | timestamptz | until nullable | until > from；GiST 不重疊 | 有效期間 |
| supplier_price_versions | created_by_id | bigint | 否 | → users，PROTECT | 建立人 |
| supplier_price_versions | created_at | timestamptz | DB now() | | 建立時間；版本不可變 |

### approval_policies／approval_policy_steps

| Table | Column | 型別 | Nullable／Default | PK／FK／Constraint | 說明 |
| --- | --- | --- | --- | --- | --- |
| approval_policies | id | bigint | identity | PK | 政策 ID |
| approval_policies | name／currency | varchar(100)／varchar(3) | 否 | 三碼大寫幣別 | 政策名稱／幣別 |
| approval_policies | min_amount／max_amount | numeric(14,2) | max nullable | min >= 0；max > min；GiST 不重疊 | 左含右不含金額區間 |
| approval_policies | active_from／active_until | timestamptz | until nullable | until > from；GiST 不重疊 | 政策有效期間 |
| approval_policies | is_active | boolean | true | lookup index | 是否可供新案件選用 |
| approval_policies | waiver_role_id | bigint | nullable | → roles，PROTECT；FK index | 必要條件例外的獨立覆核角色；NULL 表示未設定 |
| approval_policies | created_at／updated_at | timestamptz | DB now() | updated_at trigger | 建立／更新時間 |
| approval_policy_steps | id | bigint | identity | PK | 步驟 ID |
| approval_policy_steps | policy_id／role_id | bigint | 否 | → approval_policies CASCADE／roles PROTECT | 政策與核准角色 |
| approval_policy_steps | sequence | int | 否 | > 0；policy+sequence Unique | 執行順序 |
| approval_policy_steps | decision_mode | varchar(10) | any_one | Check any_one/all | 同一步驟決議模式 |
| approval_policy_steps | created_at | timestamptz | DB now() | | 建立時間 |

Demo seed 可重跑地建立 TWD `[0,10000)`、`[10000,100000)`、`[100000,∞)` 三段政策；大額使用獨立
`procurement_director`，不讓 `admin` 因系統管理權自動取得業務決議權。三段政策的 waiver
覆核角色為 `procurement_exception_reviewer`，Demo 由 Carol 與 David 持有。`btree_gist` 為共用 PostgreSQL
extension，Migration 只 `CREATE EXTENSION IF NOT EXISTS`，Reverse 不刪除。

## Phase 4.1 B1（開發資料庫已套用）

Migration：procurement `0005_purchaserequest_purchaserequestitem_and_more`。

| Table | 核心欄位 | PK／FK／Constraint | 說明 |
| --- | --- | --- | --- |
| purchase_requests | request_no、requester_id、status、purpose、needed_by、currency、source、legacy_quote_id、idempotency_key、version、timestamps | PK；request_no／idempotency_key／legacy_quote_id Unique；requester→users、legacy→quotes PROTECT；三碼幣別、狀態（含獨立 rejected／cancelled）與 version Check；requester+status index | 多品項採購需求單；legacy FK 暫空 |
| purchase_request_items | request_id、line_no、product_id、description_snapshot、specification_snapshot、quantity、unit_of_measure、created_at | PK；request→purchase_requests CASCADE、product→products PROTECT nullable；request+line Unique；line／quantity > 0；spec JSON object | 需求品項與規格快照，數量 numeric(14,3) |
| request_item_requirements | request_item_id、code、label、data_type、operator、expected_value、is_mandatory、created_at | PK；request item CASCADE；item+code Unique；data type／operator 白名單 | 必要條件與評選條件快照 |
| rfqs | rfq_no、request_id、revision、status、response_due_at、rule_snapshot、version、timestamps | PK；request→purchase_requests PROTECT；rfq_no+revision Unique；每 request 一個 active revision partial unique；revision／version > 0；rule JSON object | RFQ 修訂版本與評分規則快照 |
| rfq_suppliers | rfq_id、supplier_id、status、invited_at、responded_at、timestamps | PK；rfq CASCADE、supplier PROTECT；rfq+supplier Unique；responded_at >= invited_at | 每間受邀供應商的獨立回覆狀態 |

`purchase_requests`、`rfqs`、`rfq_suppliers` 的 `updated_at` 由 PostgreSQL trigger 維護。B1 不含舊 Quote
backfill、不含 API 切換，也不建立假交易資料。

## Phase 4.1 B2（開發資料庫已套用）

Migration：procurement `0006_supplierquote_rfqscoringcriterion_and_more`。

| Table | 核心欄位 | PK／FK／Constraint | 說明 |
| --- | --- | --- | --- |
| supplier_quotes | quote_no、rfq_supplier_id、revision、status、currency、exchange_rate_to_twd、items_subtotal、tax／shipping／discount、landed_total_twd、付款／有效期／提交時間快照、created_at | PK；invitation→rfq_suppliers PROTECT；quote_no+revision、invitation+revision Unique；每 invitation 一個 active revision partial unique；狀態、三碼幣別、正匯率、非負金額 Check | 每間受邀供應商的獨立版本化報價；immutable revision 不設 updated_at/version |
| supplier_quote_items | supplier_quote_id、request_item_id、quantity、unit_price、subtotal、lead_time_days、warranty_months、specification_snapshot、created_at | PK；quote CASCADE、request item PROTECT；quote+request item Unique；quantity > 0、金額非負、spec JSON object | 報價逐項商務與規格快照 |
| quote_requirement_results | quote_item_id、requirement_id、result、evidence、waiver_reason、waived_by_id、waived_at、created_at | PK；quote item CASCADE、requirement／waived user PROTECT；pair Unique；result 白名單；waived 必須同時具備非空理由、核准者與時間，非 waived 禁帶 waiver 欄位 | 必要／偏好條件符合與例外採用證據 |
| rfq_scoring_criteria | rfq_id、code、label、weight、calculation_method、sequence、created_at | PK；rfq CASCADE；rfq+code、rfq+sequence Unique；weight 0～100、sequence > 0；RFQ issued 起以 trigger 保證總權重 100 | RFQ 評分規則案件快照 |
| supplier_quote_scores | supplier_quote_id、criterion_id、raw_value、normalized_score、weighted_score、created_at | PK；quote CASCADE、criterion PROTECT；quote+criterion Unique；raw JSON object；分數 0～100 | Django 固定公式結果快照；AI 不寫入分數 |

B2 Migration 僅新增五張表、FK、索引、constraint 與權重檢查 trigger，不修改 legacy 表、不搬資料、不切換
API。Robin 核准後已成功套用；套用後五張新表均為 0 筆。

## Phase 4.1 B3（開發資料庫已套用）

Migration：procurement `0007_awarddecision_approvalcase_awardline_purchaseorder_and_more`。

| Table | 核心欄位 | PK／FK／Constraint | 說明 |
| --- | --- | --- | --- |
| award_decisions | rfq_id、revision、status、recommended_quote_id、selected_by_id、selection_reason、submitted_at、created_at | PK；rfq／recommended quote／selected user PROTECT；rfq+revision Unique；每 RFQ 一個 active 方案；送出時間與狀態成組 | 一次選商方案版本 |
| award_lines | award_id、request_item_id、supplier_quote_item_id、awarded_quantity、unit_price_snapshot、amount_snapshot、reason | PK；award CASCADE，request／quote item PROTECT；award+quote item Unique；數量正數、金額非負；trigger 確保跨表關聯一致 | 支援逐項與同品項拆量；submitted 時各品項加總必須等於需求量 |
| approval_cases | award_id、policy_id、requester_id、policy_snapshot、total_amount、currency、status、submitted/decided_at、version、timestamps | PK；award OneToOne；policy／requester PROTECT；狀態、幣別、非負金額、JSON object、version Check | 針對得標方案的政策快照與簽核案件 |
| approval_steps | approval_case_id、sequence、step_type、role_id、role_snapshot、status、claimed/decided actor/time、decision_reason、timestamps | PK；case CASCADE，role／users PROTECT；case+sequence Unique；step type Check；狀態與認領／決議欄位必須成組 | 多關簽核快照；waiver_exception 必須於 amount_approval 之前；Service 以 row lock 防競態 |
| purchase_orders | po_no、award_id、supplier_id、status、currency、total_amount、issued/closed/cancelled_at、version、timestamps | PK；po_no Unique；award+supplier Unique；FK PROTECT；狀態、幣別、非負金額、version Check | 核准後依得標供應商拆單 |
| purchase_order_items | purchase_order_id、award_line_id、line_no、product_id、product_name/specification_snapshot、ordered_quantity、unit_price、amount、created_at | PK；PO CASCADE；award line OneToOne；product PROTECT nullable；PO+line Unique；數量正數、金額非負、spec JSON object | 正式採購品項與價格快照；不因後續主檔修改而改變 |

B3 只新增六張表、FK／index／constraint、`updated_at` trigger 與得標數量延遲檢查 trigger；
不修改 legacy 表、不回填、不切換 API／UI。Robin 核准後已成功套用，六張新表均為 0 筆。

### C5-2 waiver 雙人覆核結構（開發資料庫已套用）

Migrations：procurement `0010_approval_waiver_steps`、`0011_purchase_request_rejected_status`。

| Table | 核心欄位 | PK／FK／Constraint | 說明 |
| --- | --- | --- | --- |
| approval_policies | waiver_role_id | roles PROTECT，nullable，FK index | 每個金額政策可設定 waiver 獨立覆核角色 |
| approval_steps | step_type | NOT NULL，default amount_approval，Check waiver_exception/amount_approval | 區分必要條件例外關卡與一般金額簽核 |
| approval_step_waivers | id、approval_step_id、quote_requirement_result_id、created_at | PK；step CASCADE，result PROTECT；step+result Unique；兩個 FK index | 正規化保存例外關卡實際覆核的 waiver |

`0010` 將既有 `approval_steps` 回填為 `amount_approval`，不改動其決議紀錄；`0011` 只擴充
`purchase_requests_status_check` 與欄位註解，加入獨立 `rejected` 狀態，不更新既有資料列。

## Phase 4.1 B4（開發資料庫已套用）

Migration source：erp `0003_receiving_inventory_ledger`。

| Table | 核心欄位 | PK／FK／Constraint | 說明 |
| --- | --- | --- | --- |
| goods_receipts | receipt_no、purchase_order_id、status、received_by_id、received_at、legacy_quote_id、version、timestamps | PK；receipt_no／legacy quote Unique；PO／user／legacy quote PROTECT；狀態、收貨時間、version Check；updated_at trigger；received_by 僅 legacy 可空 | 採購單分批收貨主檔 |
| goods_receipt_items | receipt_id、purchase_order_item_id、received_quantity、lot_no、created_at | PK；receipt CASCADE、PO item PROTECT；receipt+PO item Unique；數量正數；trigger 鎖定 PO item 並防跨單與累計超收 | 每次收貨的逐項實收數量 |
| quality_inspections | receipt_item_id、status、accepted／defective／rejected quantity、defect_details、inspected_by/at、notes、created_at | PK；receipt item OneToOne PROTECT；user PROTECT；三種數量非負且加總等於實收；狀態與數量一致；inspected_by 僅 legacy receipt 可空；瑕疵時說明必填；禁止 UPDATE／DELETE | 最終品質驗收；只有 accepted 可入庫 |
| inventory_movements | product_id、movement_type、quantity_delta、reference type/id、affects_balance、reason、posted_at/by、created_at | PK；product／user PROTECT；reference+type Unique；類型、正負方向、非零數量及 legacy 不影響餘額 Check；receipt_accept 必須對應驗收合格數量；禁止 UPDATE／DELETE | append-only 庫存真相來源；錯誤以 reversal 更正 |
| inventory_balances | product_id、on_hand／reserved／in_transit quantity、version、timestamps | product 為 PK/FK PROTECT；數量非負、version > 0；updated_at trigger | 庫存查詢快照；後續 Service 與 movement 在同一 transaction 更新 |

### C6-3 驗收差異與補交授權（開發資料庫已套用）

Migration source：erp `0005_inspection_variances`（Schema／約束）、
`0006_inspection_variance_comments`（forward-only 補齊欄位註解）與
`0007_variance_line_status_transition`（受控完成與補交狀態防線）與
`0008_variance_case_close_guard`（全明細完成後才能結案）。

| Table | 核心欄位 | PK／FK／Constraint | 說明 |
| --- | --- | --- | --- |
| inspection_variance_cases | quality_inspection_id、status、version、created/submitted/closed actor 與時間 | PK；inspection OneToOne PROTECT；actor PROTECT；version > 0；updated_at trigger；open／closed 時 deferred trigger 驗證完整拆量及 actor；closed 僅能由 open 進入且全明細必須 completed | 一筆不合格驗收的正式後續處理案件 |
| inspection_variance_lines | variance_case_id、action_type、quantity、status、reason、completed actor/time | PK；case／actor PROTECT；quantity > 0；reason 非空；action 與 status Check；案件離開 draft 後核心內容禁止 UPDATE／DELETE，僅允許一次附 actor/time 的 pending → completed | 可拆量記錄 replacement／return／credit／waive |
| goods_receipt_items | replacement_variance_line_id | nullable → inspection_variance_lines，PROTECT、FK index | NULL 為一般收貨；補交時必須引用同 PO 品項、open 案件且仍為 pending 的 replacement，累計不得超過核准量 |
| purchase_suggestions | suggested_qty、status、source_movement_id、purchase_request_id | 數量改 numeric(14,3)；status Check；movement／request nullable PROTECT、FK index | 支援 pending → in_progress → processed／dismissed 並保留來源與轉單關聯；應用層以同品項 pending／in_progress 去重 |

一般收貨仍由 DB trigger 阻擋累計超過訂購量；只有具正式 replacement 明細的補交可使用獨立額度。既有資料不回填，新增 FK 均允許 NULL。

B4 只新增五張表、FK／index／constraint、trigger 與 PL/pgSQL 驗證函式；不修改 legacy `inventory`／`quotes`、
不回填資料、不切換 API／UI。Robin 核准後已成功套用 erp `0003`，五張新表均為 0 筆。

### C1 legacy actor 例外與 Quote 回填（開發資料庫已套用）

erp `0004_legacy_receipt_actor_exception` 將 `goods_receipts.received_by_id` 與
`quality_inspections.inspected_by_id` 改為 nullable，但 DB 條件仍強制非 legacy 收貨必須有 actor。
`goods_receipts` 以 Check Constraint 限制；`quality_inspections` 以 trigger 追溯 receipt 的
`legacy_quote_id`。此例外只表示舊系統未保存 actor，不代表任何人實際執行收貨或驗收。

procurement `0009_backfill_legacy_quotes` 是 atomic `RunPython` data migration；以
`purchase_requests.legacy_quote_id` 作可重跑唯一根鍵，建立單品項的 legacy request／RFQ／報價／
得標鏈。approved 才建立 PO／收貨／驗收與 `migration_assumed_receipt`，其
`affects_balance=false`；不寫入 `inventory_balances`。Reverse 只透過非空 legacy root 刪除 C1 圖譜，
不更新或刪除 legacy Quote／Approval／Inventory。

開發資料庫已回填 9 筆 legacy Quote：9 筆 purchase request／RFQ／報價／得標鏈、
9 個 approval cases、6 個有原 Approval 來源的 steps，以及 4 組 approved PO／收貨／驗收／
migration movement。金額與關聯對帳錯誤為 0；庫存餘額未被回填異動。

## Phase 4.1 B5（開發資料庫已套用）

Migration source：procurement `0008_concurrent_indexes`；`atomic=False`，以 `SeparateDatabaseAndState`
同步 PostgreSQL 與 Django ORM state。

| Index | Table／Columns | 用途 |
| --- | --- | --- |
| `pr_status_updated_idx` | purchase_requests(status, updated_at DESC) | 依狀態列出最新需求單 |
| `rfq_status_due_idx` | rfqs(status, response_due_at) | 查詢待回覆或即將到期 RFQ |
| `rfq_supplier_queue_idx` | rfq_suppliers(supplier_id, status, invited_at DESC) | 供應商邀請與回覆佇列 |
| `sq_status_valid_idx` | supplier_quotes(status, valid_until) | 有效報價與到期處理 |
| `approval_step_queue_idx` | approval_steps(role_id, status, sequence) | 角色簽核工作佇列 |
| `po_supplier_status_idx` | purchase_orders(supplier_id, status) | 供應商採購單狀態清單 |

Forward 使用 `CREATE INDEX CONCURRENTLY`，Reverse 使用 `DROP INDEX CONCURRENTLY`；不修改資料列、不回填、
不切換 API／UI。Robin 核准後已成功套用；六條索引的 `pg_index.indisvalid` 與 `indisready` 均為 true。
若建立中斷，重跑前須檢查並移除 invalid index。

## roles（角色）

| Column | 型別 | Nullable | Default | PK | FK | Index/Unique | 說明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | bigint | 否 | auto | PK | | | |
| role | varchar(50) | 否 | — | | | Unique | 角色代碼。`employee`、`admin` 為保留值；其餘可自由新增多種簽核相關角色（如 `approver_50k`）|
| approval_amount_limit | decimal(12,2) | 是 | null | | | | 該角色的簽核金額上限；null＝無上限（`admin` 固定 null）；`employee` 不參與簽核路由 |

## users（使用者）

| Column | 型別 | Nullable | Default | PK | FK | Index/Unique | 說明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | bigint | 否 | auto | PK | | | |
| name | varchar(100) | 否 | — | | | | |
| email | varchar(255) | 否 | — | | | Unique | |
| password | varchar(255) | 否 | — | | | | Django 內建雜湊儲存（PBKDF2），非明碼 |
| role_id | bigint | 否 | — | | → roles.id | Index | |
| created_at | timestamp | 否 | now() | | | | |

## refresh_sessions（Refresh Token Session）

| Column | 型別 | Nullable | Default | PK | FK | Index/Unique | 說明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | bigint | 否 | auto | PK | | | |
| user_id | bigint | 否 | — | | → users.id | `refresh_user_active_idx`（未撤銷 session 的 user_id + expires_at） | Session 所有人；使用者刪除時連帶刪除 |
| jti | varchar(36) | 否 | — | | | Unique | JWT 唯一識別碼 |
| token_hash | varchar(64) | 否 | — | | | Unique | Refresh Token SHA-256 雜湊；不保存明文 |
| created_at | timestamp | 否 | now()（DB default） | | | | Session 建立時間 |
| expires_at | timestamp | 否 | — | | | Check：晚於 created_at | 到期時間 |
| revoked_at | timestamp | 是 | null | | | | 登出、rotation 或撤銷時間 |
| replaced_by_id | bigint | 是 | null | | → refresh_sessions.id | | Rotation 後的新 Session；新 Session 刪除時設 null |

## suppliers（供應商，CRM）

| Column | 型別 | Nullable | Default | PK | FK | Index/Unique | 說明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | bigint | 否 | auto | PK | | | |
| name | varchar(200) | 否 | — | | | Unique | |
| tier | varchar(20) | 否 | 'normal' | | | | 合作等級：priority／normal／watch，資訊呈現用途，不驅動流程邏輯 |
| created_at | timestamp | 否 | now() | | | | |

## products（產品，ERP）

| Column | 型別 | Nullable | Default | PK | FK | Index/Unique | 說明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | bigint | 否 | auto | PK | | | |
| name | varchar(200) | 否 | — | | | | |
| price | decimal(12,2) | 否 | — | | | | 成本/單價 |
| currency | varchar(10) | 否 | 'TWD' | | | | |

## quotes（採購單）

| Column | 型別 | Nullable | Default | PK | FK | Index/Unique | 說明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | bigint | 否 | auto | PK | | | |
| user_id | bigint | 否 | — | | → users.id | Index | 申請人 |
| supplier_id | bigint | 否 | — | | → suppliers.id | Index | |
| product_id | bigint | 否 | — | | → products.id | Index | |
| quantity | int | 否 | — | | | | |
| price | decimal(12,2) | 否 | — | | | | 單價（試算當下的真實數字） |
| total_amount | decimal(14,2) | 否 | — | | | | |
| currency | varchar(10) | 否 | — | | | | |
| ai_summary_text | text | 是 | null | | | | LLM 生成摘要；複核核准後改存系統制式文字 |
| status | varchar(30) | 否 | 'pending_verification' | | | | pending_verification／pending_review／pending_approval／approved／rejected／cancelled |
| price_deviation_pct | decimal(6,2) | 是 | null | | | | 本次單價與該供應商+產品歷史已核准均價的偏離百分比；null＝過去無已核准紀錄可比較 |
| source_suggestion_id | bigint | 是 | null | | → purchase_suggestions.id | | 若此次詢價回應某筆採購建議而發起，核准後標記該建議為 processed |
| created_at | timestamp | 否 | now() | | | | |

## approvals（簽核紀錄）

Migration `procurement/0003_backfill_pending_approvals` 會為既有 `pending_approval` 且缺少 Approval 的
Quote 依現行金額門檻補建一筆路由；不修改已有 Approval 的案件。

| Column | 型別 | Nullable | Default | PK | FK | Index/Unique | 說明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | bigint | 否 | auto | PK | | | |
| quote_id | bigint | 否 | — | | → quotes.id | Unique | 每張 Quote 最多一筆簽核路由 |
| role_id | bigint | 否 | — | | → roles.id | Index | 依 FR-7a 路由邏輯找到的角色；案件建立當下只指派角色，不預先指定特定使用者 |
| approver_id | bigint | 是 | null | | → users.id | Index | 實際認領/決議的使用者；認領前為 null（FR-8a），比照 `manual_review_queue.user_id` 的認領設計 |
| approval_level | varchar(10) | 否 | — | | | | small／medium／large，對應 FR-7 三段金額門檻 |
| status | varchar(20) | 否 | 'pending' | | | | pending／approved／rejected／cancelled |
| created_at | timestamp | 否 | now() | | | | 案件路由建立時間 |
| updated_at | timestamp | 否 | now() | | | | 最後異動時間（認領/核准/駁回時更新） |

## inventory（庫存）

| Column | 型別 | Nullable | Default | PK | FK | Index/Unique | 說明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | bigint | 否 | auto | PK | | | |
| product_id | bigint | 否 | — | | → products.id | Unique | |
| stock_qty | int | 否 | 0 | | | | 目前庫存數量 |
| threshold | int | 否 | — | | | | 低於此值觸發 purchase_suggestions |

## purchase_suggestions（採購建議）

| Column | 型別 | Nullable | Default | PK | FK | Index/Unique | 說明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | bigint | 否 | auto | PK | | | |
| product_id | bigint | 否 | — | | → products.id | Index | |
| suggested_qty | int | 否 | — | | | | 系統建議本次補貨數量，算法於實作階段定案 |
| status | varchar(20) | 否 | 'pending' | | | | pending／processed／dismissed |
| created_at | timestamp | 否 | now() | | | | |

## manual_review_queue（待人工複核佇列）

| Column | 型別 | Nullable | Default | PK | FK | Index/Unique | 說明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | bigint | 否 | auto | PK | | | |
| quote_id | bigint | 是 | null | | → quotes.id | Index | supplier_fuzzy_match 案件在 Mask 階段建立，尚無 Quote，此欄位為 null；hallucination_mismatch 案件照樣填值 |
| requester_user_id | bigint | 是 | null | | → users.id | Index | 原始詢價發起人，模糊比對核准後 Django 直接續傳解析時用來建立採購需求草稿 |
| review_type | varchar(30) | 否 | — | | | | hallucination_mismatch／supplier_fuzzy_match |
| ai_generated_text | text | 是 | null | | | | 幻覺案件用 |
| expected_value | text | 是 | null | | | | 原始真實數字（JSON），幻覺案件用 |
| supplier_id | bigint | 是 | null | | → suppliers.id | | 模糊比對案件：系統疑似比對到的供應商 |
| raw_input_text | text | 是 | null | | | | 模糊比對案件：使用者原始輸入 |
| status | varchar(20) | 否 | 'unclaimed' | | | | unclaimed／claimed／resolved |
| user_id | bigint | 是 | null | | → users.id | | 認領/處理的管理員 |
| decision | varchar(20) | 是 | null | | | | approved／rejected |
| resume_status | varchar(20) | 否 | 'not_applicable' | | | | not_applicable／pending／succeeded／failed，supplier_fuzzy_match 核准後續傳解析的持久化狀態 |
| resume_error_code | varchar(40) | 是 | null | | | | resume_status=failed 時的非敏感錯誤代碼，不含原始例外訊息或供應商名稱 |
| created_purchase_request_id | bigint | 是 | null | | → purchase_requests.id | | resume_status=succeeded 時自動建立的採購需求草稿 |
| created_at | timestamp | 否 | now() | | | | |
| updated_at | timestamp | 否 | now() | | | | 認領/決議/續傳結果更新時更新 |

CheckConstraint（2026-09-02 新增，Migration `audit/0004_manualreviewqueue_created_purchase_request_and_more`）：
`resume_status='succeeded'` 時 `created_purchase_request_id` 不得為 null；`resume_status='failed'` 時
`resume_error_code` 不得為 null。

## audit_logs（稽核 log）

| Column | 型別 | Nullable | Default | PK | FK | Index/Unique | 說明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | bigint | 否 | auto | PK | | | |
| user_id | bigint | 是 | null | | → users.id | Index | 觸發者；系統自動觸發時為 null |
| action_type | varchar(50) | 否 | — | | | | 例如 llm_parse／hallucination_check／review_decision |
| masked_payload | text | 是 | null | | | | 送往 LLM 的脫敏內容 |
| real_query_summary | text | 是 | null | | | | 查了哪張表的摘要 |
| verification_result | varchar(10) | 是 | null | | | | pass／fail／n/a |
| quote_id | bigint | 是 | null | | → quotes.id | Index | |
| created_at | timestamp | 否 | now() | | | | |
