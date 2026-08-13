#!/usr/bin/env bash
# 시연용으로 trucks/{truck_id}에 현재 위치와 목적지를 넣는다.
#
# 설계서 D1은 PWA가 사진과 함께 GPS를 보내는 구조지만 PWA가 아직 없고,
# SpaceGeometryReady 이벤트에도 좌표가 없다(2.2 통신 계약). 그래서 matching-processor는
# trucks 문서에서 위치를 읽는다. 이 값이 없으면 M2 경로 회랑을 만들 수 없어
# can_load=false(truck_position_or_destination_unknown)로 끝난다.
#
# PWA가 붙으면 이 스크립트는 필요 없어진다 — 업로드 시점에 좌표가 갱신돼야 한다.
#
#   ./infra/seed_truck_position.sh T-000001 36.3879 127.3823 37.4813 126.8970
set -euo pipefail

cd "$(dirname "$0")/.."
source infra/config.sh

TRUCK_ID="${1:-T-000001}"
CUR_LAT="${2:-36.3879}"   # 대전 (pending_cargos 상차지가 몰려 있는 지역)
CUR_LNG="${3:-127.3823}"
DST_LAT="${4:-37.4813}"   # 서울 구로
DST_LNG="${5:-126.8970}"

TOKEN="$($GCLOUD auth print-access-token | tr -d '[:space:]')"
BASE="https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)/documents"

# 기존 제원 필드를 지우지 않도록 updateMask로 좌표 4개만 갱신한다.
MASK="updateMask.fieldPaths=current_lat&updateMask.fieldPaths=current_lng"
MASK="${MASK}&updateMask.fieldPaths=destination_lat&updateMask.fieldPaths=destination_lng"

curl -s -X PATCH "${BASE}/trucks/${TRUCK_ID}?${MASK}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"fields\":{
        \"current_lat\":{\"doubleValue\":${CUR_LAT}},
        \"current_lng\":{\"doubleValue\":${CUR_LNG}},
        \"destination_lat\":{\"doubleValue\":${DST_LAT}},
        \"destination_lng\":{\"doubleValue\":${DST_LNG}}
      }}" > /dev/null

echo "trucks/${TRUCK_ID} 위치 설정: (${CUR_LAT}, ${CUR_LNG}) -> (${DST_LAT}, ${DST_LNG})"
