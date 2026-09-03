#!/bin/sh
# Phase 7：n8n workflow 冪等初始化（Codex 建議方案，Robin 2026-09-02 核准）。
#
# 由獨立的 n8n-init 服務執行，在 n8n 主服務 healthcheck 通過後才跑，並與主
# 服務共用同一份 groundtruth_n8n_data volume，因此匯入結果對正在跑的 n8n
# 立即生效，不需要重啟 n8n 容器。
#
# 冪等性：n8n/workflows/*.json 內都已內建固定的 `id` 欄位（見各檔案），
# `n8n import:workflow` 依 id 覆蓋既有紀錄，不會每次啟動都產生新副本
# （官方文件：匯入時 id 與既有紀錄相同即覆寫，而非新增）。
#
# 只匯入現行必要的「採購需求候選解析」與「Gmail 通知」流程；legacy
# inquiry-flow.json 刻意不在下面的匯入清單內，本流程不會碰到或啟用它。
#
# 匯入與啟用的分工：
# - 匯入失敗（`set -e` 觸發）→ 本容器以非 0 狀態結束，`docker compose` 會
#   明確顯示 n8n-init 失敗，不會靜默略過。
# - 「採購需求候選解析」流程匯入後嘗試自動發布；改用 `publish:workflow`
#   （n8n 2.0 起 `update:workflow --active=true` 已 deprecated，見
#   docs/ADR/debug/phase7-integration.md 2026-09-03 條目），發布失敗時只印
#   警告、不中止整個初始化，需要 Robin 手動到 n8n 畫面確認並視需要手動啟用。
# - 「Gmail 通知」流程刻意只匯入、不呼叫發布指令：Google 帳號 OAuth 授權
#   仍須在 n8n 畫面上手動完成一次（無法自動化），完成後才由 Robin 手動啟用。
# - 兩個 workflow 都在 webhook 節點後加了「IF：Internal API Key 正確？」，
#   比對 header `X-Internal-Api-Key` 是否等於 `INTERNAL_API_KEY` 環境變數，
#   不符合直接回 401（見 docs/ADR/debug/phase7-integration.md 2026-09-03
#   條目：修復前這兩支 webhook 任何人都能直接打，不需要任何驗證）。
set -e

WORKFLOWS_DIR=/home/node/workflows
CANDIDATE_ID=groundtruth-purchase-request-candidate-flow

echo "[n8n-init] 匯入採購需求候選解析流程（AI 解析，必要）..."
n8n import:workflow --input="$WORKFLOWS_DIR/purchase-request-candidate-flow.json"

echo "[n8n-init] 匯入 Gmail 通知流程（先不啟用，需完成 Google OAuth 授權後再手動啟用）..."
n8n import:workflow --input="$WORKFLOWS_DIR/notification-flow.json"

echo "[n8n-init] 嘗試發布（啟用）採購需求候選解析流程..."
if n8n publish:workflow --id="$CANDIDATE_ID"; then
  echo "[n8n-init] 發布成功。"
else
  echo "[n8n-init] 警告：自動發布失敗（可能是這個 n8n 版本的 publish:workflow 指令行為不同）。"
  echo "[n8n-init] 請手動到 http://localhost:5678 開啟「GroundTruth - 採購需求候選解析（Phase 5 起正式流程）」並啟用。"
fi

echo "[n8n-init] n8n workflow 初始化完成。"
echo "[n8n-init] 提醒：Gmail 通知流程尚未啟用。請到 http://localhost:5678 開啟"
echo "[n8n-init]      「GroundTruth - Gmail 通知（FR-6b／FR-8）」，在寄送 Gmail 節點完成"
echo "[n8n-init]      一次 Google 帳號 OAuth 授權後，自行點右上角 Active 開關啟用。"
echo "[n8n-init] legacy「[歷史／Phase 3 已停用] ...」流程本次未匯入、未啟用，維持現況。"
