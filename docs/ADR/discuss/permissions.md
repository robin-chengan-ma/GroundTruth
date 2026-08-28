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
3. ~~JWT payload 只放使用者 ID 與角色，不放簽核金額上限等易變資料；金額上限即時查資料庫。~~ **【superseded，2026-08-28】** JWT 改為只放使用者 ID，角色、權限與簽核政策每次請求即時查詢，見下方「多角色 RBAC 與職責分離」。
4. Gmail 認證交由 n8n 內建 OAuth 節點處理，不在本專案規格範圍內。

**理由**：JWT 對 SPA+DRF 是業界主流、不需重造輪子；n8n 屬內部服務對服務呼叫，用固定 API Key 已足夠、避免過度工程；JWT payload 精簡可避免權限資料不同步的風險。

**後果**：
- 需要安裝 `djangorestframework-simplejwt`（或等效套件），並在技術棧表補上版本。
- `.env` 需新增一組內部 API Key（供 n8n 與 Django 之間互相驗證），依安全規範不得記錄實際值於文件中，只記變數名稱與用途於 `docs/reference/`。
- Django 需實作驗證 `X-Internal-Token` 的權限檢查類別，套用在所有 n8n 呼叫的 API 端點與 webhook 接收端點上。

## 2026-08-27 [標籤：AI 提案／使用者確認] Phase 4 登入、Token 保存與資料可視範圍

**狀態**：accepted

**背景**：Phase 1～3 為開發驗證暫時開放一般 CRUD API，且前端尚未建立；Phase 4 必須把登入、Token 保存、角色權限與資料歸屬規則落地，否則只隱藏前端按鈕仍無法阻止越權 API 呼叫。

**討論內容**：討論了測試版本控制、人工複核頁範圍、JWT 保存方式、採購清單可視範圍、一般員工權限、CRUD API 收斂與登入識別欄位。使用者確認測試原始碼納入 Git、測試產物排除，並要求 JWT 比照企業常見安全做法。

**決策**：
1. 登入使用 Email＋Password；錯誤訊息統一為「帳號或密碼錯誤」，不得透露 Email 是否存在。
2. ~~JWT payload 僅包含 `user_id` 與角色代碼；簽核額度每次請求即時查 DB。~~ **【superseded，2026-08-28】** JWT 改為只放 `user_id`，見下方「多角色 RBAC 與職責分離」。
3. access token 採短效期（15 分鐘）且只保存在前端記憶體；refresh token 有效期 1 天，保存於 HttpOnly、SameSite Cookie，正式 HTTPS 環境加 `Secure`，並採 refresh token rotation、舊 token 撤銷與登出撤銷。
4. 一般員工可查看自己的採購單；簽核角色只能操作路由至自己角色且符合認領規則的案件；管理員可查看全部，但不得跨角色代簽。管理員人工複核權限維持不變。
5. n8n 內部端點繼續使用固定 API Key；前端使用者端點改由 JWT 驗證。Quote、Approval 等狀態不得透過通用 CRUD 任意改寫，只能經正式 service action。
6. Phase 4 包含管理員人工複核頁；測試原始碼提交 GitHub，coverage、cache、build 等測試產物不提交。

**理由**：Token 與角色權限必須由後端驗證，不能信任前端傳入的 `user_id` 或只靠畫面隱藏；HttpOnly refresh cookie 可降低 XSS 直接竊取長效 token 的風險，rotation 與撤銷則限制 token 重放。

**後果**：
- 後端需新增登入、refresh、logout、目前使用者端點，以及自訂業務 User 的 JWT authentication。
- Refresh token 撤銷可能需要 SimpleJWT blacklist 資料表；Migration 必須另行提出影響與 rollback，經使用者核准後才執行。
- 前端需以 Pinia 保存短效 access token，頁面重新載入時透過 HttpOnly refresh cookie 恢復登入狀態。

## 2026-08-28 [標籤：使用者／AI 提案] 多角色 RBAC 與職責分離

**狀態**：accepted

**背景**：企業採購流程新增需求、RFQ、選商、簽核、收貨、驗收、主檔與庫存操作後，每位使用者可能同時
具備多項職責；既有單一 `users.role_id` 與角色名稱判斷無法穩定擴充，也容易讓系統管理員被誤認為可執行
所有業務決議。

**討論內容**：比較繼續增加細分角色與改採 role-permission RBAC。細分角色會隨功能組合膨脹，仍無法清楚
表達同一人同時具備採購與驗收能力；RBAC 可用穩定的 permission code 控制操作，簽核額度則獨立為業務政策。

**決策**：
1. 使用 `roles`、`permissions`、`user_roles`、`role_permissions` 多對多模型，不在 API／View 硬寫角色名稱。
2. JWT payload 只保存使用者 ID；有效角色、權限及簽核政策每次請求即時查 DB。
3. 簽核額度與目標角色由 `approval_policies` 管理，與系統管理權限分離；簽核路由以得標後實際總成本為準。
4. 申請人不得核准自己的案件；系統管理員不自動取得選商、簽核、驗收、庫存調整或人工複核等業務權限。
5. 認領與決議仍由後端 transaction／row lock 防止競態；前端隱藏按鈕不作為授權依據。

**理由**：權限能力與簽核政策分離後，新增角色或功能只需新增資料與 permission mapping，不需修改核心授權
架構；同時能明確展示企業內控的職責分離。

**後果**：Phase 4.1 需可逆遷移既有 `users.role_id`、角色額度與 JWT 角色 claim；既有角色資料先轉成
`user_roles`／`role_permissions`，舊欄位在切換驗證完成前保留，不執行 DROP。
