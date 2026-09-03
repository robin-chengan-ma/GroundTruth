---
title: Phase 7 一鍵啟動除錯紀錄
updated: 2026-09-03
---

# Phase 7 一鍵啟動除錯紀錄

## 2026-09-03 `docker compose up --build` frontend image 建置失敗

**現象**：Robin 於本機首次執行 `docker compose up --build` 驗證 Phase 7 一鍵啟動（對應
`docs/specs/SPEC.md` 驗收矩陣「全新環境一鍵啟動」情境），`frontend` image 建置在
`RUN pnpm install --frozen-lockfile` 步驟失敗，整個 `docker compose up` 中止，`backend`
的建置步驟因此被取消（非 backend 本身問題）。

**排查過程**：檢視建置輸出，pnpm 本身印出警告：

```
warn: This version of pnpm requires at least Node.js v22.13
The current version of Node.js is v20.20.2
Error [ERR_UNKNOWN_BUILTIN_MODULE]: No such built-in module: node:sqlite
```

比對 `frontend/package.json` 的 `packageManager: "pnpm@11.25.0"` 與
`frontend/Dockerfile` build 階段的 `FROM node:20-slim`，確認版本不相容。

**根因**：`frontend/package.json` 已透過 `packageManager` 欄位釘死 `pnpm@11.25.0`，該版本
要求 Node.js >= 22.13（會用到 `node:sqlite` 內建模組）；但 `frontend/Dockerfile` 的 build
階段仍使用 `node:20-slim`，corepack 依 `packageManager` 解析安裝 pnpm 11.25.0 後即因 Node
版本不足而在啟動時就丟出 `ERR_UNKNOWN_BUILTIN_MODULE`。屬於 Dockerfile 基底映像版本落後於
專案既有版本釘選的建置環境問題，不涉及產品邏輯或規格。

**修復方式**：改 `frontend/Dockerfile` build 階段基底映像為 `node:22-slim`，並在該行上方加
註解說明原因，避免之後又被改回較舊版本。其餘階段（`nginx:1.27-alpine`）與 `backend`
Dockerfile 不受影響，未修改。

**驗證方式**：本次修復由 Claude 在沒有 Docker 的沙箱環境完成，無法實際執行
`docker compose up --build` 驗證；待 Robin 於本機重新執行後回報結果，再補上實測結論。

**未驗證範圍**：整個 Phase 7 五服務一鍵啟動流程（migration、demo seed、n8n workflow 自動
匯入與啟用、前端可開啟）仍全數待重新驗證——這次只排到 frontend 建置這一步就中止，後面的
service 尚未起來過。

## 2026-09-03 修復①之後，frontend image 建置在下一步又失敗（`ERR_PNPM_IGNORED_BUILDS`）

**現象**：套用上一則修復（`node:22-slim`）後，Robin 重新執行 `docker compose up --build`，
`frontend` build 這次成功解析並下載了全部套件，但緊接著失敗：

```
[ERR_PNPM_IGNORED_BUILDS] Ignored build scripts: esbuild@0.28.2
Run "pnpm approve-builds" to pick which dependencies should be allowed to run scripts.
```

`backend` 這次已成功建置完成（不再被取消），確認上一則修復本身有效，這是新的、獨立的第二個
建置問題。

**排查過程**：pnpm（`packageManager` 釘死的 `pnpm@11.25.0`）預設不會執行依賴套件的
build/postinstall script（供應鏈安全機制），未在允許清單中的套件會被跳過並要求明確核准；
互動環境下可執行 `pnpm approve-builds` 手動選擇，但 `docker compose build` 是非互動環境，
沒有人可以回應核准提示，此時 pnpm 選擇直接以非 0 狀態結束，而不是靜默略過該套件的 build
script。`esbuild` 需要這個 build script 才能安裝對應平台的原生執行檔，Vite／`vue-tsc` 都
依賴 `esbuild`，就算略過不報錯，後續 `pnpm build` 大機率也會因缺少 `esbuild` 執行檔而失敗。

在 Claude 端沒有 Docker 的沙箱環境用同一份 `frontend/package.json`＋`pnpm-lock.yaml`、
同版本 `pnpm@11.25.0`（corepack 解析）重現安裝，多次嘗試皆未能重現一模一樣的
`ERR_PNPM_IGNORED_BUILDS` 阻擋行為（該沙箱的網路與全域設定與 Robin 全新 `node:22-slim`
容器不同，具體差異未查出確切原因）；因此本次修復是依 pnpm 錯誤訊息本身指出的正規做法設計，
**未能在原始失敗情境下重現後再驗證修復有效，需 Robin 實機確認**。

