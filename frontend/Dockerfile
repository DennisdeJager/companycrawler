FROM node:22-alpine AS build
WORKDIR /app
RUN apk add --no-cache git
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
COPY .git /repo/.git
RUN VITE_COMMIT_ID=$(git --git-dir=/repo/.git rev-parse --short HEAD) VITE_BUILD_TIME="$(date -u '+%Y-%m-%d %H:%M:%S UTC')" npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
