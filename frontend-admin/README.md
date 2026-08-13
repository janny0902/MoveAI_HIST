# frontend (D1 촬영 앱)

React + Vite. `vision-processor` / `matching-processor`와 **별도의 Cloud Run 서비스**로 배포된다.
UI만 고칠 때 Depth 가중치를 굽는 vision 이미지를 다시 빌드하지 않아도 된다.

## 구조

```
src/
  lib/          재생성 금지. 백엔드 계약과 이미지 처리 규칙
    exif.js         원본 EXIF 파싱 (축소 전에 읽어야 한다)
    image.js        1024px 축소 + focal length 보정
    api.js          upload-url / signed URL PUT / 결과 폴링
    useAnalysis.js  전체 흐름을 관리하는 훅
  ui/           교체 가능. Stitch / AI Studio 산출물로 갈아끼운다
  App.jsx       얇은 배선
  styles.css    교체 가능
```

UI를 새로 만들 때는 **[UI_CONTRACT.md](UI_CONTRACT.md)를 프롬프트에 붙여 넣는다.**
지켜야 할 경계와 데이터 형태가 전부 적혀 있다.

## 로컬 개발

Node 18 이상이 필요하다(Vite 5).

```bash
npm install
npm run dev
```

로컬에서는 `window.__APP_CONFIG__`가 없으므로 `public/config.js`를 만들어 둔다
(gitignore 대상):

```js
window.__APP_CONFIG__ = {
  VISION_BASE_URL: "https://vision-processor-....run.app",
  MATCHING_BASE_URL: "https://matching-processor-....run.app"
};
```

## 배포

```bash
./infra/deploy.sh
```

백엔드 주소는 배포된 Cloud Run 서비스에서 자동으로 찾아 `--set-env-vars`로 넘기고,
컨테이너 시작 시 `/config.js`로 써 넣는다. 빌드에 굽지 않으므로 백엔드 주소가 바뀌어도
프론트를 다시 빌드할 필요가 없다.

## 브라우저가 직접 호출하는 곳

이 앱은 서버를 경유하지 않고 세 곳을 직접 호출한다. 각각 CORS가 열려 있어야 한다.

| 대상 | 용도 | CORS 설정 위치 |
|---|---|---|
| vision-processor | upload-url 발급, 분석 결과 조회 | `CORS_ALLOW_ORIGINS` 환경변수 |
| GCS Signed URL | 이미지 직접 업로드 | 버킷 CORS (`vision-processor/infra/bootstrap.sh`) |
| matching-processor | 매칭 결과 조회 | `CORS_ALLOW_ORIGINS` 환경변수 |

프론트 주소가 바뀌면 두 백엔드의 `CORS_ALLOW_ORIGINS`를 갱신해야 한다.

## 서비스 계정

`frontend-sa`에는 아무 IAM 역할도 주지 않는다. 정적 파일만 서빙하므로 GCP 리소스에
접근할 이유가 없고, 권한이 없어야 프론트 컨테이너가 뚫려도 백엔드 데이터에 닿지 못한다.