**根因**：`frontend/package.json` 未宣告 `pnpm.onlyBuiltDependencies`，非互動的 Docker
build 環境下 pnpm 對未核准的 build script 直接視為錯誤中止，而不是略過繼續。

**修復方式**：於 `frontend/package.json` 新增

```json
"pnpm": {
  "onlyBuiltDependencies": ["esbuild"]
}
```

這是 `pnpm approve-builds` 互動核准後實際寫入 `package.json` 的同一種設定，等同於預先把
`esbuild` 核准寫死，非互動環境下不再需要提示。

**驗證方式**：在沙箱環境用同一份 `pnpm-lock.yaml` 重新執行 `pnpm install --frozen-lockfile`
（先清空 `node_modules`），確認：①指令成功結束（exit 0）；②`pnpm-lock.yaml` 沒有被改寫
（`git diff` 無差異），代表這個設定不影響 `--frozen-lockfile` 的鎖定檔一致性檢查，
Robin 不需要重新產生鎖定檔。**未能在會重現原始阻擋錯誤的環境下驗證此設定真的能解除阻擋**，
這部分待 Robin 重新執行 `docker compose up --build` 確認。

**未驗證範圍**：`docker compose up --build` 完整跑完（含 `pnpm build`／`vite build`
是否能正常產生 `dist/`）、migration、demo seed、n8n workflow 自動匯入與啟用、前端可
開啟——這些仍是本情境完整待驗清單，尚未有任何一次跑到 frontend 建置之後的階段。

## 2026-09-03 修復②其實無效，真正根因是 Dockerfile 少 COPY 一個檔案

**現象**：套用上一則的 `pnpm.onlyBuiltDependencies` 修復後，Robin 第三次執行
`docker compose up --build`，`backend` 這次完全用 cache 秒過，`frontend` build 仍在
同一步驟失敗，而且這次多印出一行過去沒看到的警告：

```
[WARN] The "pnpm" field in package.json is no longer read by pnpm. The following keys
were ignored: "pnpm.onlyBuiltDependencies". See https://pnpm.io/settings for the new
home of each setting.
```

證實上一則修復完全沒生效——pnpm 直接忽略了它，`ERR_PNPM_IGNORED_BUILDS` 原樣重現。

**排查過程**：這行警告點出關鍵：`package.json` 的 `pnpm` 欄位已被 pnpm 棄用，設定改放
別處。檢查 repo 既有的 `frontend/pnpm-workspace.yaml`，發現裡面**早就有**這個設定：

```yaml
allowBuilds:
  esbuild: true
```

也就是說 esbuild 的核准設定根本就已經存在於 repo 裡，從來都不是缺設定的問題。回頭看
`frontend/Dockerfile` 的 build 階段：

```dockerfile
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
```

`pnpm install` 執行的當下，容器裡只有 `package.json`／`pnpm-lock.yaml`，**`pnpm-workspace.yaml`
還沒被複製進去**（要等到下一行 `COPY . .` 才會進來，但那時候 install 已經跑完/失敗了）。
pnpm 因此看不到 `allowBuilds` 設定，判定 esbuild 未核准，直接中止。

在沙箱環境用同一份 `package.json`／`pnpm-lock.yaml` 完整重現此行為後（無 `pnpm-workspace.yaml`
時必定重現 `ERR_PNPM_IGNORED_BUILDS`，exit 1），加回 `pnpm-workspace.yaml` 後重新執行
`pnpm install --frozen-lockfile`，成功結束且 `pnpm-lock.yaml` 未被改寫——**這次是在會重現
原始錯誤的情境下驗證過的**，不同於前兩則修復。

**根因**：`frontend/Dockerfile` 的 `COPY` 指令沒有把 `pnpm-workspace.yaml` 一起複製進
build context，導致 `pnpm install` 執行時讀不到既有的 `allowBuilds` 設定。上一則修復
（改用 `package.json` 的 `pnpm` 欄位）方向錯誤：這個欄位在目前 pnpm 版本已不生效，就算
Dockerfile 有這個問題，那則修復本來就不可能成功。

