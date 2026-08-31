---
title: Phase 4 開發環境與安全收尾紀錄
updated: 2026-08-28
---

# Phase 4 開發環境與安全收尾紀錄

## 2026-08-28 測試基線與認證資料完整性

**現象**：專案沒有獨立且可重現的開發測試依賴，既有 Ruff baseline 無法作為乾淨門檻；Phase 4
初版管理員使用者 CRUD 會直接保存輸入密碼，Refresh Session 建立時間也不是資料庫 default。

**排查過程**：建立隔離測試設定後跑完整 Ruff、Migration dry-run 與 coverage；逐項檢查 User serializer、
JWT session model、登入／rotation／重放與簽核路由的未覆蓋分支。

**根因**：Phase 1 的通用 ModelSerializer 沿用明碼欄位寫入行為；新 Session model 初版沿用
`auto_now_add`；舊專案尚未固定 dev dependencies 與 lint 排除範圍。

**修復方式**：新增 `requirements-dev.txt`、`pyproject.toml`、`config/test_settings.py`；User serializer
在 create/update 統一呼叫 Django 密碼雜湊；`refresh_sessions.created_at` 改為 DB `now()` default；
補上錯誤憑證、Token rotation／重放、JWT 使用者失效、簽核門檻與角色限制測試。

**驗證方式**：執行 backend Ruff、Migration check、pytest coverage，以及 frontend lint、test、type-check、build。

**未驗證範圍**：未以同時啟動的 Django、n8n、PostgreSQL 執行瀏覽器真實環境 E2E。

## 2026-08-28 Phase 4 權限收斂造成 n8n 查詢 401

**現象**：使用者從 Vue 送出詢價後顯示「詢價送出失敗」；Django 記錄 n8n 查詢
`/api/v1/suppliers/` 回 401，接著因 n8n 回應為空而在 `response.json()` 發生未攔截例外，最終回 500。

**排查過程**：確認 n8n health 與 Webhook 均可連線，再比對 Phase 4 ViewSet authentication 與
workflow HTTP Request 節點；以失敗測試重現 suppliers/products 內部查詢 401 及非 JSON 回應 500。

**根因**：Phase 4 將 suppliers/products 從 `AllowAny` 改為只接受 JWT，但遺漏 n8n 仍需以內部
API Key 唯讀查詢；workflow 的四個主流程／續傳查詢節點也未帶 `X-Internal-Api-Key`。
`inquiry_service` 只攔截 HTTP／連線錯誤，未涵蓋成功狀態但內容非 JSON 的上游回應。

**修復方式**：suppliers/products 同時接受 JWT 與內部 API Key，permission 限制內部服務只能使用
GET／HEAD／OPTIONS；n8n 四個查詢節點補上 API Key header；非 JSON 上游回應統一轉為安全的
`InquiryTriggerError`，由 API 回 502，不再洩漏 stack trace。

**驗證方式**：新增內部 API Key 唯讀／拒絕寫入及非 JSON 回應測試；重新匯入並啟用本機 n8n
workflow，真實呼叫小額詢價 Webhook 回 HTTP 200 與 JSON 回應；再執行完整 backend regression。

**未驗證範圍**：無；Robin 已由 Vue 重新送出 9,000 TWD 小額詢價，成功取得 Quote #7 的 JSON
摘要、2.39% 歷史均價偏離值並完成簽核路由。

## 2026-08-28 舊 pending_approval Quote 未出現在簽核工作區

**現象**：Alice 的採購清單可見 Quote #4、#5、#6 均為 `pending_approval`，但 Carol 的簽核工作區
只看得到 #6。

**排查過程**：唯讀查詢 Quote #4～#6 與 Approval 關聯；#4、#5 沒有任何 Approval，#6 則有
`approver_10k`／small／pending 的有效路由。

**根因**：#4、#5 是簽核路由功能落地前或流程中斷時留下的既有測試資料；Quote 狀態已進
`pending_approval`，但 Phase 4 migration 沒有回填既有待簽核資料。簽核工作區以 Approval 為資料來源，
因此不會顯示沒有路由的 Quote。#4 的 30,000 TWD 即使回填也應路由 David，不是 Carol；#5 的
1,500 TWD 應路由 Carol。

**修復方式**：經 Robin 核准後新增 forward data migration，僅為「狀態為 `pending_approval` 且
不存在 Approval」的 Quote 依現行門檻補建路由，避免人工 shell 修資料且保留可重現性；reverse
採 no-op，避免回滾時誤刪後續已認領或已決議的簽核紀錄。

