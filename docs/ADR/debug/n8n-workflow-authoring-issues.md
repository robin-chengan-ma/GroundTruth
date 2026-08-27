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

## 2026-08-27 [標籤：使用者] Gemini 模型名稱過期

**現象**：申請到真實 `GEMINI_API_KEY` 並發布 workflow 後，實際打 `POST /api/v1/inquiries/trigger/`，Django 500，n8n Executions 顯示「Gemini 解析詢價」節點失敗。

**根因**：Gemini 節點呼叫的模型 `models/gemini-2.0-flash` 已被 Google 下架，錯誤訊息明確指示改用 `models/gemini-3.6-flash`。

**修復**：`n8n/workflows/inquiry-flow.json` 的 Gemini 節點 URL 從 `gemini-2.0-flash` 改為 `gemini-3.6-flash`。

**未驗證範圍**：這類雲端 LLM API 的模型名稱會持續變動，未來若又下架需要重新查 Google 官方文件確認最新可用模型名稱，`docs/reference/deploy.md` 或本檔案應同步更新。

## 2026-08-27 [標籤：AI] Phase 3 workflow 本機驗證：4 種分支情境

**現象**：Phase 3 把 workflow 從 7 個節點擴增到 19 個節點（新增 Mask/Unmask 節點、Gemini 摘要生成、幻覺驗證、兩層 IF 分流），改版幅度大，開工前先在本機用 mock 驗證過一輪再交付，避免重蹈 Phase 2 的 `jsonCode`/`$env` 踩坑。

**重現方式**：
1. 本機起假的 Django + Gemini mock server（單一 Python `http.server`，依 path／prompt 內容分流回應），把 workflow 裡兩個 Gemini 節點的 URL 暫時指向 mock（只用於本機驗證，交付物仍指向真實 Gemini endpoint）
2. `n8n import:workflow` 匯入、`n8n publish:workflow` 啟用、重啟 n8n
3. 分別用 4 種 `raw_text` 打 `POST /webhook/inquiry`，對應遮罩層與幻覺驗證的 4 種分支結果

**踩坑與排查**：
1. 本機殘留 Phase 2 舊版 workflow（`groundtruth-inquiry-flow-phase2`）與更早的一次性測試 workflow（`test-inquiry-flow-verify`）都掛在同一個 `/webhook/inquiry` 路徑上，導致新 workflow 啟用時噴 `SQLITE_CONSTRAINT: UNIQUE constraint failed: webhook_entity.webhookPath`；`n8n unpublish:workflow` 之後仍有一筆殘留在 `webhook_entity` 表沒清掉（本機 sqlite 資料庫本身的殘留資料問題，不影響交付物邏輯），直接用 Python 連 sqlite 手動清掉那筆殘留 row 才解決。這是本機驗證環境的殘留資料問題，不是 workflow 設計本身的 bug，記錄下來避免下次又卡在同樣地方。

**驗證結果（4 種情境皆通過）**：
1. **正常成功**：`raw_text` 含完整供應商全名＋數量，回傳 `{quote_id, summary_text, unit_price, total_amount, currency, price_deviation_pct, price_deviation_flag}`，摘要文字數字與試算結果一致。
2. **供應商查無**（FR-2b）：`raw_text` 不含任何已知供應商，直接回覆 `{"detail": "查無供應商，請確認名稱或先建檔"}`，不寫入複核佇列、不呼叫 LLM。
3. **供應商模糊比對**（FR-2b）：`raw_text` 只包含供應商名稱片段，回覆 `{"detail": "供應商身分待人工複核確認，請稍候", "review_id", "candidates"}`，流程在 Mask 節點階段中止。
4. **幻覺驗證失敗**（FR-6）：模擬 Gemini 摘要漏掉一個真實數字，回覆 `{"detail": "報價摘要與真實資料不一致，已建立複核案件，待管理員確認", "review_id", "reasons"}`。

**未驗證範圍**：同 Phase 2 的已知限制——這次驗證用 mock 取代真正的 Gemini API，兩個 Gemini 呼叫（詢價解析、摘要生成）尚未用真實 `GEMINI_API_KEY` 測試過。使用者本機測試真實 Gemini API 後應回報結果，若摘要生成的中文數字/格式與預期不同（例如仍輸出中文數字），需要調整 prompt 用詞。

## 2026-08-27 [標籤：AI] FR-6a 續傳子流程本機驗證：發現並修正節點參照錯誤

