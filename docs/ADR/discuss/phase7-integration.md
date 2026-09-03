---
updated: 2026-09-03
---

# Phase 7 整合、發布與 Demo 收尾

## 2026-09-02 [標籤：使用者／AI] Phase 7 範圍確認與啟動

**狀態**：accepted

**背景**：`docs/ADR/discuss/phase5.md` 2026-09-01「剩餘 Roadmap 收斂為三個正式階段」條目
定義 Phase 7 為「完成 n8n 新核心正式流程、Gmail 通知、根目錄 Docker Compose 全服務一鍵
啟動、可重建 Demo 種子資料、跨 Backend／Frontend／n8n／PostgreSQL／瀏覽器 E2E 與邊界
情境、文件及 Demo 指南、安全與 Git 內容稽核」。實際盤點現況發現的缺口比預期更大：
`n8n/workflows/inquiry-flow.json` 全部呼叫已於 Phase 5.0-B3A 退場（回 `410 Gone`）的
legacy `/quotes/calculate/`、`/quotes/verify-hallucination/` 端點，整支 workflow（含
「Webhook 接收詢價」與「Webhook 續傳詢價」兩條分支）已無任何正式程式碼呼叫；現行
`services/inquiry_service.py` 實際呼叫的候選解析 webhook（`N8N_INQUIRY_PARSE_WEBHOOK_URL`，
路徑 `webhook/purchase-request-candidate`）從未匯出進版控。Gmail 通知（FR-6b／FR-8）在
`masking_service.py`／`manual_review_service.py` 中留著「通知留待 n8n 串接」的註解，完全
未實作。

**討論內容**：Robin 確認依盤點結果一次做完全部範圍，不分批確認、盡量減少中途提問；
Claude 依 AGENTS.md「中大型實作前必須等使用者確認」規則，仍先提出完整實作計畫（涵蓋
下方 4 項決策與已知限制）取得一次性核准後才開工，符合「一次做完」與「重大實作需確認」
兩條規則。

**決策**：
1. **n8n workflow 拆檔**：不修改／刪除 `inquiry-flow.json`，改為加註 sticky note 標記
   「已停用僅供歷史參考」（ADR 保留歷史決策的既有原則，不刪除舊決策）；新增
   `purchase-request-candidate-flow.json` 作為現行正式流程，依
   `services/inquiry_service.py`／`services/masking_service.py`／`repositories/inquiry.py`
   目前的呼叫 contract 重建（Django 已在呼叫前完成遮罩，n8n 端只做「純解析」：接收
   `{raw_text, user_id}`、呼叫 Gemini 解析成 `{purpose, needed_by, currency,
   assistant_message, suppliers[], items[]}`、原樣回傳，不做供應商／品項查詢或試算）。
2. **Gmail 通知架構**：依「業務邏輯在 Django、n8n 只做串接」既有分工原則，收件人清單
   （依權限碼／角色查詢目前生效的 `user_roles`）與信件內容組裝都在新增的
   `backend/services/notification_service.py` 完成；n8n 新增 `notification-flow.json`
   只接收 `{subject, body, recipients, link}` 呼叫 Gmail 節點寄出。通知呼叫一律為
   best-effort（比照既有 `inquiry_resume_service.trigger_resume` 原則），失敗不拋例外、
   不影響已提交的複核決議或簽核決議；呼叫時機刻意放在對應 `transaction.atomic()`
   交易「提交之後」才觸發（`masking_service.py` 兩處建立 `ManualReviewQueue` 之後、
   `api/procurement/views.py` 的 `submit()`／`decide()` action 於 service 呼叫成功
   返回之後），避免把耗時外部 HTTP 呼叫包進資料庫交易。Gmail 節點的 Google 帳號
   OAuth 授權無法由程式自動完成，匯入 workflow 後需要 Robin 在 n8n 畫面手動完成一次。