**修復方式**：
1. 撤銷上一則修復：移除 `frontend/package.json` 裡已確認無效的 `pnpm.onlyBuiltDependencies` 欄位。
2. `frontend/Dockerfile` 的 `COPY package.json pnpm-lock.yaml ./` 改為
   `COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./`，並加註解說明原因。

**驗證方式**：沙箱環境用 Robin repo 內完全相同的 `package.json`（未改版本前的原始內容）、
`pnpm-lock.yaml`、`pnpm-workspace.yaml`，同版本 `pnpm@11.25.0`：(a) 缺 `pnpm-workspace.yaml`
時執行 `pnpm install --frozen-lockfile`，重現 `ERR_PNPM_IGNORED_BUILDS`、exit 1；
(b) 補上 `pnpm-workspace.yaml` 後重新執行（先清空 `node_modules`），成功結束、exit 0，
`pnpm-lock.yaml` 未被改寫。前後對照確認這次的根因判斷與修復皆正確。

**未驗證範圍**：`frontend/.dockerignore` 已確認未排除 `pnpm-workspace.yaml`，理論上這個
修復足夠讓 `pnpm install` 通過；但沙箱沒有 Docker，無法驗證接下來的 `pnpm build`
（`vue-tsc -b && vite build`）與整個 Docker layer cache 行為是否正常，也還沒驗證 backend
migration／demo seed／n8n workflow 自動匯入與啟用／前端可開啟——這些仍待 Robin 這次
`docker compose up --build` 一次跑完後回報。

## 2026-09-03 frontend／backend image 建置全部通過，`docker compose up` 卡在容器名稱衝突

**現象**：套用上一則修復後，Robin 第四次執行 `docker compose up --build`：`backend`
全部 cache 命中、`frontend` 的 `pnpm install`／`pnpm build` 皆成功完成，兩個 image 都
建置成功。到了啟動容器階段才失敗：

```
Error response from daemon: Conflict. The container name "/groundtruth-n8n" is already
in use by container "9e90e40103a1...". You have to remove (or rename) that container.
```

**根因**：非程式碼缺口。前幾次測試在建置階段失敗、`docker compose up` 未能正常跑完就
中斷，殘留了同名的舊 `groundtruth-n8n` 容器（Docker container name 需唯一），這次重新
`up` 時發生名稱衝突。與 `docker-compose.yml`／Dockerfile／workflow 邏輯本身無關，是
Robin 本機 Docker 環境的殘留狀態問題。

**修復方式**：不涉及程式碼變更。建議 Robin 在自己機器執行：

```bash
docker compose down --remove-orphans
```

清掉這個 compose project 底下所有殘留容器（不會刪除 `groundtruth_postgres_data`／
`groundtruth_n8n_data` 這兩個具名 volume，demo 資料與已匯入的 n8n workflow 不受影響），
再重新執行 `docker compose up --build`。

**驗證方式**：等 Robin 清掉殘留容器、重新執行後回報結果。

**未驗證範圍**：backend migration／demo seed 是否自動建立、n8n-init 是否成功匯入並啟用
「採購需求候選解析」workflow、前端 `http://localhost:5173` 是否可正常開啟——這些仍是本情境
最後一段待驗清單，frontend／backend 建置本身已確認沒問題。

## 2026-09-03 修正上一則診斷：容器衝突並非「up 沒跑完的殘留」，是兩份 docker-compose.yml 撞名

**現象**：Robin 依上一則建議執行 `docker compose down --remove-orphans`，輸出只顯示
`groundtruth-frontend`／`groundtruth-backend`／`groundtruth-postgres` 與網路被移除，
**完全沒有提到 `groundtruth-n8n`**；重新 `docker compose up --build` 後，同一個
`groundtruth-n8n` 容器名稱衝突原樣重現（同一個 container ID `9e90e40103a1...`）。

**排查過程**：`down --remove-orphans` 只會清掉「屬於同一個 compose project、但目前
compose 檔案已移除」的孤兒容器；它完全沒動 `groundtruth-n8n`，代表這個容器根本不屬於
根目錄這個 compose project。檢查 `n8n/docker-compose.yml`（Phase 2 遺留，供只需單獨
啟動 n8n 的情境使用），發現裡面的服務也寫死 `container_name: groundtruth-n8n`，
使用**不同**的 volume（`n8n_data`，即獨立 project 的 `n8n_n8n_data`，與根目錄 compose
的 `groundtruth_n8n_data` 是兩份不同資料）。上一則條目把根因誤判為「先前建置失敗留下的
殘留容器」，其實是 Robin 先前（Phase 2 開發階段）用這份獨立 compose 啟動過 n8n，該容器
仍在（不論是否還在執行），與根目錄 compose project 是兩個不相干的 project，只是剛好
container name 撞在一起，`docker compose down`（根目錄）天生看不到它、管不到它。

