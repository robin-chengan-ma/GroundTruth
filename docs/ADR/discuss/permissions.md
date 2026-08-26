# 權限管理（簡化版） 討論紀錄

> 同一功能的多次討論都寫在同一個檔案，依時間往下附加新段落，不要開新檔案。

## 2026-08-24 [標籤：使用者] 認證機制：使用者登入、系統對系統呼叫

**狀態**：accepted

**背景**：原始構想文件完全沒有規格認證機制，Vue 前端如何登入 Django API、n8n 呼叫 Django API 用什麼身分驗證、Django 觸發與接收 n8n webhook 怎麼驗證，開發前必須先定案。

**討論內容**：
- Vue ↔ Django：討論 JWT vs Session，決定用 JWT（`djangorestframework-simplejwt`），因為 Vue SPA + DRF 是主流組合，不需要自建機制。
- n8n ↔ Django：n8n 是內部流程協調服務、不是終端使用者，討論後決定不套用使用者登入那套 JWT 流程，改用固定 API Key（寫在 `.env`，n8n 呼叫時帶在自訂 header），比 OAuth Client Credentials 更簡單，複雜度符合 demo 系統範圍。
- Django → n8n（觸發 webhook）與 n8n → Django（回呼）：比照系統對系統呼叫，同樣用固定 API Key 驗證。
- Gmail 通知：n8n 內建 Gmail OAuth 節點處理，不屬於本專案自建的認證機制範圍。
- JWT payload 內容：討論要不要放「簽核金額上限」，決定不放，因為該欄位可能被管理員即時調整，放進 token 會有资料不同步風險（要等 token 過期重新登入才生效）；只放使用者 ID 與角色（變動頻率低），金額上限每次請求即時查資料庫。

**決策**：
1. Vue ↔ Django：JWT 認證（access token 短效期如 15 分鐘，refresh token 長效期如 1 天，用 refresh token 換發新 access token）。密碼儲存用 Django 內建雜湊機制（PBKDF2）。
2. n8n ↔ Django（含 Django 觸發 webhook、n8n 回呼）：固定 API Key，驗證自訂 header（如 `X-Internal-Token`），Django 端以 DRF 權限檢查類別驗證。
3. JWT payload 只放使用者 ID 與角色，不放簽核金額上限等易變資料；金額上限即時查資料庫。
4. Gmail 認證交由 n8n 內建 OAuth 節點處理，不在本專案規格範圍內。

**理由**：JWT 對 SPA+DRF 是業界主流、不需重造輪子；n8n 屬內部服務對服務呼叫，用固定 API Key 已足夠、避免過度工程；JWT payload 精簡可避免權限資料不同步的風險。

**後果**：
- 需要安裝 `djangorestframework-simplejwt`（或等效套件），並在技術棧表補上版本。
- `.env` 需新增一組內部 API Key（供 n8n 與 Django 之間互相驗證），依安全規範不得記錄實際值於文件中，只記變數名稱與用途於 `docs/reference/`。
- Django 需實作驗證 `X-Internal-Token` 的權限檢查類別，套用在所有 n8n 呼叫的 API 端點與 webhook 接收端點上。
