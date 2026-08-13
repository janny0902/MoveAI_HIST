# 빌드 단계 -------------------------------------------------------------------
FROM node:20-alpine AS build
WORKDIR /app

# 의존성 레이어를 소스와 분리해, UI만 고칠 때 npm install을 다시 돌리지 않는다.
COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# 서빙 단계 -------------------------------------------------------------------
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html

# nginx:alpine은 /etc/nginx/templates/*.template를 envsubst로 처리해 conf.d에 넣는다.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# 백엔드 주소를 컨테이너 시작 시 config.js로 써 넣는다(빌드에 굽지 않는다).
COPY docker-entrypoint.d/40-write-config.sh /docker-entrypoint.d/40-write-config.sh
RUN chmod +x /docker-entrypoint.d/40-write-config.sh

ENV PORT=8080
EXPOSE 8080
