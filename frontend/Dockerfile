# Phase 7：根目錄 Docker Compose 一鍵啟動用。多階段建置：build 階段用 Node 產生
# 靜態檔案，正式提供服務只用 nginx，image 小很多。
# node:20-slim 會導致 `pnpm install` 失敗（pnpm 11.x 要求 Node >= 22.13，
# 見 docs/ADR/debug/phase7-integration.md 2026-09-03 條目），故用 22-slim。
FROM node:22-slim AS build
WORKDIR /app
# COREPACK_ENABLE_DOWNLOAD_PROMPT=0：避免非互動 build 環境卡在確認下載提示；
# package.json 的 packageManager 欄位已釘死版本，corepack 才能非互動下正確解析。
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
# pnpm-workspace.yaml 一併複製：pnpm 目前把 `allowBuilds`／`onlyBuiltDependencies` 等
# 設定放在這個檔案（package.json 的 pnpm 欄位已不再被讀取，見
# docs/ADR/debug/phase7-integration.md 2026-09-03 條目），install 前沒複製到，
# esbuild 的 build script 會被 pnpm 判定未核准而中止安裝。
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
