#!/bin/sh
set -eu

CONFIG_PATH=/usr/share/nginx/html/config.js
VISION_BASE_URL="${VISION_BASE_URL:-}"
MATCHING_BASE_URL="${MATCHING_BASE_URL:-}"
KAKAO_JS_KEY="${KAKAO_JS_KEY:-}"

cat > "$CONFIG_PATH" <<EOF
window.__MOVEAI_ADMIN__ = {
  VISION_BASE_URL: "${VISION_BASE_URL}",
  MATCHING_BASE_URL: "${MATCHING_BASE_URL}",
  KAKAO_JS_KEY: "${KAKAO_JS_KEY}"
};
EOF

echo "[frontend-admin] wrote config.js"
