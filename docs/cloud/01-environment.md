# 01. 개발 환경 · 툴체인 제약

Windows + Git Bash 조합에서 나온 것이 대부분이다. Linux/macOS에서는 대부분 해당 없지만,
그 환경에서도 깨지지 않도록 대응해 두었으므로 코드를 되돌리지 말 것.

---

### ENV-01 Windows Git Bash에서 gcloud 셸 래퍼가 깨진다

- **증상** Git Bash에서 `gcloud`를 부르면 `Python`만 출력하고 exit 49로 종료한다. 어떤 하위 명령도 실행되지 않는다.
- **원인** Cloud SDK의 `bin/gcloud`(POSIX 셸 래퍼)가 이 환경에서 Python 인터프리터를 찾지 못한다. `gcloud.cmd`는 정상 동작한다.
- **대응** 각 `infra/config.sh`가 동작하는 실행 파일을 자동 선택해 `$GCLOUD`로 노출한다. Linux/macOS에서는 그냥 `gcloud`가 잡힌다. `GCLOUD` 환경변수로 강제 지정도 가능하다.

```bash
if gcloud version >/dev/null 2>&1; then GCLOUD=gcloud
elif gcloud.cmd version >/dev/null 2>&1; then GCLOUD=gcloud.cmd
else echo "gcloud를 찾을 수 없다" >&2; exit 1; fi
```

- **적용 위치** `vision-processor/infra/config.sh`, `matching-processor/infra/config.sh`, `frontend/infra/config.sh`
- **상태** 적용됨

---

### ENV-02 gcloud.cmd는 인자 안의 중첩 따옴표에서 깨진다

- **증상** `'C:\Users\...\Google\Cloud' is not recognized as an internal or external command` 같은 cmd.exe 오류. gcloud가 아예 실행되지 않는다.
- **원인** `gcloud.cmd`는 cmd.exe를 거친다. `--format='value[separator="|"](...)'`처럼 따옴표가 중첩되면 SDK 설치 경로(`...\Cloud SDK\...`, 공백 포함)에서 인자 파싱이 깨진다.
- **대응** `--format`에 따옴표를 중첩하지 않는다. 기본 탭 구분자만 쓰고 셸에서 나눈다. annotation처럼 따옴표가 필수인 조회는 별도 호출로 분리한다.

```bash
# 나쁨:  --format='value[separator="|"](a,b)'
# 좋음:  --format='value(a,b)'   # 기본 구분자는 탭
```

- **적용 위치** `vision-processor/infra/verify.sh`, `deploy.sh`, `matching-processor/infra/deploy.sh`
- **상태** 적용됨. 이 함정을 두 번 밟았다(리소스 조회, minScale 조회)

---

### ENV-03 gcloud.cmd는 공백이 들어간 인자에서도 깨진다

- **증상** 위와 같은 cmd.exe 오류.
- **원인** 같은 이유. `--display-name "matching-processor runtime"`처럼 값에 공백이 있으면 깨진다. `--filter="a:x AND b:y"`의 `AND` 앞뒤 공백도 마찬가지다.
- **대응**
  - `--display-name=matching-processor-runtime`처럼 공백 없는 값에 `=`로 붙여 쓴다.
  - 복합 필터는 쓰지 않는다. 전체를 받아 셸에서 `grep`으로 거른다.
- **적용 위치** `*/infra/bootstrap.sh`의 SA 생성, `vision-processor/infra/verify.sh`의 tokenCreator 확인
- **상태** 적용됨. 이 때문에 존재하는 IAM 바인딩을 "없음"으로 오탐한 적이 있다

---

### ENV-04 Model Garden 조회에 ADC quota project가 필요하다

- **증상** `gcloud ai model-garden models list`가 `SERVICE_DISABLED`로 실패하고, `consumer: projects/32555940559`(gcloud 공용 프로젝트)를 가리킨다.
- **원인** ADC에 quota project가 없으면 aiplatform 호출이 사용자 프로젝트로 귀속되지 않는다.
- **대응**

```bash
gcloud auth application-default set-quota-project "$PROJECT_ID"
gcloud config set billing/quota_project "$PROJECT_ID"
```

`set-quota-project`만으로는 부족했고 `billing/quota_project`까지 설정해야 통과했다.