**根因**：repo 內兩份 docker-compose.yml（根目錄 Phase 7 版本、`n8n/` 獨立版本）各自
的 n8n 服務都寫死同一個 `container_name: groundtruth-n8n`，且都綁 `5678` port；只要
其中一份啟動過，另一份就會在容器建立階段撞名（若前者已在跑，還會先撞 port）。這是 repo
既有設計就存在的潛在衝突，非本次 Phase 7 新增程式碼造成，先前未發現是因為兩份 compose
一直沒有被同一位開發者交錯使用過。

**修復方式**：不改程式碼（兩份 compose 各自的使用情境不同，改名稱屬於會影響既有操作習慣
的變更，且非本次驗收範圍，不逕自更動）。請 Robin 直接移除這個獨立於根目錄 compose project
之外的容器：

```bash
docker rm -f groundtruth-n8n
```

（只刪容器，不刪 volume；`n8n/docker-compose.yml` 用的 `n8n_data` volume 不受影響，
之後仍可用 `cd n8n && docker compose up` 復原那個獨立 n8n 環境），再重新於根目錄執行
`docker compose up --build`。`docs/reference/deploy.md` 已補上這個撞名限制的說明，
提醒未來不要同時或交錯啟動這兩份 compose。

**驗證方式**：待 Robin 移除容器後重新執行回報結果。

**未驗證範圍**：backend migration／demo seed／n8n-init workflow 自動匯入與啟用／前端
可開啟，仍是本情境最後、也是目前唯一還沒觸及過的待驗範圍。

## 2026-09-03 確認：n8n 自動啟用 workflow 這步實際上沒有生效（非理論風險，已實測證實）

**現象**：n8n workflow 匯入成功，UI 上「採購需求候選解析」也顯示綠色「Published」，
但直接打它的正式 webhook：

```bash
curl -i -X POST http://localhost:5678/webhook/purchase-request-candidate -d '{}'
```

回傳 **404**：

```json
{"code":404,"message":"The requested webhook \"POST purchase-request-candidate\" is not
registered.","hint":"The workflow must be active for a production URL to run
successfully. You can activate the workflow using the toggle in the top-right of the
editor. ..."}
```

證實 UI 上的「Published」標記只反映資料庫欄位，不代表跑著的 n8n 服務真的已經註冊這個
webhook——`n8n-init` 這步過去在文件裡一直標注「理論風險，未實測」，這次是第一次真正
用實際請求驗證，確認**這個自動化目前不可靠**。

**排查過程**：對照 `n8n-init` log 裡 `update:workflow --active=true` 執行時印出的原話：

```
⚠️  WARNING: The "update:workflow" command is deprecated.
Please use: publish:workflow --id=...
Note: Changes will not take effect if n8n is running.
Please restart n8n for changes to take effect if n8n is currently running.
```

`update:workflow` 是直接改資料庫的 `active` 欄位，不會通知正在跑的 n8n process 重新
註冊 webhook；而 `n8n-init` 依 `depends_on: n8n: condition: service_healthy` 設計，
本來就是在 `n8n` 主服務已經活著之後才執行，等於每次都精準踩進這個「服務已在跑、CLI 改
了資料庫但服務不知道」的情境。額外查了 n8n 官方原始碼裡的 breaking-change 規則說明
（`cli-replace-update-workflow-command.rule.js`），官方對這個情境的正式建議是：
「自動化腳本應改用 Public API 個別啟用 workflow，不要用 CLI」，而不是換用
`publish:workflow` 這個新 CLI 指令了事——代表就算換成新指令，作為非互動 script 呼叫時
是否真的能讓已在跑的服務即時生效，官方本身也沒有背書。

**根因**：`n8n update:workflow`／`publish:workflow` 這類 CLI 指令是設計給「n8n 尚未
啟動、或啟動後會重啟」的情境用（例如寫在 entrypoint 裡、容器啟動時執行一次就重啟），不
是設計給「n8n 已經在跑、且不會重啟」的旁路 sidecar 容器（目前 `n8n-init` 的架構）用。

