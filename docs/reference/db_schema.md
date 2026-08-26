---
title: DB Schema
updated: 2026-08-26
---

# DB Schema

> 技術參考文件，跟著程式碼異動更新，不是決策紀錄（決策放 `docs/ADR/discuss/`）也不是產品規格（放
> `docs/specs/SPEC.md`）。內容力求簡述；設計理由與討論過程見 `docs/ADR/discuss/db-schema.md`。
>
> **最新 Migration 編號**：`0001_initial`（core／crm／erp／procurement／audit 五個 app 各自的 0001_initial，Phase 1 建立，2026-08-26）。

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

| Column | 型別 | Nullable | Default | PK | FK | Index/Unique | 說明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| id | bigint | 否 | auto | PK | | | |
| quote_id | bigint | 否 | — | | → quotes.id | Index | |
| role_id | bigint | 否 | — | | → roles.id | Index | 依 FR-7a 路由邏輯找到的角色；案件建立當下只指派角色，不預先指定特定使用者 |
| approver_id | bigint | 是 | null | | → users.id | Index | 實際認領/決議的使用者；認領前為 null（FR-8a），比照 `manual_review_queue.user_id` 的認領設計 |
| approval_level | varchar(10) | 否 | — | | | | small／medium／large，對應 FR-7 三段金額門檻 |
| status | varchar(20) | 否 | 'pending' | | | | pending／approved／rejected |
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
| quote_id | bigint | 否 | — | | → quotes.id | Index | |
| review_type | varchar(30) | 否 | — | | | | hallucination_mismatch／supplier_fuzzy_match |
| ai_generated_text | text | 是 | null | | | | 幻覺案件用 |
| expected_value | text | 是 | null | | | | 原始真實數字（JSON），幻覺案件用 |
| supplier_id | bigint | 是 | null | | → suppliers.id | | 模糊比對案件：系統疑似比對到的供應商 |
| raw_input_text | text | 是 | null | | | | 模糊比對案件：使用者原始輸入 |
| status | varchar(20) | 否 | 'unclaimed' | | | | unclaimed／claimed／resolved |
| user_id | bigint | 是 | null | | → users.id | | 認領/處理的管理員 |
| decision | varchar(20) | 是 | null | | | | approved／rejected |
| created_at | timestamp | 否 | now() | | | | |
| updated_at | timestamp | 否 | now() | | | | 認領/決議時更新 |

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