3. **Docker Compose 服務拓樸**：新增 `backend/Dockerfile`（沿用 `manage.py runserver`
   為進入點，與 `docs/reference/deploy.md` 現行記錄一致，不額外引入 gunicorn）、
   `frontend/Dockerfile`（Node 建置＋nginx 提供靜態檔案並反向代理 `/api` 給
   `backend` 服務）、根目錄 `docker-compose.yml`（postgres＋backend＋frontend＋n8n，
   容器間以 service 名稱互連，`N8N_*_WEBHOOK_URL` 從 `host.docker.internal` 改為
   `n8n:5678`）。**已知限制**：本沙箱環境對 Docker Hub／常見容器登錄檔（ghcr.io、
   gcr.io、public.ecr.aws 皆測試回 403 Forbidden）的網路存取被擋，Docker 本身可執行
   （daemon 可啟動）但無法 pull image，故只能以 `docker compose config` 驗證
   YAML／變數插值語法正確、以 review Dockerfile 邏輯與各自獨立驗證 `pnpm build`
   （成功產出 `dist/`）／`pytest`（430 全過）確認內容正確，**無法在此環境實際執行
   `docker compose up` 驗證完整啟動**；這一步需要 Robin 在自己機器上執行驗證。
4. **安全與 Git 內容稽核**：掃描全部已提交檔案（`git grep` 比對 Google/Slack/GitHub/
   AWS 常見金鑰格式、`password=`／`api_key=`／`secret=`／`token=` 字面值賦值樣式），
   未發現任何真實金鑰或憑證外洩；確認 `.gitignore` 涵蓋 `.env`（含新增的根目錄
   `.env`）、`node_modules/`、`dist/`；確認唯二追蹤的 `.env` 相關檔案為
   `backend/.env.example`、`n8n/.env.example`（僅欄位名稱，無真實值），符合
   `docs/reference/` 只能記錄環境變數名稱與假資料的規則。結論：**目前 Git 內容無
   安全疑慮**。

**理由**：n8n workflow 用「加註歷史＋新建正式檔案」而非直接改寫或刪除舊檔，維持 ADR
「不覆寫決策歷史」的既有紀律，同時讓正式流程與已停用流程在版控中清楚區分。Gmail
通知放在交易提交之後呼叫，維持既有「正式決議的正確性（DB transaction）」與「通知這種
外部系統可靠性」分開處理的一貫設計。Docker Compose topology 改用 service name 互連是
從「n8n 在 host 機器上跑、Django 在 host 機器上跑」（Phase 2 設計）演進到「四個服務都在
同一個 compose 網路內」的必然調整。

**後果**：Phase 7 完成門檻明文要求「全新環境可一鍵啟動並完整 Demo」，本次僅完成程式碼
與設定層級的實作與可自動化驗證的部分（單元／整合測試、`docker compose config` 語法
驗證、`pnpm build` 產物驗證）；**`docker compose up` 的實際一鍵啟動驗證、瀏覽器端 E2E、
Gmail 真實寄信驗證、n8n workflow 匯入後與真實 Gemini API 的端到端驗證，都需要 Robin
在自己機器上完成**，Phase 7 在完成這些之前不得標記為完成。詳見 `docs/specs/PROGRESS.md`
本次條目的「未驗證範圍」。

## 2026-09-02 [標籤：Codex／使用者／AI] Codex 複查回報 4 項缺口，其中「一鍵啟動」自動化範圍決策

**狀態**：accepted

**背景**：Robin 請 Codex 對本次 Phase 7 範圍做獨立複查，Codex 回報 4 項缺口：①FR-8
通知未附簽核頁面連結；②通知收件人查詢只檢查 `valid_until` 未檢查 `valid_from`，未生效
的未來角色會提前收到通知；③Robin 本機資料庫尚未套用 `audit/0004` migration（Phase 5
既有 migration，非本次新增，屬 Robin 本機操作）；④`docker compose up` 後仍需手動跑
`seed_demo_data`、手動匯入並啟用 n8n workflow，與 SPEC.md「全新環境可一鍵啟動並完整
Demo」的完成門檻有落差。Claude 逐項對照 SPEC.md 條文與程式碼獨立驗證（不採信原始報告
用詞），確認①②③屬實，④屬於需要 Robin 決定自動化範圍與風險取捨的架構決策，先呈現
現況分析並詢問 Robin 意願，不逕自實作。

