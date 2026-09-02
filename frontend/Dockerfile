# Phase 7：根目錄 Docker Compose 一鍵啟動用。多階段建置：build 階段用 Node 產生
# 靜態檔案，正式提供服務只用 nginx，image 小很多。
FROM node:20-slim AS build
WORKDIR /app
# COREPACK_ENABLE_DOWNLOAD_PROMPT=0：避免非互動 build 環境卡在確認下載提示；
# package.json 的 packageManager 欄位已釘死版本，corepack 才能非互動下正確解析。
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
