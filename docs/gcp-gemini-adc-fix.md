# GCP Gemini ADC 수정 (IsADirectoryError)

## 원인

```
IsADirectoryError: ... '/secrets/adc.json'
# 또는
IsADirectoryError: ... '/credentials/application_default_credentials.json'
```

Windows용 `${APPDATA}/gcloud/...` 마운트가 GCP Linux에선 파일이 없어  
Docker가 **디렉터리**를 만들고, Gemini가 그걸 인증 파일로 읽다 실패함.

## GCP VM에서 즉시 복구

SSH 후 저장소 루트에서:

```bash
cd ~/MoveAI   # 실제 경로로

# 1) .env 에서 ADC 강제 지정 제거 (있으면)
# GOOGLE_APPLICATION_CREDENTIALS=...  ← 주석/삭제
# GOOGLE_ADC_HOST=...                 ← 주석/삭제

# 2) 최신 compose/코드 pull 후 AI만 재기동
git pull
docker compose -p moveai-mvp up -d --build --force-recreate --no-deps backend-ai

# 3) 예전에 잘못 생긴 디렉터리 마운트 잔여 정리(필요 시)
docker compose -p moveai-mvp exec backend-ai sh -c \
  'ls -la /secrets /credentials 2>/dev/null; echo CRED=$GOOGLE_APPLICATION_CREDENTIALS'

# 4) 헬스: adc는 metadata 모드, vertex connected
curl -s http://127.0.0.1:8000/ai/health
```

GCE VM 서비스 계정에 Vertex 권한이 있어야 함:

```bash
# VM에 연결된 SA에 예:
# roles/aiplatform.user
```

## 다음 에러: `ACCESS_TOKEN_SCOPE_INSUFFICIENT` (403)

ADC 디렉터리 문제를 넘기면 흔히 이어서 나옴:

```
PermissionDenied: 403 Request had insufficient authentication scopes.
reason: ACCESS_TOKEN_SCOPE_INSUFFICIENT
service: aiplatform.googleapis.com
```

**의미:** IAM 역할이 있어도, GCE VM **액세스 스코프**가 좁으면 Vertex 토큰에 `aiplatform` 권한이 안 실림.  
코드/앱 버그가 아니라 **VM 설정** 문제.

### 수정 (둘 다 필요)

**A. VM 액세스 스코프** (이게 403의 원인인 경우가 많음)

```bash
# VM 이름/존 확인 후
gcloud compute instances stop INSTANCE --zone=ZONE
gcloud compute instances set-service-account INSTANCE --zone=ZONE \
  --scopes=https://www.googleapis.com/auth/cloud-platform
gcloud compute instances start INSTANCE --zone=ZONE
```

또는 Console → VM → 수정 → **Cloud API에 대한 전체 액세스 허용** → 저장 후 재시작.

**B. 서비스 계정 IAM**

```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:SA_EMAIL" \
  --role="roles/aiplatform.user"
```

그다음 `docker compose ... up -d backend-ai` 재기동 후 `/ai/health` 확인.

## 확인

앱에서 `fill_30pct.png` 업로드 → 로그에  
`gemini-2.5-flash-vision` / `Depth/YOLO 생략` / `IsADirectory`·`SCOPE_INSUFFICIENT` 없음.