**討論內容**：Robin 轉達 Codex 針對④的具體建議：採用「demo seed＋n8n workflow 皆自動
初始化」方案，並提出 4 項安全條件：(1) demo seed 須由 `LOAD_DEMO_DATA` 環境變數控制，
只有啟用時才執行；(2) `seed_demo_data` 須冪等（重複啟動不重複建立、不清空不覆蓋既有
資料），失敗須讓容器明確停止或顯示錯誤；(3) n8n workflow 初始化須用獨立初始化服務，
等待 n8n healthcheck 通過後執行，冪等匯入並自動啟用現行必要的 AI 解析流程，通知
workflow 可匯入但 OAuth 未完成前不強制啟用，legacy `inquiry-flow.json` 不得被碰到或
啟用；(4) 本沙箱無法實測不是不開發的理由，但須如實記錄「靜態檢查由 Claude Code 完成、
`docker compose up --build` 由 Robin 實測、實測前不得標記 Phase 7 正式完成」。Robin
核准採用此方案並轉達執行。

**決策**：
1. **demo seed 自動化**：新增 `backend/docker-entrypoint.sh` 取代原本內聯在
   `backend/Dockerfile` `CMD` 的 `migrate && runserver`，改為
   `migrate → （`LOAD_DEMO_DATA=true` 時）seed_demo_data → runserver` 三段式，任一步
   失敗因 `set -e` 讓容器以非 0 狀態結束。確認 `seed_demo_data.py` 現有實作已全部使用
   `get_or_create`（無 `.create()`／`.update_or_create()`／`.delete()`／`bulk_create`），
   本就冪等、不清空不覆蓋既有資料，符合安全條件 (1)(2)，不需修改該檔案本身。
   `docker-compose.yml` 的 backend 服務新增 `LOAD_DEMO_DATA=${LOAD_DEMO_DATA:-true}`
   （對外預設值），`backend/docker-entrypoint.sh` 本身預設 `false`（image 若被其他非
   本次 compose 情境重用，不會無端灌入假資料）。
2. **n8n workflow 自動初始化**：新增獨立服務 `n8n-init`（同一個 `n8nio/n8n:latest`
   image，不 restart），`depends_on: n8n: condition: service_healthy`；`n8n` 服務新增
   `/healthz/readiness` healthcheck（n8n 一般模式內建端點，不需額外環境變數，DB 連線
   與 migration 完成才回 200）。`n8n-init` 與 `n8n` 主服務共用同一份
   `groundtruth_n8n_data` volume，執行 `n8n/scripts/init-workflows.sh`：依序
   `import:workflow` `purchase-request-candidate-flow.json`、`notification-flow.json`
   （兩檔皆已內建固定 `id` 欄位，依官方文件匯入時 id 相同即覆寫既有紀錄而非新增，
   冪等，符合安全條件 (3) 的「不產生多份副本」），再對候選解析流程呼叫
   `n8n update:workflow --id=... --active=true` 嘗試自動啟用；通知流程刻意不呼叫
   啟用指令，維持匯入後預設未啟用（`import:workflow` 預設 `--activeState=false`）；
   legacy `inquiry-flow.json` 不在匯入清單內。**已知風險**：`update:workflow` 官方
   文件標記為 n8n 2.0 起 deprecated（未來會被 `publish:workflow` 取代），且社群回報
   不同版本對匯入／啟用旗標的實際行為不完全一致；script 對啟用步驟失敗只印警告、
   不中止整體初始化（匯入本身失敗才會因 `set -e` 讓容器失敗），並在 log 中明確提示
   Robin 到 n8n 畫面手動確認。
3. **文件同步**：`docs/demo-guide.md` 步驟 3／4 從「手動執行 seed 指令」「手動匯入並
   啟用 workflow」改寫為「自動完成，僅需確認結果、Gmail OAuth 仍手動」；
   `docs/reference/deploy.md` Docker Compose 區塊新增「一鍵啟動涵蓋範圍」列與
   `LOAD_DEMO_DATA` 環境變數說明，「已知限制」更新為五服務未實測、自動匯入／啟用
   邏輯未經真實 n8n 跑過驗證；`docs/specs/PROGRESS.md` 新增對應條目。SPEC.md 第 127
   行 Phase 7 完成門檻文字本就是「全新環境可一鍵啟動並完整 Demo」的目標敘述，不是
   對舊實作方式的描述，核對後不需修改。