**背景**：供應商模糊比對案件經 `manual-review-queue/{id}/decide/` 核准後，Django 主動呼叫 n8n 的 `POST /webhook/inquiry/resume`（架構決策見 `docs/ADR/discuss/main-flow.md`），交還 n8n 重新走「遮罩金額→LLM 解析品項/數量→查詢供應商/產品→試算→摘要→幻覺驗證」流程。這段串接在上一輪驗證時（見前一條目「未驗證範圍」）確認屬於 Phase 3 範圍但尚未實作，本條目記錄補上並驗證的過程。workflow 節點數從 19 增加到 33（新增 14 個「續傳」節點）。

**重現方式**：
1. 沿用既有 mock Django + Gemini server，補上續傳流程需要的三個路由：`GET /api/v1/suppliers/{id}/`（detail route，供應商名稱已知只需查名稱）、`POST /api/v1/masking/mask-amounts-only/`、續傳版 `generateContent`（依 prompt 是否含 `supplier` 欄位描述，分流回傳「只含 item/quantity/currency」的簡化 JSON）
2. 為避免跟正式 workflow 的 `/webhook/inquiry` 路徑衝突，另外匯入一份 webhook path 加 `-localtest` 後綴、且兩個 Gemini 節點 URL 暫時指向本機 mock 的測試專用副本（`groundtruth-inquiry-flow-phase3-localtest`，僅用於本機驗證，驗證完畢即刪除，未寫入交付物）
3. `curl -X POST http://localhost:5678/webhook/inquiry/resume-localtest -d '{"review_id":77,"raw_input_text":"跟優品科採購A產品","user_id":5,"supplier_id":1}'`

**踩坑與排查**：
1. 第一次執行卡在「整合查詢結果（續傳）」節點丟出 `查無產品：A產品`（品項名稱其實有正確解析出來，但查詢卻查不到）。查 n8n log 定位到問題在上一個節點「查詢產品（續傳）」：這個節點的 URL 表達式寫 `{{$json.item}}`，原意是取「解析 LLM 輸出（續傳）」節點的輸出，但續傳流程的節點串接順序改成「解析 LLM 輸出（續傳）→查詢供應商名稱（續傳）→查詢產品（續傳）」（供應商已知，改成先查供應商名稱、再查產品，序列式串接、不是平行分支），所以「查詢產品（續傳）」的直接上游其實是「查詢供應商名稱（續傳）」，`$json` 在這裡指的是供應商查詢結果（只有 `id`/`name` 欄位），沒有 `item` 欄位，`encodeURIComponent(undefined)` 變成字面字串 `"undefined"`，查詢自然落空。
2. **根因**：n8n 表達式裡的 `$json` 永遠是「直接上游節點」的輸出，不是「邏輯上想要的來源節點」的輸出；序列式串接（而非平行分支）時特別容易犯這個錯，因為中間插入的節點會悄悄改變 `$json` 指向的內容。

**修復**：`build_workflow.py` 裡「查詢產品（續傳）」節點的 URL，把 `{{encodeURIComponent($json.item)}}` 改成明確具名參照 `{{encodeURIComponent($('解析 LLM 輸出（續傳）').first().json.item)}}`，不依賴隱含的 `$json`。

**驗證結果**：修正後整段續傳子流程（webhook 接收→金額遮罩→Gemini 解析品項→查供應商名稱→查產品→整合→Django 試算建立 Quote→Gemini 生成摘要→幻覺驗證→分流回覆）成功跑通，`幻覺驗證（續傳）` 分支正確依 mock 回應路由到「回覆：摘要待複核（續傳）」，回傳：
```json
{"detail":"報價摘要與真實資料不一致，已建立複核案件，待管理員確認","review_id":55,"reasons":["mock: number mismatch"]}
```
成功分支（`IF：幻覺驗證通過？（續傳）` 為 true）與主流程既有的同構 IF 節點模式一致，已在前一條目（4 種分支情境）驗證過同樣的路由邏輯，本次不重複用不同 mock 內容硬測，視為結構等價驗證。

**未驗證範圍**：同前，兩個 Gemini 呼叫尚未用真實 `GEMINI_API_KEY` 測試過；`http-lookup-supplier-resume`／`http-mask-amounts-resume` 這類新端點的正式 Django 端邏輯已有 100% 覆蓋率單元測試，但本次只驗證了 n8n 流程串接本身（節點連線、表達式參照是否正確），未涵蓋 Django 端與真實 PostgreSQL 的整合測試（已由既有 pytest 套件覆蓋，非本次 n8n 驗證範圍）。

