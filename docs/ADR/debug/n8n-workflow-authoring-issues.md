## 2026-08-27 [標籤：AI] n8n workflow 本機驗證：兩個踩坑

**現象**：用 n8n CLI（`n8n import:workflow` + `n8n publish:workflow`）匯入並啟用 `inquiry-flow.json` 後，打 `POST /webhook/inquiry` 回 `200` 但 body 是空的，看不出哪裡錯。

**重現方式**：
1. 本機起一個假的 Gemini mock server（固定回傳結構化 JSON），把 workflow 裡 Gemini 節點的 URL 暫時指向這個 mock（只用於驗證，不隨交付物打包）
2. `n8n import:workflow` 匯入、`n8n publish:workflow` 啟用、重啟 n8n
3. `curl -X POST http://localhost:5678/webhook/inquiry -d '{"raw_text": "..."}'`

**排查過程與根因**：
1. 先查 n8n log，看到兩個 Code node 都回 `Unknown error / undefined`。檢查 workflow JSON 才發現 Code node（`n8n-nodes-base.code`）的參數欄位打成 `jsonCode`，正確欄位名稱是 `jsCode`（JavaScript 模式）；欄位名稱錯誤導致程式碼沒被執行，节点回傳空結果但不報明確錯誤。
2. 修正欄位名稱後重新匯入，log 出現新的訊息：`access to env vars denied`。查到 n8n 2.x 版預設會擋 Code/Expression node 對 `$env` 的存取（安全性預設），workflow 裡多處用了 `{{$env.DJANGO_API_BASE_URL}}`、`{{$env.INTERNAL_API_KEY}}`、`{{$env.GEMINI_API_KEY}}`，全部被擋下。

**修復**：
- `n8n/workflows/inquiry-flow.json`：`jsonCode` → `jsCode`（2 處：「解析 LLM 輸出」「整合查詢結果」節點）
- `n8n/docker-compose.yml`：新增環境變數 `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`

**驗證**：修復後用同一組 mock Gemini + 本機 Django（含 Phase 1 seed 假資料）重跑，`POST /webhook/inquiry` 回傳：
```json
{"product_id":1,"supplier_id":1,"quantity":20,"unit_price":1500,"total_amount":30000,"currency":"TWD","price_deviation_pct":2.39,"price_deviation_flag":false}
```
`price_deviation_pct` 對照 seed 資料中優品科技／A產品-辦公椅的兩筆已核准歷史單價（1450、1480，均價 1465）算出偏離 2.39%，數字正確，流程閉環驗證通過。

**未驗證範圍**：這次驗證用 mock 取代真正的 Gemini API，尚未用真實 `GEMINI_API_KEY` 測試過 Gemini 回應格式是否與 mock 假設的一致（例如是否穩定回傳可直接 `JSON.parse` 的文字、是否會有 ```json 包裹等邊界情況）；使用者申請到金鑰後應補測一次。