**理由**：demo seed 冪等性直接沿用既有 `seed_demo_data.py` 的 `get_or_create` 設計，
不需重寫；n8n 初始化採「獨立服務＋固定 id 覆寫匯入」而非在 workflow JSON 內臨時產生
id 或用第三方 API key 方案，是因為 CLI 匯入依 id 覆寫的行為有官方文件明確记載，而
n8n Public API 需要先建立 API Key、又需要先完成 owner 帳號設定，非互動情境下的可靠性
在查證過程中發現社群有多篇「無法用環境變數建立 API Key」的疑難討論，相對更不可靠；
啟用步驟失敗時選擇「警告不中止」而非「失敗即中止整個初始化」，是因為工作流程存在但
未啟用，是比「workflow 完全沒被匯入」小很多、也更容易由 Robin 手動修復的落差。

**後果**：與上一則條目相同的「Phase 7 完成門檻」限制持續有效，本次新增的自動化同樣
**完全未經真實環境驗證**（本沙箱無法拉取 `n8nio/n8n` image），Robin 執行
`docker compose up --build` 時務必檢查 `n8n-init`／`backend` 容器 log 是否有警告或
錯誤，並在 n8n 畫面確認候選解析流程確實已啟用；若自動啟用失敗，屬已知風險內、按
log 提示手動啟用即可，不代表整體自動化失敗。Codex 複查的①②（FR-8 通知連結、
`valid_from` 判斷）已直接修正，③（本機 migration 未套用）為 Robin 自行操作事項，
本次不處理。


## 2026-09-03 [標籤：使用者／AI] 人工複核駁回原因、通知與「我的採購需求」呈現方式決策

**狀態**：accepted

**背景**：Robin 實測「供應商模糊比對」（FR-2b）情境時發現兩個問題：(1) 核准後若品項
名稱過於泛稱、對不到主檔正式品名（例如輸入「筆電」，主檔正式品名是「B產品-筆記型
電腦」），自動續傳解析會一直失敗，「重試續傳」形同無限迴圈死路，跟「缺數量／只寫
供應商」這種真的無法自動判斷、可以直接駁回的情況不一樣；(2) 案件遭駁回時，系統完全
不會通知申請人——`manual_review_service._decide_supplier_fuzzy_match()` 駁回分支的
註解寫著「通知申請人重新送出由 n8n／Gmail 串接負責」，但比對 `notification_service.py`
發現這支通知從未被實作，`decide_review()` 駁回分支也沒有呼叫任何通知邏輯。

**決策**：
1. 品項比對死循環（問題一）：暫緩處理，留待後續評估「把人工選品項的既有 UI 機制
   （`InquiryView.vue` 現成的『待選擇品項』流程）下放給申請人」這個方向的實作時程，
   本次先聚焦問題二／三。
2. `ManualReviewQueue` 新增 `rejection_reason` 欄位（migration 0005），
   `decide_review()` 駁回時強制要求填寫非空字串（比照 `approval_case_service.
   decide_step()` 既有作法），空字串直接拋 `ManualReviewError`。
3. 新增 `notification_service.notify_manual_review_rejected()`：supplier_fuzzy_match
   案件通知 `review.requester`，hallucination_mismatch 案件通知 `review.quote.user`；
   決議交易提交後才呼叫，best-effort 不阻斷已落地的決議，跟既有
   `notify_manual_review_created` 同一套設計原則。
4. 「我的採購需求」頁面要不要讓申請人看到這類駁回——這裡有架構衝突：
   supplier_fuzzy_match 駁回發生在**尚未建立任何 PurchaseRequest** 的階段（這正是
   FR-2b 驗收標準「不先建立 Purchase Request」要求維持的行為），但「我的採購需求」
   頁面查的就是 PurchaseRequest 表，兩者天生對不起來。提出三個選項給 Robin 選：
   A. 破例建立一筆空白 PurchaseRequest 只為了讓它出現在清單裡（違反既有驗收標準）；
   B. 清單額外整合查詢沒有 PurchaseRequest 的駁回案件，用獨立區塊呈現；
   C. 只靠 Email 通知解決「不知道」的核心痛點，畫面不強求呈現。
   Robin 選 **B**：新增 `GET /manual-review-queue/mine/` 端點（權限重用既有
   `purchase_request.read_own`，不新增權限碼），前端在「我的採購需求」頁面用獨立
   區塊「詢價已駁回（尚未建立採購需求）」呈現，不跟正式的 PurchaseRequest 表格混成
   同一張表、不共用同一個 status 欄位語意。