## 2026-08-27 [標籤：使用者] FR-2b 第三種情境（格式無法解析）遺漏，補齊後本機驗證

**背景**：使用者直接追問「Phase 3 是不是都做完了」，重新逐條核對 SPEC.md 才發現 FR-2b 定義了三種遮罩失敗情境，但只做了前兩種（查無供應商、模糊比對）；第三種「供應商比對成功但其他欄位（如金額）格式無法解析→不進複核佇列，即時回覆使用者請求修正格式重新輸入」完全沒做。檢查主流程與續傳流程的「解析 LLM 輸出」Code node，發現 `JSON.parse(cleaned)` 沒有 try/catch，`quantity` 欄位也沒有做數字格式驗證，一旦 LLM 回傳格式壞掉或 `quantity` 不是合法數字，會直接 throw 一個未被攔截的 Error，n8n 只會當成一般執行失敗處理，不會產生 SPEC 要求的明確訊息，也不會跟複核佇列的情境區分開來。

**修復**：
1. 主流程與續傳流程的「解析 LLM 輸出」節點都改成：`JSON.parse` 包 try/catch，額外驗證 `parsed.item`／`quantity`（`Number.isFinite` 且 `> 0`，主流程另外驗證 `parsed.supplier`）是否有效；任一項失敗時不 throw，改回傳 `{ parse_error: true }`。
2. 兩個流程各自新增一個 IF 節點（`IF：解析格式正確？`／`IF：解析格式正確？（續傳）`），依 `parse_error` 分流：true 分支照原本流程繼續（Unmask 供應商／查詢供應商名稱），false 分支導向新增的回覆節點（`回覆：格式錯誤`／`回覆：格式錯誤（續傳）`），直接回應 `{"detail": "詢價內容格式無法解析，請確認數量/金額等欄位後重新輸入"}`，不寫入 `manual_review_queue`。
3. `build_workflow.py` 重新產生後節點數 33→37。

**驗證方式**：mock server 的 `generateContent` 路由新增一個依 prompt 是否含「格式錯誤測試」這個標記字串分流的分支，回傳 `quantity` 為中文字串（`"二十個"`）而非數字，模擬 LLM 解析出不合法格式的情況。用同一顆本機測試專用副本（`groundtruth-inquiry-flow-phase3-localtest`）分別打：
- 主流程 `POST /webhook/inquiry-localtest`，`raw_text` 含「格式錯誤測試」標記
- 續傳流程 `POST /webhook/inquiry/resume-localtest`，`raw_input_text` 含同一標記

兩者皆正確回傳：
```json
{"detail":"詢價內容格式無法解析，請確認數量/金額等欄位後重新輸入"}
```
另外重新跑過既有 5 種情境（主流程：成功／查無供應商／模糊比對／幻覺驗證失敗；續傳流程：成功路徑至幻覺驗證分流）確認補丁沒有影響既有行為。驗證完成後照慣例把本機測試專用副本 unpublish 並清掉殘留的 sqlite `workflow_entity`／`webhook_entity` row，交付物 `n8n/workflows/inquiry-flow.json` 兩個 Gemini 節點仍指向真實 endpoint。

**未驗證範圍**：同前，兩個 Gemini 呼叫尚未用真實 `GEMINI_API_KEY` 測試過——這次用中文數字字串模擬「LLM 回傳格式異常」的情況是否貼近真實 Gemini API 的實際失敗模式（例如 Gemini 更常見的異常可能是回傳結構完全不是預期 JSON、而非欄位值型別錯誤）也還沒有真實數據佐證，待使用者實測時留意。

## 2026-08-27 [標籤：使用者] 真實 GEMINI_API_KEY 實測：發現「Mask 遮罩」節點未轉傳 user_id，續傳流程試算報價失敗

**現象**：使用者在自己機器上用真實 Gemini API、真實 Docker n8n、真實 Django + seed 資料完整跑一輪 5 種分支：正常成功／查無供應商／模糊比對／格式無法解析皆通過（含真實 Gemini 回應格式驗證：摘要文字正確輸出阿拉伯數字，未觸發過往擔心的中文數字問題）。接續測續傳流程：`claim` → `decide` 核准，回應正確帶 `"resume_triggered": true`，但 Django log 隨即出現：
```
[27/Aug/2026 16:21:28] "POST /api/v1/quotes/calculate/ HTTP/1.1" 400 30
```
回應內容 `{"detail": "user_id 為必填"}`，且核准回應本身的 `manual_review_queue.requester` 欄位是 `null`。

