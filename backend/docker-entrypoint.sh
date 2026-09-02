#!/bin/sh
# Phase 7：backend 容器啟動流程（Codex 建議方案，Robin 2026-09-02 核准）。
#
# 1) migrate 一定執行。
# 2) 只有 LOAD_DEMO_DATA=true 時才灌 demo 種子資料，避免非展示用途誤灌假資料；
#    `seed_demo_data` 全部使用 get_or_create（見該檔案 docstring），重複執行
#    不會產生重複帳號／主檔，也不會清空或覆蓋既有正式資料。
# 3) 任一步驟失敗（exit code 非 0）本 script 因 `set -e` 立即中止，容器隨之
#    以非 0 狀態結束並印出實際錯誤，不會靜默帶著半套資料或壞掉的 migration
#    狀態啟動 Django。
set -e

echo "[backend-entrypoint] 執行資料庫 migration..."
python manage.py migrate --noinput

if [ "${LOAD_DEMO_DATA:-false}" = "true" ]; then
  echo "[backend-entrypoint] LOAD_DEMO_DATA=true，執行 seed_demo_data（冪等，不清空／不覆蓋既有資料）..."
  python manage.py seed_demo_data
else
  echo "[backend-entrypoint] LOAD_DEMO_DATA 未啟用，略過灌入 demo 假資料。"
fi

echo "[backend-entrypoint] 啟動 Django..."
exec python manage.py runserver 0.0.0.0:8000