5. 順便補上簽核階段（`ApprovalStep.decision_reason`，這欄位在 `approval_case_service.
   decide_step()` 核准／駁回時本來就是必填且已經有資料，只是從未被序列化到任何 API
   回應過）的駁回理由，一併顯示在「我的採購需求」表格新增的「備註」欄——這跟
   supplier_fuzzy_match 駁回是兩種不同階段、不同資料來源、不同呈現位置的東西，UI 上
   刻意分開放，不要讓使用者誤以為是同一種「駁回」。

**理由**：選 B 是因為要同時滿足 Robin「讓申請人清楚知道審核流程」的需求，又不能
破壞已經驗收過的「不先建立 Purchase Request」行為；用獨立區塊呈現（而非混進同一張
表／同一個 status 欄位）是因為 supplier_fuzzy_match 駁回與簽核階段駁回是兩種資料模型
截然不同的「駁回」，混在一起顯示容易讓使用者誤讀為同一件事。

**影響範圍**：`backend/apps/audit/models.py`（新欄位＋`migrations/0005_
manualreviewqueue_rejection_reason.py`）、`backend/services/manual_review_service.py`、
`backend/services/notification_service.py`、`backend/api/audit/views.py`（新增
`mine` action）、`backend/schemas/audit.py`、`backend/schemas/procurement.py`
（`PurchaseRequestListSerializer`／`PurchaseRequestDetailSerializer` 新增
`rejection_reason` 欄位）、`frontend/src/views/ManualReviewView.vue`（駁回原因彈窗、
合併狀態篩選下拉、已駁回紅字卡片）、`frontend/src/views/PurchaseRequestListView.vue`
（狀態篩選下拉、備註欄、「詢價已駁回」區塊）、`frontend/src/types/api.ts`。程式碼已
完成並通過 `vue-tsc --noEmit` 與 Python 語法檢查，**尚未經 Robin 實測**，見
`docs/specs/PROGRESS.md` 對應條目。


## 2026-09-03 [標籤：使用者／AI] 已駁回案件「複製並重新編輯」，避免整份重打並保留稽核軌跡

**狀態**：accepted

**背景**：接續上一則條目（人工複核駁回通知與呈現），Robin 追問「已駁回的案件，申請人
可以重新編輯這則案件並重新送出嗎？還是只能重建一筆新案件？一般企業會怎麼做？」。查證
發現現行系統兩種駁回（人工複核駁回、簽核階段駁回）都是終態，完全沒有「編輯同一筆再
送出」的機制，程式碼裡沒有任何 `resubmit`／`revise`／`reopen` 邏輯，申請人只能整份
重新輸入。討論三種常見企業做法（終態＋建新單／退回同一張單重編／保留駁回紀錄不可變＋
複製捷徑），因為本系統既有的 RFQ／SupplierQuote 都是版本化快照、不可覆寫單據的設計
精神，選擇第三種。

**決策**：
1. `PurchaseRequest` 新增兩個來源追蹤欄位：`copied_from_review`（FK 到
   `audit.ManualReviewQueue`，字串參照避免循環 import）、`copied_from_request`
   （self FK）。兩者互斥，皆 nullable，migration `0012_purchaserequest_copy_
   tracking.py`。
2. 「只能複製一次」用**已存在的結果**判斷，不是鎖按鈕本身：`create_draft()` 新增
   `_resolve_copied_from_review`／`_resolve_copied_from_request`，分別檢查
   來源必須屬於呼叫者本人、必須已是駁回狀態、且 `copies.exists()` 必須為否，否則
   拋 `DraftError`；只有實際呼叫 `create_draft()` 成功建立新需求的那一刻，來源才會
   被標記為「已複製」。單純點按鈕、把內容帶入畫面、甚至中途放棄都不會鎖住，維持
   「打開看看又反悔」的彈性——跟 FR-6a 決議「先落地 pending、外部呼叫在交易外」
   的既有設計原則一致：狀態鎖定只在真正確定發生的那一刻寫入。