- **적용 위치** 수동 설정. [00-new-project-setup.md](00-new-project-setup.md#1-프로젝트와-전역-설정)에 포함
- **상태** 적용됨

---

### ENV-05 billing/quota_project 설정의 부작용

- **증상** 위 설정 직후 `gcloud projects get-iam-policy`가 `cloudresourcemanager.googleapis.com` 미활성으로 실패한다. 설정 전에는 잘 되던 명령이다.
- **원인** quota project를 지정하면 Resource Manager 호출도 사용자 프로젝트로 귀속돼, 그 프로젝트에서 API가 켜져 있어야 한다.
- **대응** `cloudresourcemanager.googleapis.com`을 활성화한다. 활성화 후에도 전파에 몇 분 걸린다(쓰기는 먼저 되고 읽기가 나중에 풀린 사례가 있다).
- **적용 위치** `*/infra/bootstrap.sh`의 API 목록
- **상태** 적용됨

---

### ENV-06 로컬에 실행 가능한 Python이 없다

- **증상** `python --version`이 `Python`만 출력하고 exit 49. Windows 스토어 스텁이다.
- **원인** 실제 Python이 설치돼 있지 않다.
- **대응** 백엔드 로직의 로컬 단위 테스트를 못 한다. **검증은 컨테이너 빌드와 실제 배포로 한다.** 문법/임포트 오류는 컨테이너 기동 실패로 드러나므로 배포 자체가 스모크 테스트 역할을 한다.
- **영향** 반복 주기가 느리다. 로직을 바꾸면 배포까지 가야 확인된다. Python 3.11을 설치하면 크게 개선된다.
- **상태** 미해결(환경 문제). Python 설치를 권장한다

---

### ENV-07 Node 16으로는 프론트 로컬 개발이 안 된다

- **증상** 로컬 Node가 16.17.0. Vite 5는 Node 18 이상을 요구한다.
- **대응** 컨테이너는 `node:20-alpine`으로 빌드하므로 **배포에는 문제가 없다.** 로컬에서 `npm run dev`를 쓰려면 Node 18 이상으로 올린다.
- **적용 위치** `frontend/Dockerfile`, `frontend/package.json`의 `engines`
- **상태** 적용됨(배포 기준). 로컬 개발은 Node 업그레이드 필요

---

### ENV-08 .sh가 CRLF로 체크아웃되면 shebang이 깨진다

- **증상** `#!/usr/bin/env bash\r`가 되어 스크립트가 실행되지 않는다.
- **원인** Windows Git의 `core.autocrlf` 기본 동작.
- **대응** `.gitattributes`에 `*.sh text eol=lf`.
- **적용 위치** 저장소 루트 `.gitattributes`
- **상태** 적용됨

---

### ENV-09 gcloud logging read의 --freshness는 --order=asc에서 무시된다

- **증상** `--freshness=10m --order=asc`로 조회했는데 몇 시간 전 로그가 나온다.
- **원인** 오름차순 조회에서는 freshness 창이 적용되지 않고 보존 기간 전체에서 오래된 것부터 반환된다.
- **대응** 최신 로그를 볼 때는 기본 정렬(desc)에 `--freshness`를 쓴다. 시간순으로 보고 싶으면 받아서 셸에서 뒤집는다.
- **상태** 적용됨(조회 습관)

---

### ENV-10 파이프를 거치면 배포 진행 상황이 보이지 않는다

- **증상** 백그라운드로 돌린 배포의 출력 파일이 계속 비어 있어 "실행되지 않았다"고 오판하게 된다.
- **원인** `gcloud ... | tail -8`처럼 파이프를 물리면 출력이 버퍼링돼 명령이 끝나야 한 번에 나온다.
- **대응** 진행 상황을 봐야 하면 파이프를 걸지 않는다. 완료 여부는 출력이 아니라 **리비전 상태를 폴링해서** 판단한다.

```bash
until gcloud run services describe <svc> --region <r> --project <p> \
      --format='value(status.latestReadyRevisionName)' | grep -q <expected>; do sleep 30; done
```

- **상태** 적용됨(조회 습관)

---

### ENV-12 --set-env-vars 값에 쉼표를 넣을 수 없다

- **증상** `gcloud run services update ... --update-env-vars "CORS_ALLOW_ORIGINS=a,b"`가 사용법 오류로 실패한다.
- **원인** gcloud가 쉼표로 **항목**을 구분한다. 값 안의 쉼표는 새 항목의 시작으로 읽힌다.
- **왜 우회했나** gcloud는 `^@^KEY=a,b` 형태로 구분자를 바꿀 수 있지만, `^`는 cmd.exe의 이스케이프 문자라 Windows에서 또 깨진다([ENV-02](#env-02-gcloudcmd는-인자-안의-중첩-따옴표에서-깨진다)). 공백 구분자도 [ENV-03](#env-03-gcloudcmd는-공백이-들어간-인자에서도-깨진다)에 걸린다.
- **대응** 목록형 값은 **세미콜론**으로 구분한다. 쉼표도 아니고 공백도 아니라 양쪽 함정을 피한다. 애플리케이션은 둘 다 받아들인다.

```python
def _parse_origins(raw: str):
    return [o.strip() for o in raw.replace(",", ";").split(";") if o.strip()]
```

- **적용 위치** `vision-processor/main.py`, `matching-processor/main.py`, 각 `infra/config.sh`
- **상태** 적용됨

---

### ENV-13 config.sh에서 변수 정의 순서가 중요하다

- **증상** `CORS_ALLOW_ORIGINS`에 `https://frontend-.asia-northeast3.run.app`처럼 프로젝트 번호가 빠진 값이 들어갔다.
- **원인** `PROJECT_NUMBER`를 파일 아래쪽에서 정의해 두고, 위쪽 CORS 계산에서 참조했다. 셸은 위에서 아래로 실행하므로 그 시점에는 빈 문자열이다.
- **대응** 여러 곳에서 쓰는 값은 파일 상단에서 먼저 구한다.
- **상태** 적용됨. 조용히 잘못된 값이 들어가므로 배포 전 `source infra/config.sh && echo $VALUE`로 확인하는 습관이 필요하다

---

### ENV-11 Vision 이미지 빌드가 15분 걸린다

- **증상** 사소한 수정에도 배포가 15분씩 걸린다.
- **원인** Depth 가중치를 이미지에 굽고([MODEL-08](03-ai-models.md#model-08-depth-가중치를-이미지에-굽고-revision을-sha로-고정한다)) torch/open3d를 설치한다. Cloud Run `--source` 빌드는 레이어 캐시를 재사용하지 않는다.
- **대응** UI를 별도 Cloud Run 서비스로 분리해 프론트 수정이 Vision 빌드를 유발하지 않게 했다(약 2분). 백엔드 빌드 자체를 줄이려면 Artifact Registry에 베이스 이미지를 따로 굽는 방법이 있다.
- **적용 위치** `frontend/`
- **상태** 부분 해소. 백엔드 빌드 시간은 그대로다