**目前處理方式（不逕自變更架構）**：這是會改變「一鍵啟動」自動化方式的架構決策
（改用 n8n Public API＋API Key 個別啟用，需要額外處理 API Key 產生／儲存；或接受
「匯入自動化、啟用需人工在畫面上點一次」作為 Phase 7 一鍵啟動的正式定義），依 AGENTS.md
中大型實作前先確認的規則，不逕自實作，待 Robin 決定要選哪個方向。**當下解法**：Robin
直接到 http://localhost:5678 該 workflow 的編輯畫面，把右上角 Active／Published 開關
關掉再開一次（這是官方文件本身建議的正常操作路徑，能讓跑著的服務重新註冊 webhook），
再重新執行上面的 curl 確認不再是 404。

**驗證方式**：待 Robin 手動切換開關後，重新執行 webhook curl 測試回報結果。

**未驗證範圍**：前端 `http://localhost:5173` 是否可正常開啟——本情境目前唯一還沒驗證的
最後一項。

## 2026-09-03 手動切換 Active 開關解法驗證有效

**驗證方式**：Robin 在 n8n 畫面把「採購需求候選解析」的 Active 開關關掉再開一次，重新執行
`curl -i -X POST http://localhost:5678/webhook/purchase-request-candidate -d '{}'`，
這次不再是 404，Executions 列表出現一筆對應的執行紀錄，證實 webhook 已正確重新註冊。

**結論**：上一則條目提出的「當下解法」（人工切換一次 Active 開關）確認有效，能解除
`n8n-init` 自動啟用不可靠造成的阻塞；是否要進一步投資让匯入後自動啟用也可靠（例如改用
n8n Public API），仍是待 Robin 決定的架構問題，本次不逕自實作。

**附帶觀察（非本情境驗收範圍，不判定為缺陷）**：這筆用空 `{}` payload 觸發的 execution
執行超過 1 分半仍顯示 Running，研判是刻意送的無效測試資料缺少必要欄位，導致某個 node
（可能是呼叫 Gemini 的那步）卡住等待或重試；因為這不是 demo-guide.md 設計的正常展示流程
輸入，本次不予排查，留給 Robin 視需要用「Stop all」手動終止即可。若之後用正確格式的 payload
（走 demo-guide.md 展示腳本，由 Django 遮罩後送出）測試時仍出現這種卡住行為，才需要另開
排查。

## 2026-09-03 Gmail 通知／候選解析兩支 webhook 缺少身分驗證

**現象**：驗證 FR-6b／FR-8 Gmail 通知鏈路時，直接用 curl 打 `POST /webhook/notify`（完全沒有帶任何
header）就成功寄出信件、拿到 `{"sent":true}`，實際收到信。

**排查過程**：查 `n8n/workflows/notification-flow.json` 與 `purchase-request-candidate-flow.json` 的
webhook 節點設定，兩者 `parameters.options` 都是空物件，`authentication` 欄位維持 n8n 預設的
「無驗證」，不是 headerAuth。對照 Django 呼叫端 `backend/services/notification_service.py`、
`backend/repositories/inquiry.py`，兩者都正確送出 `X-Internal-Api-Key: settings.INTERNAL_API_KEY`；
`docs/reference/api.md` 修復前的內容甚至已經寫著「Django 主動呼叫 n8n...同上 header 驗證」——文件
宣稱這個方向有驗證，但 n8n 端從未真正檢查這個 header，任何人只要連得到 5678 port，就能不帶任何
憑證直接觸發寄信（用 Robin 真實連接的 Gmail 帳號）或呼叫 Gemini（消耗真實 API 額度）。

**根因**：設計 Django→n8n 這個方向的認證時，只在 Django 呼叫端加上了 header，兩支 workflow 都沒有
在 n8n webhook 端加對應的驗證節點；`docs/reference/api.md` 當初直接假設兩邊都做了對稱驗證，寫成
文件時沒有實際驗證過，造成文件與程式碼不一致。