3. 兩種來源分開處理，因為底層資料本來就不同：
   - 人工複核駁回：沒有 PurchaseRequest 可以複製，純粹是把 `raw_input_text` 帶回
     詢價頁（`/inquiry?copied_from_review=<id>&text=<原文>`）讓申請人重新編輯、
     重新走一次正常的 AI 解析流程，`copied_from_review_id` 跟著最終的
     `saveAndEstimate()` 一起送出。
   - 簽核階段駁回：PurchaseRequest 跟明細都已存在，讀取來源需求的
     `GET /purchase-requests/{id}/`，在前端直接組出跟 AI 解析結果同樣形狀的
     `candidate` 物件（`candidate_token` 給空字串，略過 AI 解析），套用畫面上
     既有的手動編輯 UI，一樣要等 `saveAndEstimate()` 才真正建立新需求。
4. **原本規劃是後端提供一支 `POST /purchase-requests/{id}/copy/` 立即建立新草稿**，
   實作中途發現這個系統目前**完全沒有「重新開啟既有草稿繼續編輯」的畫面**——
   `InquiryView.vue` 的 `draft` 狀態只存在單一瀏覽器工作階段的記憶體裡，沒有任何頁面
   會對已存在的草稿呼叫 `GET`，即使是使用者自己半途放棄的一般草稿也一樣無法回頭
   編輯。若照原規劃立即建立草稿，會生出一筆「建立了但誰也打不開」的孤兒記錄，比
   駁回前更糟。改為前端先用畫面既有的編輯 UI 走過一輪，`create_draft()` 才是真正
   落地的時機，避免了這個孤兒記錄問題，也完全不需要新的「草稿列表／恢復編輯」頁面。
5. 前端呈現：`PurchaseRequestDetailView.vue`（已駁回時顯示「複製為新草稿」連結，
   已複製則顯示「已複製為 PR-00456」）；`PurchaseRequestListView.vue` 的「詢價已
   駁回」區塊比照辦理，多一欄「複製並重新編輯」／「已複製為 PR-00456」；兩邊都會
   顯示「此需求複製自已駁回的 XXX」讓主管可以快速核對這是修正重送、不是全新案子
   （Robin 提出的「快速通關」需求）。

**理由**：選「保留駁回紀錄不可變＋複製捷徑」而非「同一張單打回草稿重編」，是因為後者
會覆寫一筆已經定案的單據，跟本系統既有的版本化快照、不可覆寫單據的設計精神衝突；
「只能複製一次」鎖在建立結果而非按鈕點擊，是為了不要因為使用者猶豫、中途放棄而被
不合理地鎖死。

**影響範圍**：`backend/apps/procurement/models.py`（新欄位＋migration 0012）、
`backend/services/purchase_request_draft_service.py`（`create_draft()` 擴充、新增
兩個 `_resolve_copied_from_*` helper）、`backend/schemas/procurement.py`
（`PurchaseRequestDetailSerializer` 新增 `copied_from_request_no`／
`copied_from_review_id`／`copied_to_request_no`）、`backend/schemas/audit.py`
（`ManualReviewQueueSerializer` 新增 `copied_to_request_no`）、
`frontend/src/views/InquiryView.vue`（新增 `copied_from_request`／
`copied_from_review` 兩種 query string 帶入模式）、
`frontend/src/views/PurchaseRequestDetailView.vue`、
`frontend/src/views/PurchaseRequestListView.vue`、`frontend/src/types/api.ts`。
程式碼已完成，通過 `vue-tsc --noEmit` 與 Python 語法檢查；**尚未經 Robin 實測**，
併入 `docs/specs/PROGRESS.md` 同日條目的待驗範圍。


## 「詢價已駁回」獨立成頁

**狀態**：accepted
**日期**：2026-09-03

