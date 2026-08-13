# 11 — 관리자 화면 통합

파일: `frontend-admin/` (React SPA), `nginx/default.conf`, `docker-compose.yml`.

원래 별도 저장소의 Cloud Run 화면을 `/admin`으로 합쳤다.  
역할은 **「이 차에 얼마나 실리나」용량 시뮬**이다. 기사 앱의 위치·20km 복화 배차와는 분리한다.

---

## 1. 논리 구성

```
브라우저 :30100
    → Nginx
         /       → frontend        (Vue3, 기사)
         /admin/ → frontend-admin  (React, 관리자)
         /api    → backend-spring :8080
         /ai     → backend-ai :8000
                     ↓
         PostgreSQL

브라우저 → Cloud Run (moveai-504903)   ※ Nginx 경유 안 함
         → vision-processor / matching-processor → Firestore
```

관리자 화면은 정적 파일이다. 백엔드를 **브라우저가 직접** 호출한다.

compose에 관리자 백엔드가 없는 이유다. 소스는 이 저장소에 있다 — 배포만 Cloud Run으로 나간다.

---

## 2. 디렉터리

| 경로 | 역할 | 배포 |
|------|------|------|
| `frontend/` | Vue, 기사 화면 | compose |
| `frontend-admin/` | React, 관리자 화면 | compose |
| `backend-spring/` | 도메인 API | compose |
| `backend-ai/` | 공간 AI + Gemini | compose |
| `vision-processor/` | 차량 제원·지오코딩 | **Cloud Run** |
| `matching-processor/` | 매칭·운송장 적재 | **Cloud Run** |
| `tools/` | Firestore 데이터 스크립트 | 없음(로컬 실행) |
| `docs/cloud/` | 위 두 서비스 상세 문서 | — |

---

## 3. 두 GCP 프로젝트

| | 기사 | 관리자 |
|---|---|---|
| 프로젝트 | `moveai-504907` | `moveai-504903` |
| 용도 | Vertex AI Gemini (`us-central1`) | Cloud Run ×2, Firestore, GCS |
| DB | PostgreSQL (compose) | Firestore |

프로젝트 단위로 격리된다. 서비스 이름이 같아도 충돌하지 않고, 한쪽이 다른 쪽 데이터를
덮어쓸 수 없다. **합칠 이유 없음.**

로컬에서 겹치는 것 하나: compose가 `%APPDATA%/gcloud/application_default_credentials.json`을
backend-ai에 마운트한다. 관리자 쪽 `gcloud`와 **같은 파일**이다. 로그인 계정에 따라 Gemini
호출이 실패할 수 있다.

---

## 4. CORS

관리자 화면이 브라우저에서 Cloud Run을 직접 부른다. 화면이 뜨는 주소가 그쪽
`CORS_ALLOW_ORIGINS`에 있어야 한다.

등록된 출처:

```
https://frontend-xi6ooeq3ta-du.a.run.app
https://frontend-590544600586.asia-northeast3.run.app
http://localhost:30100
http://127.0.0.1:30100
```

GCP VM에 올리면 `http://EXTERNAL_IP:30100` 추가.

```bash
gcloud run services update matching-processor \
  --region asia-northeast3 --project moveai-504903 \
  --update-env-vars 'CORS_ALLOW_ORIGINS=<기존;목록>;http://EXTERNAL_IP:30100'
# vision-processor 동일
```

구분자는 쉼표가 아니라 **세미콜론**. `gcloud --update-env-vars`가 쉼표로 항목을 나눈다.

빠뜨리면 화면은 뜨는데 데이터가 안 나온다. 콘솔에만 CORS 오류가 남아 원인 찾기 어렵다.

---

## 5. `/admin` 경로 처리

세 곳이 맞물린다. 하나만 틀려도 흰 화면.

**1) Vite base** — `frontend-admin/vite.config.js`

```js
base: "/admin/",
```

없으면 번들이 `/assets/`를 찾아 Vue 쪽으로 떨어진다.

**2) proxy_pass 끝의 슬래시** — `nginx/default.conf`

```nginx
location /admin/ {
    proxy_pass http://frontend-admin:8080/;
}
location = /admin {
    absolute_redirect off;
    return 301 /admin/;
}
```

- 끝의 `/`가 없으면 컨테이너가 `/admin/assets/...`를 받아 404.
- `absolute_redirect off`가 없으면 리다이렉트에서 포트가 빠진다. nginx는 안에서 80을 듣고
  밖으로 30100에 매핑돼 있어 `http://host/admin/`이 되고 브라우저가 80으로 간다.

**3) index.html 상대경로** — `./config.js`, `./icon.svg`

절대경로면 `/admin/` 밖에서 찾는다.

---

## 6. 백엔드 주소 주입

빌드에 굽지 않는다. 컨테이너 시작 시 `docker-entrypoint.d/40-write-config.sh`가 `config.js`를 쓴다.

```yaml
frontend-admin:
  environment:
    - VISION_BASE_URL=${ADMIN_VISION_BASE_URL:-https://vision-processor-xi6ooeq3ta-du.a.run.app}
    - MATCHING_BASE_URL=${ADMIN_MATCHING_BASE_URL:-https://matching-processor-xi6ooeq3ta-du.a.run.app}
    - KAKAO_JS_KEY=${VITE_KAKAO_JS_KEY:-}
```

주소만 바뀌면 `.env`의 `ADMIN_*` 수정 후 컨테이너만 재생성. 이미지 재빌드 불필요.

---

## 7. 줄바꿈(CRLF) 주의

`.gitattributes`로 `*.sh` 등을 LF 고정. Windows 클론 시 git이 CRLF로 바꾸면 리눅스 셸이
줄 끝 `\r`를 명령의 일부로 읽는다.

실제 증상:

```
/import_volumetric.sh: line 4: set: pipefail
: invalid option name
```

`pipefail\r`를 옵션 이름으로 읽은 것. 줄바꿈 문제인 줄 알아채기 어렵다.

---

## 8. 데이터 분리

화면만 합쳤다. 같은 개념이 두 DB에 따로 있고 **동기화되지 않는다.**

| 개념 | 기사 (PostgreSQL) | 관리자 (Firestore) |
|------|-------------------|--------------------|
| 트럭 | `trucks` — `capacity_tons`, `remaining_volume_percent` | `trucks/T-000001` — 적재함 W/L/H(m), `max_payload_kg` |
| 화물 | `volumetric_cargo` — `volume_m3`, `depot_code` | `pending_cargos` — `volume_cbm`, `origin/destination_terminal_code` |
| 배차 | `cargo_requests`, `load_history` | `matching_results` |

- `volume_cbm` = `volume_m3` (같은 값, 다른 이름)
- 트럭은 한쪽이 치수(m), 다른 쪽이 톤수 → 변환 불가
- 관리자 파렛트 계산은 적재함 W/L/H가 필요한데 `trucks` 테이블에 없음

데이터까지 합치려면 이 대응표부터 정해야 한다.

---

## 9. 배포

[09-ops.md](09-ops.md) 8절 참고.

Cloud Run 쪽 상세 제약은 `docs/cloud/`:

| 문서 | 내용 |
|------|------|
| `docs/cloud/05-matching-processor.md` | 차량 기준 매칭, 파렛트, 후보 상한, CP-SAT |
| `docs/cloud/06-frontend.md` | 관리자 화면 컴포넌트·표시 규칙 |
| `docs/cloud/07-operations.md` | 배포 순서·리소스 |
| `docs/cloud/08-open-issues.md` | 미해결 항목 |
| `docs/cloud/09-data-model.md` | Firestore 컬렉션 스펙 |