**修復方式**：
1. 在 `notification-flow.json`、`purchase-request-candidate-flow.json` 的 webhook 節點後方各加一個
   「IF：Internal API Key 正確？」節點，比對 `{{$json.headers['x-internal-api-key']}}` 是否等於
   `{{$env.INTERNAL_API_KEY}}`；n8n 主服務環境已有 `INTERNAL_API_KEY` 與
   `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`（見本檔 Phase 2 `$env` 踩坑紀錄），`$env` 存取沒有問題。
   不符合直接回 401 `{"detail":"unauthorized"}`，不繼續往下執行（notify 不寄信、candidate 不呼叫
   Gemini）。
2. `n8n/scripts/init-workflows.sh` 的 deprecated `update:workflow --active=true` 換成
   `publish:workflow --id=...`（官方文件確認的正式替代指令）。
3. 兩支 workflow 的說明 sticky note 補上這次修復的說明。

**驗證方式**：目前只完成 JSON／腳本層級的靜態檢查（Python 重新載入兩份 workflow JSON、確認所有
`connections` 參照的節點名稱都存在、`sh -n` 檢查腳本語法皆通過）；尚未在真實 n8n 服務跑過。待 Robin
`docker compose up --build` 套用新版 workflow 後，麻煩分三種情況各打一次 curl 確認：
1. 帶正確 `X-Internal-Api-Key` → 正常執行（notify 收到信／candidate 收到解析結果）
2. 帶錯誤 key → 401 `{"detail":"unauthorized"}`
3. 完全不帶這個 header → 401（也就是重現這次發現問題的原始呼叫方式，這次應該要失敗）

**未驗證範圍**：
- `publish:workflow` 是否會重蹈上一則條目 `update:workflow` 同樣「服務已在跑、CLI 改資料庫但不會
  通知服務重新註冊 webhook」的問題，尚未在真實環境測過，麻煩 Robin 這次順便一併確認；若仍不可靠，
  照舊需要手動切換一次 Active 開關。
- 本次只補上「Django 呼叫 n8n」這個方向的驗證；`docs/reference/api.md` 其餘既有認證欄位（Vue／n8n
  呼叫 Django 的方向）本次沒有重新查證，維持原狀。
- n8n Editor 手動「Execute step」單節點測試持續卡住無回應（轉圈圈、無任何提示）這件事，根因尚未
  確認；已證實不影響正式 webhook 執行路徑，暫不視為阻塞項，記為「n8n Editor 手動單節點執行異常，
  根因未確認」，未有官方 issue 或原始碼佐證前不定義成 n8n 已知 bug。

## 2026-09-03 安全修復與 publish:workflow 皆已在真實環境驗證

**驗證方式**：Robin 在真實環境重新套用兩支修復後的 workflow，針對 `notify`／
`purchase-request-candidate` 兩支 webhook 各打三種情況（正確 `X-Internal-Api-Key`／錯誤
key／完全不帶 header），共 6 次請求，結果皆符合預期：帶正確 key 正常執行，錯誤或缺少
header 都回 401 `{"detail":"unauthorized"}`。webhook 身分驗證缺口修復確認生效。

**`publish:workflow` 是否解決 CLI 自動啟用不可靠的問題**：**沒有解決，跟 `update:workflow`
一樣不可靠**。Robin 這次重新套用候選解析流程時，起初打 webhook 一樣回 404，需要在 n8n
畫面手動把 Active 開關切一次之後才生效，跟先前 `update:workflow` 遇到的情況完全相同。
證實：這不是 `update:workflow` 這個指令本身 deprecated 造成的問題，而是「CLI 改資料庫、
不會通知已在跑的 n8n process 重新註冊 webhook」這個根因，`publish:workflow` 一樣是走
CLI 改資料庫的路徑，換指令名稱沒有解決根本問題。

**結論**：`init-workflows.sh` 换用 `publish:workflow` 仍值得保留（至少不再印 deprecated
警告），但不能期待它讓「一鍵啟動時自動啟用」變可靠——`n8n-init` 目前的架構（CLI 對已在跑
的服務改資料庫）本質上就會遇到這個限制，不論用哪個 CLI 指令都一樣。要做到真正可靠的自動
啟用，需要改用 n8n Public API（官方原始碼註解建議的方向），這仍是待 Robin 決定是否投資的
架構問題，本次不逕自實作。「候選解析流程需人工切換一次 Active 開關」維持是目前 Phase 7
一鍵啟動的已知、已記錄限制。

**驗收狀態**：webhook 身分驗證修復——**通過**。n8n 自動啟用可靠性——**維持原本已知限制，
未改善**。