**背景**：接續上一則條目（已駁回案件「複製並重新編輯」）。Robin 實測該功能過程中反覆
測試，「詢價已駁回（尚未建立採購需求）」區塊（塞在「我的採購需求」頁最上方）短時間內就
累積了 3 筆 `PR-DRAFT-...` 草稿，Robin 提出：這個區塊會隨案件增加持續往上堆，是否該在
「工作台」選單新增子選單「詢價已駁回清單」獨立成頁，駁回時間一樣新到舊排序、不需要狀態
下拉（單一用途清單本身就是篩選結果）、保留原有功能（原始輸入內容／駁回原因／駁回時間／
「複製並重新編輯」），讓「我的採購需求」頁也回歸單純。

**決策**：
1. 同意獨立成頁。這個區塊當初的設計定位是「小提醒」，塞進另一個頁面的最上方；現在角色
   已經變成會持續成長的正式清單，跟系統裡其他一級資源（RFQ、供應商報價、稽核紀錄等）一樣，
   都應該有自己的路由與選單項目，不該繼續當附屬區塊。
2. 新增路由 `/rejected-inquiries`＋新增 Vue 元件 `RejectedInquiryListView.vue`，沿用原區塊
   的表格與按鈕邏輯（不重新設計互動），拿掉狀態下拉。
3. 選單項目「詢價已駁回清單」新增於既有的「工作台」群組（`navigation.ts`），排在「我的
   採購需求」之後；權限比照「我的採購需求」用 `purchase_request.read_own`（同樣是申請人
   查詢自己的資料，不需要人工複核權限）。
4. 順帶修正兩個原本不影響小提醒區塊、但會直接影響獨立清單頁可用性的既有缺口（不在
   Robin 原始需求裡，屬於「做這個功能勢必要一併處理」的範圍，非擴大需求）：
   - `GET /manual-review-queue/mine/` 排序原本沿用 `ManualReviewQueueRepository.all()`
     的預設 `.order_by("id")`（舊到新，是給管理員複核佇列 FIFO 處理設計的排序，不適合
     這支「查自己」端點），改在 `mine` action 內對過濾後的 queryset 額外
     `.order_by("-updated_at")`（駁回/決議當下即為最新更新時間），不影響
     `ManualReviewQueueRepository.all()` 本身的預設排序、不影響管理員複核佇列頁。
   - 原本直接 `Response(serializer.data)` 回傳裸陣列，沒有分頁；一個「本質上會持續變多」
     的清單頁没有分頁上限並不合理，改套用既有的共用 `paginate_response()`（`backend/lib/
     pagination.py`），回應信封與 `/purchase-requests/` 等其他清單端點一致
     （`{count,page,page_size,total_pages,results}`）。
5. `PurchaseRequestListView.vue` 移除該區塊與 `rejectedInquiries`／`loadRejectedInquiries`
   邏輯，回歸單純的採購需求清單＋分頁＋狀態篩選。

**理由**：這個變動的觸發點很直接——Robin 自己重複測試就已經產生出「越堆越多」的實際現象，
不是假設性的未來問題。順手修正排序與分頁，是因為兩者都是「小提醒區塊」時代不構成問題、但
一旦扶正為獨立清單頁就立刻不合理的既有缺口，跟這次的頁面獨立化是同一個變更範圍內必然要
處理的部分，不修就等於把「小提醒」的隱性限制原封不動地搬進一個號稱可以獨立瀏覽的正式清單頁。

**影響範圍**：`backend/api/audit/views.py`（`mine` action 改用 `paginate_response()`＋
`.order_by("-updated_at")`）、`frontend/src/views/RejectedInquiryListView.vue`（新增）、
`frontend/src/views/PurchaseRequestListView.vue`（移除區塊）、`frontend/src/navigation.ts`
（新增選單項目）、`frontend/src/router/index.ts`（新增路由）、`frontend/src/styles.css`
（移除隨區塊一起變成孤兒的 `.rejected-inquiries` 樣式）、`docs/reference/api.md`（新增
`GET /manual-review-queue/mine/` 章節，並補上前一項工作項目遺留的 `decide` 端點 `reason`
欄位文件缺口）。不需要新的 Migration（`ManualReviewQueue` 沒有新增欄位，只改查詢排序與
序列化包裝方式）。程式碼已完成，通過 `vue-tsc --noEmit` 與 Python 語法檢查；**尚未經
Robin 實測**，併入 `docs/specs/PROGRESS.md` 同日條目的待驗範圍。
