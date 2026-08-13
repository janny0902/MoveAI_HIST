# UI 재생성 계약

Stitch / AI Studio로 화면을 새로 만들 때 이 문서를 그대로 프롬프트에 붙여 넣는다.
여기에 적힌 경계만 지키면 UI를 몇 번을 갈아엎어도 백엔드 파이프라인은 깨지지 않는다.

## 절대 재생성하지 말 것 — `src/lib/`

| 파일 | 이유 |
|---|---|
| `lib/exif.js` | 리사이즈하면 EXIF가 사라진다. 반드시 축소 **전** 원본 바이트에서 읽어야 한다 |
| `lib/image.js` | focal length를 리사이즈 배율로 보정한다. 이 한 줄이 빠지면 depth 추정이 배율만큼 어긋나고 CBM이 통째로 틀어진다 |
| `lib/api.js` | 백엔드 계약(엔드포인트·필드명). 서버와 1:1로 맞춰져 있다 |
| `lib/useAnalysis.js` | 촬영→업로드→폴링 순서와 실패 처리 |
| `lib/truck.js` | 차량 제원 조회. 등록 제원이 곧 측정의 자다 |
| `lib/location.js` | 현재 위치 추적 + 역지오코딩. 화면에 보인 좌표가 그대로 분석에 쓰인다 |
| `lib/kakaoMap.js` | 카카오 지도 SDK 로더(선택 기능) |
| `lib/explain.js` | 결과 설명(XAI) 문장 생성. **여기서 CBM을 다시 계산하지 말 것** — 화면과 저장값이 갈라진다 |
| `lib/waybill.js` | 운송장 등록 계약. 입력 항목이 체적 측정기 CSV 17컬럼과 1:1이다 |
| `lib/cargo.js` | 좌표·중량을 이미 아는 자체 포맷 등록 경로 |

UI에서 `fetch`를 직접 부르지 않는다. 반드시 `lib/`의 함수를 통한다.

**체적·중량을 화면에서 계산하지 않는다.** 운송장 등록 폼은 치수(mm)와 작업터미널만 보내고,
체적·추정중량·상차좌표는 서버가 만든다. 규칙을 화면에도 두면 서버와 어긋날 때 조용히 다른
값이 저장된다.

## 자유롭게 바꿔도 되는 것 — `src/ui/`, `src/App.jsx`, `src/styles.css`

레이아웃, 컴포넌트 분리 방식, CSS 프레임워크(Tailwind 등) 도입 모두 자유.

**단, 색·타이포·모서리·그림자는 기사 화면(`frontend/src/App.vue`)과 맞춰 둔 것이다.**
`styles.css`의 `:root` 토큰이 App.vue의 `:root`를 그대로 옮긴 값이고, 두 화면을 오가는
사람에게 한 제품으로 보여야 해서 맞췄다. 바꾸려면 양쪽을 같이 바꾼다.

| 토큰 | 값 | 쓰는 곳 |
| --- | --- | --- |
| `--kakao-yellow` | `#ffcd00` | 원색 노랑. 아래 `--accent`의 실체 |
| `--kakao-black` | `#3c3c3c` | 본문 글자 |
| `--kakao-bg` | `#f2f2f2` | 페이지 배경 |
| `--accent` | = 노랑 | **면**으로 보이는 강조 — 카드 테두리, 버튼, 막대, 점, 탭 밑줄 |
| `--accent-ink` | `#856800` | **글자**로 보이는 강조 — 숫자, 링크, 얇은 선 |

기사 화면에는 `--kakao-blue`(`#2f80ed`)가 강조색으로 있지만 **관리자 화면은 파랑을 쓰지
않는다.** 강조색을 노랑 하나로 통일했다.

### 강조색이 토큰 둘로 갈린 이유

`#ffcd00`은 흰 배경 대비가 **1.50:1**이다. 접근성 기준(본문 4.5:1)의 3분의 1이라 글자로
쓰면 사실상 안 읽힌다. 그래서 같은 노랑 계열이면서 대비를 지키는 값을 따로 뒀다 —
`#856800`은 흰 배경 **5.28:1**, 카드 안쪽 회색(`#f2f2f2`) 배경 **4.72:1**로 둘 다 통과한다.

규칙: **칠하면 `--accent`, 읽으면 `--accent-ink`.** 큰 숫자(`.earn-amount`)도 `--accent-ink`를
쓴다 — 같은 숫자가 자리마다 다른 노랑이면 색이 의미를 잃는다.

다크 모드에서는 `--accent-ink`가 원색 노랑으로 돌아간다(어두운 배경 대비 9.56:1).

### CSS 밖에 색이 박힌 곳

토큰을 바꾸면 여기도 같이 고쳐야 한다. CSS 변수가 닿지 않는 자리들이다.

| 파일 | 무엇 | 현재 값 |
| --- | --- | --- |
| `src/ui/LocationCard.jsx` | 카카오맵 경로선 | `#856800` (원색 노랑은 지도 위에서 안 보인다) |
| `public/icon.svg` | PWA 아이콘 | 노랑 바탕 + 검은 트럭 |
| `public/manifest.webmanifest` | `theme_color` | `#ffcd00` |
| `index.html` | `<meta name="theme-color">` | `#ffcd00` |

