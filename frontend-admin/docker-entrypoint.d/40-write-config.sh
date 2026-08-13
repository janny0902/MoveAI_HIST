#!/bin/sh
# 백엔드 주소를 런타임에 config.js로 써 넣는다.
# 빌드에 굽지 않는 이유: 같은 이미지를 dev/prod 어디에나 올릴 수 있어야 하고,
# 백엔드 URL이 바뀌었다고 프론트를 다시 빌드하고 싶지 않기 때문이다.
set -eu

OUT=/usr/share/nginx/html/config.js

cat > "$OUT" <<EOF
window.__APP_CONFIG__ = {
  VISION_BASE_URL: "${VISION_BASE_URL:-}",
  MATCHING_BASE_URL: "${MATCHING_BASE_URL:-}",
  KAKAO_JS_KEY: "${KAKAO_JS_KEY:-}"
};
EOF

# KAKAO_JS_KEY는 카카오 지도용 JavaScript 키다. 도메인 제한이 걸린 공개 키라
# 브라우저에 나가도 된다 — 서버에서만 쓰는 REST 키와 혼동하지 말 것.
echo "config.js 작성: VISION=${VISION_BASE_URL:-<미설정>} MATCHING=${MATCHING_BASE_URL:-<미설정>} KAKAO_MAP=${KAKAO_JS_KEY:+설정됨}${KAKAO_JS_KEY:-<미설정>}"
