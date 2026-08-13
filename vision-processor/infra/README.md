# vision-processor 인프라

Cloud Run 리소스 설정과 IAM 권한을 스크립트로 고정한다. `gcloud run deploy`를 손으로 치면
`--memory` / `--concurrency`가 빠져 기본값(4Gi, 동시성 80)으로 되돌아가고 컨테이너가 OOM으로
죽는다. 배포는 항상 `deploy.sh`로 한다.

| 파일 | 역할 |
|---|---|
| `config.sh` | 모든 설정값의 단일 출처. 나머지 스크립트가 source한다 |
| `bootstrap.sh` | API·서비스 계정·IAM·버킷·토픽·Eventarc 트리거 생성 (멱등) |
| `deploy.sh` | Cloud Run 배포. 리소스 설정 고정 |
| `verify.sh` | 실제 상태가 `config.sh`와 맞는지 검사 (읽기 전용, 불일치 시 exit 1) |

## 실행 환경

bash 스크립트다. Windows에서는 Git Bash로 실행한다. Cloud SDK의 `bin/gcloud` 셸 래퍼가
Python을 못 찾고 깨지는 환경이 있어 `config.sh`가 동작하는 실행 파일(`gcloud` 또는
`gcloud.cmd`)을 자동으로 고른다. `GCLOUD` 환경변수로 직접 지정할 수도 있다.

## 처음 세팅

```bash
./infra/bootstrap.sh   # 트리거는 서비스가 없어 건너뛴다
./infra/deploy.sh
./infra/bootstrap.sh   # 이제 트리거까지 생성
./infra/verify.sh
```

## 이후 배포

```bash
./infra/deploy.sh
```

## 설정을 바꿀 때

`config.sh`만 고치고 `deploy.sh`를 다시 돌린다. 일회성으로 덮어쓰려면 환경변수를 쓴다:

```bash
MEMORY=16Gi ./infra/deploy.sh
```

## 왜 이 값인가

- **`MEMORY=8Gi`** — 4Gi에서 `Memory limit of 4096 MiB exceeded with 4109 MiB used`로 컨테이너가
  종료됐다. torch + transformers(Depth-Anything V2) + open3d가 동시에 상주한다.
- **`CONCURRENCY=1`** — 기본값 80이면 Eventarc 재시도가 한 인스턴스에 몰려 위 메모리 한도를
  곧바로 넘긴다. 이미지 1장당 인스턴스 1개로 묶는다.
- **런타임 SA 자기 자신에 대한 `roles/iam.serviceAccountTokenCreator`** — V4 signed URL은 서명 키가
  필요한데 메타데이터 서버 ADC에는 개인키가 없다. `storage_client._signing_client()`가 IAM
  signBlob으로 대신 서명하려면 이 권한이 있어야 한다. GCS 읽기/쓰기는 impersonation 없이
  ADC를 그대로 쓰므로 이 권한과 무관하다.
- **GCS 서비스 에이전트의 `roles/pubsub.publisher`** — GCS → Eventarc는 서비스 에이전트가
  Pub/Sub에 publish해서 동작한다. 없으면 트리거는 만들어지지만 이벤트가 오지 않는다.

## 알려진 미완 사항

- `OWLVIT_ENDPOINT_ID`가 비어 있어 OWL-ViT 탐지가 비활성이다. `owl_coverage_ratio=0`이 되어
  품질점수에서 가중치 0.10을 통째로 잃고, 결과가 `LIMITED`/`REJECTED` 경계(0.50)에서 흔들린다.
  Vertex Endpoint를 배포한 뒤 `config.sh`의 `ENV_VARS`에 추가한다.
- Depth 모델 가중치가 이미지에 포함돼 있지 않아 콜드 스타트마다 HuggingFace에서 받아온다.
  `Dockerfile`에서 미리 받아 굽는 편이 낫다.
