---
updated: 2026-09-02
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