**根因**：主流程「Mask 遮罩」節點呼叫 `POST /masking/mask/` 的 `jsonBody` 只帶了 `raw_text`，沒有把 webhook 收到的 `user_id` 一併轉傳：
```js
JSON.stringify({ raw_text: $json.body.raw_text })
```
`inquiries/trigger/` 端點與 `inquiry_service.trigger_inquiry()` 早就有把 `user_id` 放進送給 n8n 的 webhook payload（Phase 3 開發時就確認過），但 n8n workflow 這邊的「Mask 遮罩」節點沒有把它繼續往下傳，導致 `masking_service.mask_text()` 拿到的 `requester_id` 永遠是 `None`，`manual_review_queue.requester` 因此永遠是 `null`。核准供應商模糊比對案件、觸發 `trigger_resume()` 時，`requester_id` 這個 `None` 值就一路帶到續傳 webhook payload 的 `user_id`，最終傳進 `quotes/calculate/`，撞上該端點對 `user_id` 的必填驗證（Phase 3 開發時特意把這個驗證放在 API 層，見 `services/inquiry_service.py` 的設計筆記）。

這個 bug 之所以在先前用 mock 驗證時沒被抓到，是因為 mock server 的 `masking/mask/` 端點本來就不檢查／不使用 `user_id`，只看 `raw_text` 內容決定回應，所以就算 n8n 沒轉傳 `user_id`，mock 端也不會反映出問題；只有接到真實 Django（會實際把 `requester_id` 寫進 DB、並在續傳流程真正用到它）才會暴露這個斷點。這點值得記錄：**mock 驗證能確認流程「連線」是否正確，但無法取代對「資料實際有沒有正確流動」的驗證**，尤其是像 `user_id` 這種在 mock 端被忽略、但在真實後端會被使用的欄位。

**修復**：`build_workflow.py` 的「Mask 遮罩」節點 `jsonBody` 改為：
```js
JSON.stringify({ raw_text: $json.body.raw_text, user_id: $json.body.user_id })
```
重新產生 workflow，節點數不變（37），只改動這一個節點的參數。

**驗證**：檢查續傳流程「整合查詢結果（續傳）」節點讀取 `webhookBody.user_id` 那段邏輯本身沒有問題（正確讀取 `$('Webhook 續傳詢價').first().json.body.user_id`），確認問題只出在「Mask 遮罩」節點沒有把 `user_id` 往下傳這一步；本機用 mock 重新跑一次模糊比對＋續傳流程（帶入非空 `user_id`），確認整段串接能正常跑到幻覺驗證階段（不再卡在 `quotes/calculate/` 的必填驗證），細節同前一條目。修復後的 workflow 已推送給使用者，待使用者用真實環境重新跑一次模糊比對→核准→續傳的完整流程確認。

**未驗證範圍**：修復後尚未在使用者的真實環境（真實 Django + 真實 n8n + 真實 Gemini）重新跑過一次完整的模糊比對→核准→續傳流程，只在本機用 mock 確認資料能正確流動；使用者下次測試時應重新製造一個模糊比對案件（因為 `review_id=1` 已經因這次的失敗嘗試被消耗掉，狀態已是 `resolved`）並完整跑一次，確認 `manual_review_queue.requester` 不再是 `null`、`quotes/calculate/` 不再回 400。

**後續補充（同日）**：使用者用真實環境重新測過一次，確認修復生效：
1. 匯入修好的 workflow 後，`docker compose exec n8n n8n import:workflow` 匯入完不會自動生效，要 `docker compose restart n8n` 容器才會套用（跟 CLI 訊息提示的一樣，這裡再次驗證這條踩坑對 Docker Compose 部署方式也成立，不只是本機 CLI 直接跑 `n8n start` 的情況）；重啟後還發現 workflow 的 Active 開關狀態沒有保留，需要在網頁介面手動重新開啟才會重新註冊 webhook。
2. 重新製造模糊比對案件（新的 `review_id`），查詢該筆紀錄確認 `requester` 已正確帶入使用者 id（不再是 `null`）。
3. claim → decide 核准，`resume_triggered: true`，Django 未再出現 `quotes/calculate/` 的 400。
4. n8n Executions 頁面確認續傳子流程完整跑完（`Succeeded in 12.77s`），且這次真實 Gemini 生成的摘要通過了幻覺驗證，走的是「回覆：成功（續傳）」分支——這也是續傳流程「正常成功」情境第一次用真實 Gemini（而非 mock）驗證過。

Bug 確認修復完畢。