## 훅 인터페이스

```js
const { analyze, steps, preview, vision, matching, error, busy } = useAnalysis();

analyze(file, truckId)  // 파일을 고르면 이것만 호출하면 된다
busy      // boolean. true면 촬영 버튼을 비활성화한다
preview   // 축소된 이미지의 object URL (없으면 null)
error     // 에러 메시지 문자열 (없으면 null)
steps     // { [stepKey]: "active" | "done" | "fail" }
```

`STEPS`는 `[{ key, label }]` 배열이고 순서가 곧 파이프라인 순서다.
`exif → resize → url → upload → vision → matching`

### 현재 화면이 쓰는 것은 이쪽이다 — `useTruckMatch`

사진 경로는 화면에서 걷어냈다. 적재된 박스를 0으로 보기로 한 이상 실을 수 있는 공간은
등록 적재함 체적 그 자체라, 사진에서 빈 공간을 추정할 이유가 없다. 위 `useAnalysis`와
`ui/CaptureCard.jsx`는 되돌릴 때를 위해 파일만 남겨 뒀고 어디서도 부르지 않는다.

```js
const { matching, busy, error, ranAt, run, reset } = useTruckMatch();

run(truckId, position)  // 버튼을 누르면 이것만 호출한다. 결과가 곧 응답이다(폴링 없음)
reset()                 // 차량을 바꾸면 호출한다. 이전 차 결과를 남기면 안 된다
ranAt                   // Date. 화면의 숫자가 언제 것인지 표시하는 데 쓴다
```

**자동 갱신은 없다.** 주기적으로 다시 돌리면 기사가 화면을 보는 사이에 목록이 바뀌어
방금 판단한 묶음이 사라진다. 갱신 시점은 사람이 정한다.

## 데이터 형태

`vision` (설계서 5.3 / vision-processor 응답):

```json
{
  "photo_id": "P-cb1fd875",
  "truck_id": "T-000001",
  "estimated_free_cbm": 3.664,
  "usable_free_cbm": 2.335,
  "unknown_cbm": 0.342,
  "quality_score": 0.628,
  "quality_status": "ACCEPTED | LIMITED | REJECTED",
  "current_loaded_weight_kg": 460.0,
  "max_payload_kg": 900.0,
  "result_uri": "gs://.../results/P-cb1fd875.json",
  "failure_reason": null,
  "model_versions": { "detector": "...", "depth": "...", "geometry": "..." }
}
```

`matching` (matching-processor 응답, 없으면 `null`):

```json
{
  "can_load": true,
  "remaining_weight_kg": 440.0,
  "selected_cargos": [
    { "cargo_id": "C-037899", "volume_cbm": 1.304, "weight_kg": 380.0, "pickup_order": 1 }
  ],
  "final_free_cbm": 0.564,
  "solver_status": "OPTIMAL",
  "candidate_count": 20,
  "route_source": "ROUTES_API | HAVERSINE_FALLBACK",
  "failure_reason": null,
  "decision_scope": "CBM_WEIGHT_ROUTE_FEASIBILITY"
}
```

필드 이름을 바꾸지 않는다. 서버 응답 그대로다.

## 화면이 반드시 지켜야 할 규칙

설계서에서 나온 제약이라 디자인 취향으로 뺄 수 없다.

1. **기사에게 좌표를 탭시키지 않는다** (2.1). 문틀·벽·화물 경계를 지정하는 UI를 만들지 않는다.
   기사의 행위는 촬영 한 번뿐이다.
2. **추정치를 실측처럼 보이지 않게 한다** (4.11).
   - `quality_status`가 `LIMITED`면 보수적으로 계산했다는 사실을 표시한다.
   - `route_source`가 `HAVERSINE_FALLBACK`이면 우회시간이 직선거리 추정치임을 밝힌다.
3. **가려진 공간이 제외됐다는 것을 알린다** (4.9). `unknown_cbm`을 숨기지 않는다.
4. **`can_load`가 false일 때 이유를 보여준다** (5.8). `failureText(reason)`이 문장을 준다.
5. **정확도를 숫자로 약속하지 않는다** (4.11). "오차 ±20%" 같은 문구를 넣지 않는다.

## 카메라 입력

```html
<!-- 2.1: OS 기본 카메라 -->
<input type="file" accept="image/*" capture="environment" />
<!-- 앨범/파일 선택용 (capture 없음) -->
<input type="file" accept="image/*" />
```

`<label for>`와 `<input id>`에 **같은 값을 쓰지 않는다.** 같으면 `getElementById`가 label을
먼저 돌려줘 이벤트가 input에 붙지 않는다. React에서는 `useRef` + `ref.current.click()`을 쓴다.

## 백엔드 주소

빌드에 굽지 않는다. 컨테이너 시작 시 `window.__APP_CONFIG__`로 주입된다.
`lib/api.js`가 이미 읽고 있으므로 UI는 신경 쓸 필요 없다.
