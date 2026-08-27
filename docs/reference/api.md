---
title: API Reference
updated: 2026-08-27
---

# API Reference

> 技術參考文件，跟著程式碼異動更新，不是決策紀錄（決策放 `docs/ADR/discuss/`）也不是產品規格
> （放 `docs/specs/SPEC.md`）。Phase 1 的 10 個 CRUD 資源（roles/users/suppliers/products/
> inventory/purchase-suggestions/quotes/approvals/manual-review-queue/audit-logs）為標準 DRF
> ModelViewSet CRUD，不逐一列出；這裡只記錄 Phase 2 新增、行為不是單純 CRUD 的端點。

## 認證方式

| 呼叫方 | 端點範圍 | 認證方式 |
| --- | --- | --- |
| Vue 前端 | 一般 CRUD、`inquiries/trigger/` | Phase 1-2 暫開放 `AllowAny`；JWT 認證於 Phase 4 套用（FR-1a） |
| n8n | `quotes/calculate/` | 固定 API Key，自訂 header `X-Internal-Api-Key`，需與 `INTERNAL_API_KEY` 環境變數一致（FR-1a） |

## POST /api/v1/inquiries/trigger/

FR-1：接收自然語言詢價文字，同步呼叫 n8n Webhook（`N8N_INQUIRY_WEBHOOK_URL`），把 n8n 最終回應原樣回傳。

**Request**
```json
{ "raw_text": "幫我訂20個A產品，跟優品科技拿貨" }
```

**Response（200）**：原樣透傳 n8n workflow 的最終輸出（Phase 2 範圍下是 `quotes/calculate/` 的計算結果）。

**Response（502）**：n8n 連線失敗、逾時或回傳非 2xx。
```json
{ "detail": "詢價流程觸發失敗，請稍後再試" }
```

## POST /api/v1/quotes/calculate/

FR-4／FR-4a：固定程式邏輯試算報價金額，並比對該供應商＋產品的歷史已核准均價。只給 n8n 呼叫（需要 `X-Internal-Api-Key`），不開放給前端使用者。**這個端點只回傳計算結果，不會建立 `Quote` 資料列**——正式建單（含幻覺驗證後才落地）留待 Phase 3。

**Request Headers**
```
X-Internal-Api-Key: <INTERNAL_API_KEY>
```

**Request Body**
```json
{ "product_id": 1, "supplier_id": 1, "quantity": 20 }
```
`supplier_id` 可省略（不做歷史均價比對，`price_deviation_pct` 回 `null`）。

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
  "price_deviation_flag": false
}
```
`price_deviation_pct` 為 `null` 代表該供應商＋產品組合過去無已核准紀錄可比較（不視為異常）。
`price_deviation_flag` 為 `true` 代表偏離超過門檻（20%，`services/quote_calculation_service.py` 寫死）。

**Response（400）**：`product_id` 缺漏、`quantity` 非正整數、或找不到指定產品。

**Response（401）**：`X-Internal-Api-Key` 缺漏或錯誤。

## GET /api/v1/suppliers/?search=<name> 、 GET /api/v1/products/?search=<name>

Phase 2 新增 `SearchFilter`（`search_fields=["name"]`），供 n8n 依 LLM 解析出的供應商/產品名稱做查詢，屬既有 CRUD 端點的行為擴充，不是新端點。
