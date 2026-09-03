---
title: Demo 操作指南
updated: 2026-09-03
---

# Demo 操作指南

> 給第一次操作這個系統的人（含 Robin 自己或面試官）用的一鍵啟動與展示腳本。技術細節見
> `docs/reference/deploy.md`；產品規格與完整流程見 `docs/specs/SPEC.md`。

## 前置需求

- Docker、Docker Compose（`docker compose version` 確認可用）
- Gemini API Key（[Google AI Studio](https://aistudio.google.com/) 申請）
- 一組可用來授權 n8n Gmail 節點寄信的 Google 帳號（Gmail 通知用，非必要功能可先跳過）

## 一鍵啟動

1. 複製環境變數範本並填入真實值：

   ```bash
   cp .env.example .env
   # 編輯 .env：至少填 POSTGRES_PASSWORD、DJANGO_SECRET_KEY、INTERNAL_API_KEY、GEMINI_API_KEY
   # DJANGO_SECRET_KEY／INTERNAL_API_KEY 可用 openssl rand -hex 32 產生隨機字串
   ```

2. 於本檔案所在目錄（repo 根目錄）執行：

   ```bash
   docker compose up --build
   ```

   首次啟動會依序：建置 backend／frontend image → 啟動 postgres（等待 healthcheck 通過）
   → backend 自動執行 `migrate`，並在 `LOAD_DEMO_DATA=true`（`.env.example` 預設值）時
   自動灌入 demo 假資料（冪等，重複啟動不會重複建立或覆蓋既有資料，見
   `backend/docker-entrypoint.sh`）→ n8n 啟動並通過 healthcheck 後，獨立的
   `n8n-init` 服務自動匯入現行必要的「採購需求候選解析」與「Gmail 通知」workflow，
   並嘗試自動啟用前者（見 `n8n/scripts/init-workflows.sh`）→ backend／frontend／n8n
   啟動完成。**這段自動化本沙箱環境無法實測（見下方「已知限制」），第一次執行請留意
   `n8n-init`／`backend` 的 log 是否出現警告或錯誤。**

3. 確認 demo 假資料與 workflow 是否就緒（可選，不確定自動化是否成功時再做）：

   ```bash
   # demo 帳號密碼是否已建立
   docker compose exec backend python manage.py seed_demo_data
   # 已存在的資料會被 get_or_create 直接跳過，不會重複建立或出錯，可放心重跑
   ```

   瀏覽器開 <http://localhost:5678>，左側選單「Workflows」確認「GroundTruth - 採購需求
   候選解析（Phase 5 起正式流程）」已存在且 Active 開關為開啟；若沒有自動啟用（n8n-init
   log 會有警告），手動點一次 Active 開關即可。

4. 完成 Gmail 通知授權（選用，非必要功能可先跳過）：n8n 畫面開啟「GroundTruth - Gmail
   通知（FR-6b／FR-8）」（`n8n-init` 已自動匯入，但刻意不自動啟用），點「寄送 Gmail」
   節點、在 Credential 欄位選「Create New」完成一次 Google 帳號 OAuth 授權（Sign in
   with Google，這一步無法自動化），完成後回到 workflow 列表手動點右上角 Active
   開關啟用。

5. 開啟 <http://localhost:5173> 進入系統。

## 服務位址一覽

| 服務 | 位址 | 用途 |
| --- | --- | --- |
| 前端 | <http://localhost:5173> | 主要操作介面 |
| 後端 API | <http://localhost:8000/api/v1/> | 前端與 n8n 呼叫的 REST API |
| Django Admin | <http://localhost:8000/admin/> | 除錯用，非展示動線 |
| n8n | <http://localhost:5678> | 匯入 workflow、查看執行紀錄 |

## Demo 帳號

`seed_demo_data` 建立的帳號密碼見 `backend/apps/core/management/commands/seed_demo_data.py`
內的假資料定義；依角色分別對應「一般申請人」「各金額層級簽核人」「系統管理員」，
用來展示 FR-18 的職責分離（申請人不得核准自己的案件）。

## 展示腳本（對應 `docs/specs/SPEC.md` 系統主流程）

1. **一般申請人**登入 → 自然語言輸入採購需求 → 確認 AI 解析出的品項／供應商候選
   （展示 NFR-1 遮罩：可在 n8n「Executions」頁籤看到送給 Gemini 的文字已 Token 化）
   → 送出成正式 Purchase Request draft。
2. 以有 `rfq.manage` 權限的角色發出 RFQ、由多間供應商填入報價（demo 資料已預建部分
   報價，也可手動示範新增）。
3. 展示綜合評選（FR-15）：必要條件、實際總成本、品質、交期等固定公式評分，人工選商
   （系統只建議，不自動得標）。
4. 依得標金額觸發簽核路由（FR-7／FR-7a），以對應層級的簽核人角色登入認領並核准
   （展示 FR-9a 職責分離：申請人與非目標角色使用者看不到認領按鈕）。若設定了 Gmail
   通知，此時應收到通知信。
5. 核准後系統自動拆單建立 `draft` 採購單（FR-10），具 `purchase_order.manage` 權限者
   正式發單、模擬收貨與品質驗收，展示合格數量才會增加庫存、瑕疵／拒收數量需另立差異
   案件處理。
6. 刻意輸入一個系統假資料庫中不存在、或與現有供應商名稱高度相似的供應商名稱，觸發
   FR-2b 供應商模糊比對，展示「待人工複核佇列」（管理員角色登入認領、確認或駁回）；
   若設定了 Gmail 通知，管理員應收到通知信。
7. 以具 `audit.read` 權限的角色查看稽核 log 與「採購稽核與流程健康總覽」儀表板。

## 已知限制／未驗證範圍

- `docker compose up --build` 的完整五服務（含 `n8n-init`）啟動流程已於 2026-09-03 由
  Robin 在真實機器上實測成功：五服務皆 `Up (healthy)`、migration 自動套用、demo seed
  自動建立（7 個帳號）、`purchase-request-candidate-flow.json`／`notification-flow.json`
  兩個 workflow 皆自動匯入且未誤匯入 legacy、前端 `http://localhost:5173` 可正常開啟。
  過程中修復了 3 個先前未發現的 Docker 建置問題（Node 版本、`pnpm` build script 核准、
  `Dockerfile` 漏 COPY `pnpm-workspace.yaml`），詳見 `docs/ADR/debug/phase7-integration.md`
  2026-09-03 條目
- `n8n-init` 自動啟用「採購需求候選解析」workflow **經實測證實不可靠**：CLI 指令
  （`update:workflow --active=true`）只改資料庫欄位，不會通知已在跑的 n8n 服務重新註冊
  webhook，UI 顯示 Published 但打正式 webhook 仍可能回 404。**目前確認有效的解法**：到
  n8n 畫面把該 workflow 的 Active 開關關掉再開一次，即可讓服務重新註冊（Robin
  2026-09-03 實測驗證過）。是否要投資改用 n8n Public API 做到完全自動化，屬待決的架構
  決策，見 `docs/ADR/debug/phase7-integration.md`
- Gmail 通知的 OAuth 授權與實際收信尚未實測
- 展示腳本（上方步驟 1–7）跨 Backend／Frontend／n8n／PostgreSQL 全部由 Docker Compose
  同時啟動的完整瀏覽器端到端尚未實測；本次只驗證到服務啟動與 webhook 可正確觸發，尚未
  走過完整業務流程；Phase 4／6 的瀏覽器驗收目前是在 Vite 本機開發伺服器下進行，API 流程
  另由 pytest 覆蓋

`docker compose up --build` 一鍵啟動本身已於 2026-09-03 完成真實環境驗收；Gmail 通知
與完整瀏覽器端到端展示流程仍待驗證，在此之前 Phase 7 整體仍不視為正式驗收完成（見
`docs/specs/PROGRESS.md`）。