**驗證方式**：執行 migration 後驗證 #4 路由 `approver_100k`、#5 路由 `approver_10k`，並確認
已有 Approval 的 #6/#7 不重複建立；再執行完整 backend regression。

**未驗證範圍**：migration 與資料庫路由已驗證；待 Robin 由 Carol、David 頁面複驗顯示結果。

## 2026-08-28 LLM 將模糊數量「一些」猜成 1

**現象**：Robin 輸入「跟優品科技買一些 A產品-辦公椅」，系統未走 FR-2b 格式錯誤分支，反而
建立數量 1、總額 1,500 TWD 的 Quote #8。

**排查過程**：檢查 n8n 主流程與續傳的 LLM 解析 Code node；既有防呆只驗證 LLM 回傳值是正數，
沒有驗證數量是否由使用者原文明確提供。

**根因**：Gemini 將模糊量詞自行推測為 1，後續固定程式誤把合法正整數視為可信輸入。

**修復方式**：Django 在觸發 n8n 前要求原文含明確正整數數量，支援常用量詞、「數量：N」及
全形數字；模糊量詞回 400。n8n 主流程與續傳流程再比對 LLM quantity 必須存在於原文的明確
數量集合，避免直接呼叫 Webhook 繞過 Django。

**驗證方式**：新增模糊量詞、零、一般數字、「數量：N」與全形數字測試；Django API 對相同句子
回 400 且未新增 Quote；直接呼叫真實 n8n Webhook 亦回格式錯誤，未建立 Quote 或人工複核案件。

**未驗證範圍**：等待 Robin 從 Vue 以相同句子複驗；誤建 Quote #8 保留待 Robin 自行撤回。

## 2026-08-31 新採購需求送出後狀態與清單顯示不一致

**現象**：Robin 完成 n8n v2 真實環境串接並從 Vue 送出 Purchase Request 後，新增頁仍保留原輸入、候選資料與試算結果，成功訊息持續顯示；無有效價格的供應商總額顯示 `TWD 0`；「我的採購需求」仍列 legacy Quote，缺少建立時間且看不到剛送出的新 Purchase Request。

**排查過程**：比對 `InquiryView` 提交成功分支、試算卡片總額判斷、`QuoteListView` 的 API 來源，以及 `PurchaseRequest` 既有欄位與本人 RBAC。確認新單據已正確建立，問題集中在前端狀態未清除、無價格時仍格式化初始總額 0，以及清單仍呼叫 legacy `/quotes/`。

**根因**：提交成功原本只清除試算結果，未清除輸入、AI 候選與草稿識別；供應商彙總總額以 0 初始化，畫面沒有先判斷是否存在任何有效價格；Phase 4.1 新單據上線後，舊採購清單頁尚未從 legacy Quote 切換至 `purchase_requests`。

**修復方式**：提交成功後重置本輪全部表單狀態，改以約 5 秒自動消失、可手動關閉且含「查看申請」入口的 Toast 呈現申請編號；全部品項缺價時顯示「尚無報價」；新增本人 Purchase Request 唯讀清單 API，依 `created_at` 新到舊排序，前端顯示申請編號、用途、品項／候選供應商摘要、申請人、建立時間與狀態，不再與 legacy Quote 混用。

**驗證方式**：新增後端本人範圍／排序／建立時間 API 測試，以及前端送出重置、缺價與新清單呈現測試；目標 Backend 1 passed、Frontend 4 passed，完整 Backend 338 passed、Frontend 15 passed，type-check、ESLint、production build、Ruff、Django check 與 Migration check 均通過。Robin 已先完成 n8n production webhook 與 Vue 解析、人工主檔選擇、試算及提交的真實環境 E2E。

**未驗證範圍**：無；Robin 已於瀏覽器確認提交後重置、Toast 自動消失與查看入口、無價格提示，以及本人需求清單建立時間與最新排序皆正常。

### 中文明確數量補充

Robin 複驗時發現「五個」被第一版防呆誤判為格式錯誤。根因是固定驗證只涵蓋半形／全形阿拉伯
數字。現已在 Django 與 n8n 主／續傳流程加入中文整數轉換，支援零／〇、一至九、兩、十、百、千、
萬及常用採購量詞；「五個／十五件／兩百個」視為明確數量，「一些／幾個」仍拒絕。新增三個中文
數量測試並等待 Robin 由 Vue 建立案件複驗。
