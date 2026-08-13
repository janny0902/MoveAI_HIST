# 09 — 운영 · 환경 · Docker

---

## 1. 필수 환경변수 (`.env`)

```env
VITE_KAKAO_JS_KEY=
KAKAO_REST_KEY=
GCP_PROJECT_ID=moveai-504907
GCP_LOCATION=us-central1
VERTEX_ENDPOINT_ID=
```

템플릿: `.env.example`

| 변수 | 사용처 |
|------|--------|
| VITE_KAKAO_JS_KEY | frontend build ARG |
| KAKAO_REST_KEY | spring env |
| GCP_* / VERTEX_* | backend-ai |
| GOOGLE_APPLICATION_CREDENTIALS | AI 컨테이너 마운트 (compose) |

---

## 2. Compose 기동

```bash
docker compose -p moveai-mvp up -d --build
# 접속 http://localhost:20100
# GCP: http://EXTERNAL_IP:20100
```

### 호스트 포트 (2만번대)

| 서비스 | 호스트 | 컨테이너 내부 |
|--------|--------|----------------|
| nginx (앱 진입) | **20100** | 80 |
| backend-spring | **20800** | 8080 |
| backend-ai | **28000** | 8000 |
| PostgreSQL | **25432** | 5432 |

컨테이너 간 호출은 서비스명+내부 포트 유지 (`db:5432`, `backend-ai:8000`).

의존 순서: db healthy → db-import 완료 → spring/ai start.

체적 CSV 없으면 import가 그룹을 못 채울 수 있음 → `Volumetric data/` 확인.

---

## 3. 헬스

```bash
curl http://localhost:20100/ai/health
curl http://localhost:20100/api/health
```

---

## 4. 카카오 콘솔

- Web 도메인: `http://localhost:20100`, `http://127.0.0.1:20100`, GCP 시 `http://EXTERNAL_IP:20100`
- JS 키 / REST 키 구분

---

## 5. GCP VM 메모

- 방화벽 **tcp:20100** (필요 시 `20800`, `28000`, `25432`도 개방)
- **http://EXTERNAL_IP:20100** 로 접속 (HTTPS 미사용)
- Linux ADC 경로가 Windows `%APPDATA%`와 다름 → compose volume 수정
- 대용량 CSV는 scp

nginx가 **Welcome to nginx!** 만 보이면 `default.conf` 마운트가 안 된 것:

```bash
docker compose -p moveai-mvp up -d --force-recreate nginx
docker compose -p moveai-mvp exec nginx head -20 /etc/nginx/conf.d/default.conf
# proxy_pass http://frontend 가 보여야 함
```

---

## 6. AI 이미지 빌드 주의

- torch CPU wheel 분리 설치 (시간·용량)
- 첫 추론 시 HF/MiDaS 다운로드 가능 → timeout 여유
- `YOLO_CONFIG_DIR`, `TORCH_HUB_DIR`, `HF_HOME` = `/tmp/...`

---

## 7. 프로젝트 접두어

컨테이너명 `mvp-moveai-*`, compose project `moveai-mvp` — 기존 서비스와 포트·네트워크 격리.

---


## 8. 배포 경로

배포 방식이 **둘**이다. 헷갈리면 고쳐 놓고 반영 안 된 채 시연하게 된다.

| 고친 곳 | 방식 | 반영 |
|---------|------|------|
| `frontend/` | compose | `:20100/` |
| `frontend-admin/` | compose | `:20100/admin/` |
| `backend-spring/` | compose | `:20100/api` |
| `backend-ai/` | compose | `:20100/ai` |
| `nginx/default.conf` | compose(restart) | :20100 |
| `vision-processor/` | **Cloud Run** | 인터넷 |
| `matching-processor/` | **Cloud Run** | 인터넷 |
| `tools/` | 없음 | 로컬 실행 |

vision/matching도 Dockerfile로 돌지만 compose에는 없다. `gcloud run deploy --source .`가
소스를 올리면 Cloud Build가 그 Dockerfile로 빌드해 Cloud Run에 배포한다.

---

### 8.1 Compose

```bash
docker compose up -d --build frontend-admin   # 고친 서비스만
docker compose restart nginx                  # conf만 고쳤으면 빌드 불필요
docker compose logs -f frontend-admin
```

`frontend-admin`은 백엔드 주소를 빌드에 굽지 않는다. 주소만 바뀌면 `.env`의 `ADMIN_*` 수정
후 `up -d`로 컨테이너만 재생성.

---

### 8.2 Cloud Run

`moveai-504903` 권한 필요.

리소스 값의 **단일 출처는 각 서비스의 `infra/config.sh`**다. 아래 명령의 숫자는 그 파일을
그대로 옮겨 적은 것이다 — 한쪽만 고치지 말 것.

```bash
cd matching-processor
gcloud run deploy matching-processor --source . \
  --region asia-northeast3 --project moveai-504903 \
  --service-account matching-sa@moveai-504903.iam.gserviceaccount.com \
  --allow-unauthenticated --memory 8Gi --cpu 8 --concurrency 80 --timeout 900s \
  --min-instances 1
```

```bash
cd vision-processor
gcloud run deploy vision-processor --source . \
  --region asia-northeast3 --project moveai-504903 \
  --service-account vision-sa@moveai-504903.iam.gserviceaccount.com \
  --allow-unauthenticated --memory 8Gi --cpu 4 --concurrency 1 --timeout 300s \
  --min-instances 1
```

**`--min-instances`를 빼지 말 것.** 빼면 에러 없이 0으로 되돌아가고, 인스턴스가 마지막
요청 15분 뒤 죽어 다음 첫 클릭이 콜드 스타트를 문다. 실제로 이렇게 어긋나 있었다
(2026-08-11에 1로 복구). 같은 이유로 `--memory`/`--cpu`/`--concurrency`도 매번 붙여야 한다 —
생략한 값은 유지되는 게 아니라 **기본값으로 리셋된다.**

시연이 끝나면 `--min-instances 0`으로 되돌린다. 8Gi 인스턴스 두 개를 상시 켜두는 비용이다.

**`infra/deploy.sh`는 쓰지 말 것.** `--set-env-vars`로 환경변수 전체를 넘긴다.
`infra/.env.local`(gitignore)이 없는 PC에서 돌리면 `KAKAO_REST_API_KEY`가 빈 값으로 덮여
우회시간이 조용히 직선거리 추정으로 떨어진다. 위처럼 `--set-env-vars` 없이 부르면 기존
환경변수가 유지된다.

환경변수 하나만 바꿀 때:

```bash
gcloud run services update matching-processor \
  --region asia-northeast3 --project moveai-504903 \
  --update-env-vars 'SOLVER_TIME_LIMIT_S=120'
```

빌드 시간: vision 10~15분(모델 가중치), matching 2~3분.

---

### 8.3 확인

```bash
curl http://localhost:20100/
curl -I http://localhost:20100/admin/
curl http://localhost:20100/ai/health

curl https://vision-processor-xi6ooeq3ta-du.a.run.app/v1/trucks/T-000004
curl -X POST -d '{}' -H 'Content-Type: application/json' \
  'https://matching-processor-xi6ooeq3ta-du.a.run.app/v1/trucks/T-000004/match?candidates=2000&palletized=true'
```

화면 주소가 바뀌면 Cloud Run의 `CORS_ALLOW_ORIGINS`도 바꾼다 →
[11-admin-integration.md](11-admin-integration.md) 4절.
