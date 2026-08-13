#!/usr/bin/env bash
# 실제 배포 상태가 infra/config.sh와 일치하는지 확인한다(아무것도 바꾸지 않는다).
# 콘솔에서 손으로 만졌거나 --memory 없는 gcloud run deploy를 친 뒤 설정이 어긋났는지 잡는 용도.
# 불일치가 하나라도 있으면 exit 1.
#
#   ./infra/verify.sh
set -uo pipefail

cd "$(dirname "$0")/.."
source infra/config.sh

# gcloud.cmd(Windows)는 출력을 CRLF로 준다. 비교 전에 \r을 떼지 않으면 전부 불일치로 잡힌다.
# --format 문자열에 따옴표를 중첩하면 cmd.exe가 인자를 깨뜨리므로 기본 탭 구분자만 쓴다.
strip_cr() { tr -d '\r'; }

failed=0

check() {  # check <항목> <기대값> <실제값>
  if [[ "$2" == "$3" ]]; then
    printf '  OK    %-15s %s\n' "$1" "$3"
  else
    printf '  DRIFT %-15s 기대=%s  실제=%s\n' "$1" "$2" "$3"
    failed=1
  fi
}

echo "== Cloud Run =="
svc="$($GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT_ID" \
  --format='value(spec.template.spec.containers[0].resources.limits.memory,spec.template.spec.containers[0].resources.limits.cpu,spec.template.spec.containerConcurrency,spec.template.spec.serviceAccountName)' \
  2>/dev/null | strip_cr)"

# minScale은 annotation이라 조회하려면 --format 안에 따옴표를 중첩해야 하는데,
# 그러면 gcloud.cmd가 cmd.exe를 거치며 인자를 통째로 깨뜨린다. 별도로 받아 셸에서 뽑는다.
min_scale="$($GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT_ID" \
  --format='value(spec.template.metadata.annotations)' 2>/dev/null | strip_cr \
  | grep -oE 'minScale.{0,12}' | grep -oE '[0-9]+' | head -1)"

if [[ -z "$svc" ]]; then
  echo "  서비스 '$SERVICE'를 찾을 수 없다. ./infra/deploy.sh 먼저 실행."
  exit 1
fi

IFS=$'\t' read -r cur_mem cur_cpu cur_conc cur_sa <<<"$svc"
check memory         "$MEMORY"          "$cur_mem"
check cpu            "$CPU"             "$cur_cpu"
check concurrency    "$CONCURRENCY"     "$cur_conc"
check serviceAccount "$SERVICE_ACCOUNT" "$cur_sa"
check minInstances   "$MIN_INSTANCES"   "${min_scale:-0}"

echo
echo "== 런타임 SA 권한 =="
roles="$($GCLOUD projects get-iam-policy "$PROJECT_ID" \
  --flatten='bindings[].members' \
  --filter="bindings.members:${SERVICE_ACCOUNT}" \
  --format='value(bindings.role)' 2>/dev/null | strip_cr)"

for role in \
  roles/storage.objectAdmin \
  roles/datastore.user \
  roles/pubsub.publisher \
  roles/aiplatform.user
do
  if grep -qx -- "$role" <<<"$roles"; then
    printf '  OK    %s\n' "$role"
  else
    printf '  없음  %s\n' "$role"
    failed=1
  fi
done

# --filter에 공백('AND')이 들어가면 Windows의 gcloud.cmd가 인자를 깨뜨린다.
# 바인딩 전체를 받아 role+member 쌍을 셸에서 매칭한다.
sa_bindings="$($GCLOUD iam service-accounts get-iam-policy "$SERVICE_ACCOUNT" \
  --project "$PROJECT_ID" --flatten='bindings[].members' \
  --format='value(bindings.role,bindings.members)' 2>/dev/null | strip_cr)"
if grep -q "^roles/iam\.serviceAccountTokenCreator[[:space:]]*serviceAccount:${SERVICE_ACCOUNT}$" <<<"$sa_bindings"; then
  printf '  OK    roles/iam.serviceAccountTokenCreator (자기 자신)\n'
else
  printf '  없음  roles/iam.serviceAccountTokenCreator (자기 자신) — signed URL 발급 불가\n'
  failed=1
fi

echo
echo "== Eventarc =="
if $GCLOUD eventarc triggers describe "$TRIGGER" --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "  OK    트리거 $TRIGGER"
else
  echo "  없음  트리거 $TRIGGER — ./infra/bootstrap.sh 실행"
  failed=1
fi

echo
if [[ $failed -eq 0 ]]; then
  echo "설정 일치."
else
  echo "불일치 있음. ./infra/bootstrap.sh 또는 ./infra/deploy.sh로 맞춘다."
fi
exit $failed
