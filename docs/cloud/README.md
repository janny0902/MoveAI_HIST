# 제약사항 · 인프라 문서

이 디렉터리와 소스만 있으면 **빈 GCP 프로젝트에서 동일한 환경을 다시 만들 수 있도록** 쓴 문서다.
설계 의도는 [Markdown.md](../Markdown.md)에 있고, 여기에는 설계서만 봐서는 알 수 없는 것 —
실제로 부딪힌 제약, 값의 근거, 순서 의존성 — 을 모은다.

## 처음 세팅하는 경우

[00-new-project-setup.md](00-new-project-setup.md)를 위에서부터 그대로 따라 하면 된다.
순서가 중요하다(트리거는 서비스가 있어야 만들 수 있고, 색인은 빌드에 시간이 걸린다).

## 문서 목록

| 문서 | 다루는 범위 | 주로 볼 사람 |
|---|---|---|
| [00-new-project-setup.md](00-new-project-setup.md) | 빈 프로젝트에서 전체 재현하는 순차 런북 | 최초 구축 |
| [01-environment.md](01-environment.md) | Windows/Git Bash, gcloud CLI, Node/Python 툴체인 | 저장소에서 작업하는 모두 |
| [02-gcp-infra.md](02-gcp-infra.md) | Cloud Run 리소스, IAM, Eventarc, Pub/Sub, GCS | 인프라 |
| [03-ai-models.md](03-ai-models.md) | OWL-ViT Endpoint 실측 계약, Depth 모델 고정 | AI/백엔드 |
| [04-vision-processor.md](04-vision-processor.md) | Vision 파이프라인 구현 제약 | 백엔드 |
| [05-matching-processor.md](05-matching-processor.md) | Matching 파이프라인 구현 제약 | 백엔드 |
| [06-frontend.md](06-frontend.md) | 프론트엔드 배포·연동 제약 | 프론트엔드 |
| [07-operations.md](07-operations.md) | 배포 순서, 비용, 시연 전후 체크리스트 | 운영 |
| [08-open-issues.md](08-open-issues.md) | 아직 해결되지 않은 것 | 모두 |
| [09-data-model.md](09-data-model.md) | Firestore 컬렉션·필드 스펙과 시드 방법 | 백엔드/데이터 |

UI를 Stitch / AI Studio로 재생성할 때는 [frontend/UI_CONTRACT.md](../frontend/UI_CONTRACT.md)를
프롬프트에 붙여 넣는다. 그 문서는 생성 도구에 먹이는 용도라 여기와 별도로 관리한다.

## 항목 형식

각 제약에는 ID가 붙어 있다. 커밋 메시지나 이슈에서 `ENV-03`처럼 참조한다.

```
### ENV-01 제목
- **증상**     무엇이 어떻게 실패하는가
- **원인**     왜 그런가
- **대응**     무엇을 했는가
- **적용 위치** 코드/설정 경로
- **상태**     적용됨 | 미해결 | 보류 | 해소됨
```

## 관리 방법

- 새 제약을 만나면 해당 문서에 항목을 추가하고 ID를 이어서 붙인다.
- 제약이 해소되면 항목을 지우지 말고 **상태를 `해소됨`으로 바꾸고 언제·무엇으로 풀렸는지 남긴다.**
  같은 함정을 다시 밟지 않으려면 왜 그렇게 짜여 있는지가 남아 있어야 한다.
- [08-open-issues.md](08-open-issues.md)는 다른 문서의 `미해결` 항목을 모아 보는 곳이다.
  내용을 복제하지 말고 링크한다.
- 설계 자체가 바뀌면 여기가 아니라 [Markdown.md](../Markdown.md)를 고친다.
  이 문서들은 "설계대로 만들려는데 현실이 이랬다"를 담는다.
