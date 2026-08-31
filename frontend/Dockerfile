# React 프로덕션 빌드 -> nginx로 정적 서빙 + /api를 backend 컨테이너로 프록시.
# 컨텍스트는 저장소 루트 기준(docker-compose.yml에서 context: . build.dockerfile: frontend/Dockerfile).
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
