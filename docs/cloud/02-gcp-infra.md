# 02. GCP 인프라 제약과 설정 근거

값을 바꾸기 전에 여기서 왜 그 값인지 먼저 확인한다. 대부분 장애를 겪고 정한 값이다.

## 리소스 전체 목록

새 프로젝트에 만들어야 하는 것 전부다. 생성은 `*/infra/bootstrap.sh`가 담당한다.

| 종류 | 이름 | 만드는 곳 |
|---|---|---|
| Cloud Run | `vision-processor` | `vision-processor/infra/deploy.sh` |
| Cloud Run | `matching-processor` | `matching-processor/infra/deploy.sh` |
| Cloud Run | `frontend` | `frontend/infra/deploy.sh` |
| Service Account | `vision-sa` | `vision-processor/infra/bootstrap.sh` |
| Service Account | `matching-sa` | `matching-processor/infra/bootstrap.sh` |
| Service Account | `frontend-sa` | `frontend/infra/deploy.sh` |
| GCS 버킷 | `truck-vision-{PROJECT_ID}` | `vision-processor/infra/bootstrap.sh` |
| Pub/Sub 토픽 | `space-geometry-ready` | `vision-processor/infra/bootstrap.sh` |
| Pub/Sub 구독 | `space-geometry-ready-matching` | `matching-processor/infra/bootstrap.sh` |
| Eventarc 트리거 | `vision-gcs-trigger` | `vision-processor/infra/bootstrap.sh` |
| Firestore 복합색인 | `pending_cargos(status, pickup_lat, pickup_lng)` | `matching-processor/infra/bootstrap.sh` |
| Vertex Endpoint | `owlvit-endpoint` | 수동([00번 문서](00-new-project-setup.md#4-vertex-ai-owl-vit-endpoint)) |

## IAM 요약

| 주체 | 역할 | 왜 |
|---|---|---|
| `vision-sa` | `storage.objectAdmin` | 원본 읽기, 결과 JSON 쓰기 |
| `vision-sa` | `datastore.user` | Firestore 읽기/쓰기 |
| `vision-sa` | `pubsub.publisher` | `space-geometry-ready` 발행 |
| `vision-sa` | `aiplatform.user` | OWL-ViT Endpoint 호출 |
| `vision-sa` | `iam.serviceAccountTokenCreator` (자기 자신) | signed URL 서명([GCP-06](#gcp-06-signed-url-발급에-자기-자신에-대한-tokencreator가-필요하다)) |
| `matching-sa` | `datastore.user` **만** | storage 권한을 의도적으로 뺐다([GCP-16](#gcp-16-matching-sa에-storage-권한을-주지-않는다)) |
| `frontend-sa` | **없음** | 정적 서빙만 한다([GCP-17](#gcp-17-frontend-sa에-아무-역할도-주지-않는다)) |
| GCS 서비스 에이전트 | `pubsub.publisher` | GCS→Eventarc 경로([GCP-08](#gcp-08-gcs-서비스-에이전트에-pubsubpublisher가-필요하다)) |
| Compute 기본 SA | `eventarc.eventReceiver`, `run.invoker` | 트리거/푸시 전달 |

---

### GCP-01 Cloud Run 메모리 4Gi로는 Vision이 죽는다

- **증상** `Memory limit of 4096 MiB exceeded with 4109 MiB used`. 컨테이너가 종료되고 Eventarc가 재시도한다.
- **원인** torch + transformers(Depth-Anything V2) + open3d가 한 프로세스에 상주한다.
- **대응** `MEMORY=8Gi`, `CPU=4`.
- **적용 위치** `vision-processor/infra/config.sh`
- **상태** 적용됨. **`gcloud run deploy`를 손으로 치지 말 것** — 플래그가 빠져 4Gi 기본값으로 되돌아간다

---

### GCP-02 기본 동시성 80이 OOM을 증폭시킨다

- **증상** 재시도 이벤트가 몰리면 인스턴스 하나가 여러 이미지를 동시에 처리하다 메모리 한도를 넘긴다.
- **원인** Cloud Run 기본 `--concurrency=80`. 이미지 1장당 수 GB를 쓰는 워크로드에 맞지 않는다.
- **대응** `CONCURRENCY=1`. 이미지 1장당 인스턴스 1개로 묶는다.
- **적용 위치** `vision-processor/infra/config.sh`
- **상태** 적용됨

---

### GCP-03 시연 중에는 min-instances=1

- **근거** 설계서 5.4. 콜드 스타트에 모델 로드가 들어가 수십 초가 걸린다.
- **대응** `MIN_INSTANCES=1`. **상시 과금되므로 시연이 끝나면 되돌린다**: `MIN_INSTANCES=0 ./infra/deploy.sh`
- **적용 위치** `vision-processor/infra/config.sh`, `verify.sh`가 드리프트를 잡는다
- **상태** 적용됨

---

### GCP-04 버킷 lifecycle 7일

- **근거** 설계서 5.1. 시연 사진을 무기한 쌓아 두지 않는다.
- **대응** `BUCKET_LIFECYCLE_DAYS=7`, `Delete` 규칙.
- **주의** 원본과 결과 JSON이 같은 버킷에 있어 **둘 다 7일 뒤 삭제된다.** 결과를 오래 남기려면 버킷을 분리한다(`RESULTS_BUCKET_NAME`이 이미 분리 가능하게 돼 있다).
- **적용 위치** `vision-processor/infra/bootstrap.sh`
- **상태** 적용됨

---

### GCP-05 브라우저 업로드에 버킷 CORS가 필요하다

- **증상** 열지 않으면 preflight에서 막혀 업로드가 통째로 실패한다.
- **원인** 프론트가 Signed URL로 GCS에 직접 PUT한다(설계서 2.2).
- **대응** 버킷 CORS에 `PUT/GET/HEAD`, `Content-Type` 허용. 현재 origin은 `*`이며, 운영에서는 프론트 도메인으로 좁히는 편이 낫다.
- **적용 위치** `vision-processor/infra/bootstrap.sh`
- **상태** 적용됨

---

### GCP-06 signed URL 발급에 자기 자신에 대한 tokenCreator가 필요하다

- **증상** `Permission 'iam.serviceAccounts.getAccessToken' denied` → GCS 다운로드가 통째로 실패.
- **원인** 초기 `storage_client`가 ADC로 `vision-sa`를 **자기 자신에게 impersonate** 하고 있었다. Cloud Run이 이미 그 SA로 실행 중인데도 매 호출마다 IAM 토큰 교환이 끼어들었다.
- **대응** 두 가지를 함께 했다.
  1. 일반 GCS 읽기/쓰기는 impersonation을 제거하고 ADC를 직접 쓴다(클라이언트도 캐싱).
  2. **서명 키가 실제로 필요한 signed URL 발급에만** impersonated credentials를 남기고, `vision-sa`에 자기 자신에 대한 `roles/iam.serviceAccountTokenCreator`를 부여한다. 메타데이터 서버 ADC에는 개인키가 없어 IAM signBlob으로 대신 서명해야 한다.
- **적용 위치** `vision-processor/storage_client.py`, `infra/bootstrap.sh`
- **상태** 적용됨

---

### GCP-07 새 프로젝트의 런타임 SA에는 권한이 거의 없다

- **증상** Firestore 403, Pub/Sub 발행 실패가 순차적으로 터진다.
- **원인** `vision-sa`에 `storage.objectAdmin` 하나만 있었다.
- **대응** `datastore.user`, `pubsub.publisher`, `aiplatform.user`를 추가. `aiplatform.user`는 OWL-ViT를 붙이기 전에는 증상이 없다가 Endpoint 연결 순간 403이 난다.
- **적용 위치** `vision-processor/infra/bootstrap.sh`, `verify.sh`
- **상태** 적용됨

---

### GCP-08 GCS 서비스 에이전트에 pubsub.publisher가 필요하다

- **원인** GCS→Eventarc는 Cloud Storage 서비스 에이전트가 Pub/Sub에 publish해서 동작한다.
- **증상** 없으면 트리거는 만들어지지만 **이벤트가 오지 않는다.** 조용히 아무 일도 안 일어나서 원인 찾기가 어렵다.
- **대응** `gcloud storage service-agent`로 얻은 계정에 `roles/pubsub.publisher` 부여.
- **적용 위치** `vision-processor/infra/bootstrap.sh`
- **상태** 적용됨

---

### GCP-09 Eventarc 페이로드 형태를 예단하면 안 된다

- **증상** 트리거 설정/전송 경로에 따라 GCS 객체 정보가 본문 최상위, `data`, `message.data`(base64), `message.attributes`, CloudEvent 헤더 중 어디에나 실려 온다.
- **대응** 계층을 재귀 순회하며 `bucket`/`name` 후보를 모으고, 못 찾으면 CloudEvent 헤더로 폴백한다. **어떤 예외가 나도 HTTP 200을 반환**해 무한 재시도를 만들지 않는다.
- **적용 위치** `vision-processor/main.py`의 `_collect_gcs_hints`, `_extract_gcs_event`
- **상태** 적용됨

---

### GCP-10 Model Garden 배포에 Cloud Quotas API가 필요하다

- **증상** `gcloud ai model-garden models deploy`가 쿼터 확인 단계에서 대화형 프롬프트(`Would you like to enable and retry?`)를 띄우고, 비대화형 환경에서는 그대로 실패한다.
- **대응** `cloudquotas.googleapis.com`을 미리 활성화한다.
- **적용 위치** [00-new-project-setup.md](00-new-project-setup.md#2-api-활성화)
- **상태** 적용됨

---

### GCP-11 L4 배포가 INTERNAL로 즉시 실패할 수 있다

- **증상** 배포 operation이 0.4초 만에 `code: 13 INTERNAL`로 끝난다. 엔드포인트는 만들어지지 않는다.
- **확인** `CustomModelServingL4GPUsPerProjectPerRegion` 쿼터는 `asia-northeast3`에 1로 존재했다. 쿼터 부족은 아니었다.
- **대응** 재시도. 두 번째 시도에서 정상 배포됐다. 리전 용량이나 일시적 내부 오류로 보인다.
- **참고** 쿼터가 1이라 같은 리전에 L4 Endpoint를 두 개 동시에 띄울 수 없다.
- **상태** 대응책 기록. 근본 원인 미확인

---

### GCP-12 gcloud model-garden deploy가 지원하는 모델은 일부다

- **증상** `jax-owl-vit-v2`에 대해 `Model does not support deployment`.
- **대응** [03-ai-models.md](03-ai-models.md#model-01-jax-owl-vit-v2는-배포-경로가-없다) 참조.
- **상태** 우회함

---

### GCP-13 Firestore 다중 부등호는 복합색인이 필요하고 빌드에 시간이 걸린다

- **증상** 색인 없이 쿼리하면 `FAILED_PRECONDITION`. 생성 요청 후에도 `CREATING` 동안 계속 실패한다.
- **원인** `status ==` + `pickup_lat` 범위 + `pickup_lng` 범위를 함께 건다. 부등호가 걸리는 모든 필드가 색인에 있어야 한다.
- **대응** `(status, pickup_lat, pickup_lng)` 복합색인 생성. 애플리케이션은 `FAILED_PRECONDITION`을 잡아 **신규 추천을 중단**한다(10만 건 전수 조회로 넘어가지 않는다).
- **소요** 10만 건 기준 수 분.
- **적용 위치** `matching-processor/infra/bootstrap.sh`, `firestore_client.py`
- **상태** 적용됨

---

### GCP-14 Firestore timestamp는 문자열이 아니라 datetime으로 온다

- **증상** `pydantic_core.ValidationError: string_type` → `/v1/match`가 500.
- **원인** `ready_at`/`deadline_at`이 Firestore `timestampValue`라 클라이언트가 `DatetimeWithNanoseconds`를 돌려준다. 스키마는 `str`로 선언돼 있었다.
- **대응** `Optional[datetime]`으로 선언해 ISO 문자열과 datetime을 모두 받고, naive 값은 UTC로 간주한다.
- **적용 위치** `matching-processor/schemas.py`, `main.py`
- **상태** 적용됨

---

### GCP-15 Pub/Sub 구독이 없으면 이벤트는 조용히 버려진다

- **증상** Vision이 정상 발행하는데 Matching이 아무것도 받지 못한다. 에러도 없다.
- **원인** `space-geometry-ready` 토픽에 구독이 하나도 없었다.
- **대응** push 구독 `space-geometry-ready-matching`을 만든다. push SA에 `run.invoker`가 필요하다. ack deadline은 120초(Matching 처리 시간 여유).
- **적용 위치** `matching-processor/infra/bootstrap.sh`
- **상태** 적용됨

---

### GCP-16 matching-sa에 storage 권한을 주지 않는다

- **근거** 설계서 1.3/5.9 "Matching은 이미지와 depth map을 읽지 않는다".
- **대응** `datastore.user`만 부여한다. 문서상의 약속이 아니라 **IAM으로 강제**한다. 실수로 이미지를 읽는 코드가 들어가도 런타임에 막힌다.
- **적용 위치** `matching-processor/infra/bootstrap.sh`
- **상태** 적용됨. 의도적 설계이므로 편의를 위해 권한을 추가하지 말 것

---

### GCP-18 Cloud Run 서비스에는 접속 가능한 URL이 두 개다

- **증상** CORS를 설정했는데도 브라우저에서 `Failed to fetch`가 난다. preflight 로그를 봐도 허용 목록에 값이 들어가 있다.
- **원인** Cloud Run은 한 서비스에 두 주소를 준다. **둘 다 정상 동작한다.**

```
https://<svc>-<hash>.<region>.run.app              ← status.url이 돌려주는 값
https://<svc>-<project-number>.<region>.run.app    ← 콘솔에서 흔히 복사하는 값
```

`status.url`로 얻은 하나만 허용하면, 사용자가 다른 주소로 접속했을 때 Origin이 달라 막힌다.

- **대응** 두 형식을 모두 CORS 허용 목록에 넣는다. `infra/config.sh`가 `status.url`과
  `https://frontend-${PROJECT_NUMBER}.${REGION}.run.app`를 조합한다.
- **적용 위치** `vision-processor/infra/config.sh`, `matching-processor/infra/config.sh`
- **상태** 적용됨

---

### GCP-19 코드를 커밋해도 배포하지 않으면 반영되지 않는다

당연한 말이지만 실제로 겪었다. CORS 미들웨어를 추가한 커밋 이후 vision을 재배포하지 않아,
운영 리비전에는 그 코드가 없었다. 프론트에는 `Failed to fetch`만 보이고 서버 로그에는
아무것도 남지 않는다(preflight가 앱에 닿지 못하므로).

**확인 방법** 배포된 코드가 최신인지 의심되면 라우트 목록을 본다.

```bash
curl -s https://<service-url>/openapi.json | grep -o '"/[a-z0-9/{}._-]*"' | sort -u
```

새로 추가한 엔드포인트가 없으면 그 리비전은 옛 코드다.

**상태** 배포 습관. Vision 빌드가 15분이라 "나중에 한 번에" 미루기 쉬운 것이 원인이었다

---

### GCP-17 frontend-sa에 아무 역할도 주지 않는다

- **근거** 정적 파일만 서빙한다. GCP 리소스에 닿을 이유가 없다.
- **효과** 프론트 컨테이너가 뚫려도 백엔드 데이터에 접근하지 못한다.
- **적용 위치** `frontend/infra/deploy.sh`
- **상태** 적용됨
