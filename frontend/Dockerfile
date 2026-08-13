# Build stage
FROM node:20-slim AS build
WORKDIR /app
ARG VITE_KAKAO_JS_KEY=
ENV VITE_KAKAO_JS_KEY=$VITE_KAKAO_JS_KEY
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Production stage
FROM nginx:stable-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
