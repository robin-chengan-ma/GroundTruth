# GroundTruth

模擬企業內部「需求 → 詢價 → 多供應商報價 → 綜合評選 → 簽核 → 採購單 → 收貨驗收 → 庫存」完整流程的展示型系統。AI 只負責把自然語言需求解析成結構化候選資料，正式金額試算、得標決策、簽核與單據一律由固定程式邏輯與人工確認把關；送往 LLM 的內容會先經過遮罩，敏感的供應商與金額資訊不會外流。

> 這是一個模擬情境的作品展示專案，情境不掛靠任何特定產業，非正式上線系統。

## 核心特色

- **AI 輔助、非 AI 決策**：LLM（Gemini）只做自然語言解析與候選結構化，不參與金額計算、不決定得標者、不能直接建立或修改正式單據；試算、路由、狀態機全部是 Django 裡的固定程式邏輯。
- **送出前先遮罩**：供應商名稱與金額在送給 LLM 之前，由 Django 依當下合作中供應商清單做精確比對並 Token 化（例如 `SUP_001`），解析完成立即用對照表還原，對照表只在單次請求流程中暫存，不落地存 DB。
- **結構化驗證與人工確認**：主檔名稱精確命中才自動對應，模糊或有多個可能值一律交由使用者選擇，不讓 AI 用猜的；供應商模糊比對案件會進入人工複核佇列，由具權限的角色認領處理。
- **權限與職責分離**：申請人不得核准自己的案件，簽核依得標金額分三段門檻路由給對應角色，每個關卡認領後才能決議，避免多人同時處理同一案件。
- **正式單據不可覆寫**：採購單、收貨、驗收與庫存異動皆為 append-only 或版本化快照，錯誤一律用新版、取消、作廢或反向更正處理，不直接改寫歷史紀錄。
- **完整稽核軌跡**：管理員在人工複核佇列的每個決定都會寫入稽核 log；供應商比對、簽核決議與庫存異動皆可回溯。

## 系統流程

```
[Vue：採購需求對話框] 自然語言建立／補充／修改多品項需求與候選供應商
      ↓
[n8n + Gemini] 遮罩敏感資料 → 解析候選結構
      ↓
[Django + Vue] 驗證供應商、品項、數量、規格 → 結構化確認
      ↓
[RFQ] 邀請多間供應商，各自建立獨立版本化報價
      ↓
[Django] 必要規格門檻 → 實際總成本、品質、交期固定公式評分
      ↓
[採購人員] 整單／逐項／拆量選商；系統只建議，不自動得標
      ↓
[簽核] 依得標後實際總成本路由、認領與決議（Gmail 通知待處理角色）
      ↓
[採購單] 核准後依得標供應商拆單，不在此時增加庫存
      ↓
[收貨／品質驗收] 僅合格數量寫入不可覆寫的庫存異動流水帳
      ↓
[Django] 全流程寫入 append-only 稽核紀錄
```

## 技術棧

| 層級 | 技術 | 說明 |
| --- | --- | --- |
| 前端 | Vue 3 + Vite + Pinia | 詢價輸入、採購清單、簽核佇列、供應商管理、稽核 log 檢視 |
| 後端 | Django + DRF | 單一資料真相來源；`repositories/` 存取 DB、`services/` 處理業務邏輯、`api/` 提供 REST endpoint |
| 資料庫 | PostgreSQL | 唯一資料儲存 |
| 身份驗證 | djangorestframework-simplejwt | Vue↔Django 用 JWT；n8n↔Django 用固定 API Key |
| AI | Gemini | 自然語言解析與候選結構化 |
| 流程協調 | n8n（自架） | 只負責串接：接收請求 → 遮罩 → 呼叫 Gemini → 回傳 Django |
| 通知 | Gmail（n8n Gmail 節點） | 通知待處理的複核與簽核角色 |
| 部署 | Docker Compose | 前端、後端、n8n、PostgreSQL 全部容器化，本地一鍵啟動，非公開上線用途 |

## 快速開始

需要 Docker、Docker Compose，以及一組 Gemini API Key。完整步驟、Demo 帳號與展示腳本見
[`docs/reference/demo-guide.md`](docs/reference/demo-guide.md)，這裡是最短版本：

```bash
cp .env.example .env
# 編輯 .env：至少填 POSTGRES_PASSWORD、DJANGO_SECRET_KEY、INTERNAL_API_KEY、GEMINI_API_KEY

docker compose up --build
```

容器啟動時會自動執行資料庫 migration、灌入 demo 種子資料，並自動匯入與啟用 n8n 的 AI 解析
流程；Gmail 通知需要另外手動完成一次 Google 帳號 OAuth 授權才會啟用（無法自動化）。啟動完成後開啟
<http://localhost:5173>。

## 文件索引

專案採 Spec-Driven Development，開發準則見 [`AGENTS.md`](AGENTS.md)。

| 文件 | 內容 |
| --- | --- |
| [`docs/specs/SPEC.md`](docs/specs/SPEC.md) | 唯一定案規格：產品背景、技術棧、功能規格與驗收條件 |
| [`docs/specs/PROGRESS.md`](docs/specs/PROGRESS.md) | 開發進度、測試結果、commit／push／部署狀態 |
| [`docs/specs/DRAFT.md`](docs/specs/DRAFT.md) | 未定案、擱置中的想法與範圍決策 |
| [`docs/reference/`](docs/reference/) | API、DB Schema、部署方式等現行技術參考 |
| [`docs/ADR/discuss/`](docs/ADR/discuss/) | 按功能拆檔的架構與需求討論紀錄 |
| [`docs/ADR/debug/`](docs/ADR/debug/) | 按功能拆檔的除錯與修復紀錄 |

## 專案結構

```
backend/    Django + DRF（api/ services/ repositories/ apps/）
frontend/   Vue 3 + Vite + Pinia
n8n/        workflow 定義與自動初始化腳本
docs/       規格、進度、架構決策與技術參考文件
```

## 授權

[MIT License](LICENSE)
