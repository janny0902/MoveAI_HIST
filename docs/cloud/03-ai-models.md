# 03. AI 모델 계약과 제약

여기 적힌 요청/응답 형태는 **문서를 보고 쓴 것이 아니라 배포된 Endpoint를 직접 때려서 확인한 것**이다.
초기 구현은 표준 Vertex predict 스키마를 가정했다가 세 군데가 전부 틀렸다.

> **현재 관리자 화면은 이 문서의 모델을 쓰지 않는다.** 적재된 화물을 0으로 보기로 하면서
> 사진에서 빈 공간을 추정할 이유가 사라졌고, 그 경로(OWL-ViT + Depth-Anything V2 +
> 포인트클라우드)를 화면 흐름에서 걷어냈다. Endpoint와 코드는 그대로 살아 있다 —
> 이미 실린 화물이 있는 차를 재려면 그때 다시 필요하다.
>
> 지금 흐름에서 **판단을 맡기는 단계는 CP-SAT 조합 최적화 하나**다
> ([MAT-04](05-matching-processor.md#mat-04-cp-sat-모델),
> [MAT-15](05-matching-processor.md#mat-15-후보-상한을-요청이-정한다--솔버가-실패하면-그리디로-떨어진다)).
> 나머지는 산수(치수→부피)이거나 규칙 기반 추정(박스타입→중량)이다. 화면의 XAI 카드가
> 단계마다 그 구분을 라벨로 붙인다 — 단순 곱셈까지 AI라고 부르면 정작 판단을 맡긴 부분이
> 묻히고, 결과가 틀렸을 때 무엇을 의심해야 할지 알 수 없게 된다.

---

### MODEL-01 jax-owl-vit-v2는 배포 경로가 없다

설계서 3.1이 지정한 `publishers/google/models/jax-owl-vit-v2`(b16, ST/FT_ens)는 현재 배포할 수 없다.

- `gcloud ai model-garden models deploy`가 지원하지 않는다: `Model does not support deployment`.
  `list-deployment-config`도 같은 오류를 낸다.
- 공식 노트북(설계서 참고자료 2번)은 `gs://scenic-bucket/owl_vit/checkpoints`의 사전 변환 TF
  SavedModel을 받아 자기 버킷에 다시 올리는 방식인데, **이 버킷이 비공개다.**
  익명 접근 401, 인증 접근 403.
- 노트북 기준 서빙 머신이 `n1-highmem-64`(64 vCPU / 416GB)라 8시간 MVP의 비용 전제와도 맞지 않는다.

**대응** 같은 Model Garden의 `google/owlvit-base-patch32@owlvit-base-patch32`로 대체했다.
"Model Garden 모델 필수" 요구는 그대로 만족한다. 다만 모델 계열이 OWL-ViT v2 → v1 base-patch32로
내려가므로 **탐지 성능을 설계서 가정보다 낮게 잡아야 한다.**

**상태** 우회함. `jax-owl-vit-v2`가 다시 배포 가능해지면 재검토

---

### MODEL-02 배포 사양

| 항목 | 값 |
|---|---|
| 모델 | `google/owlvit-base-patch32@owlvit-base-patch32` |
| 머신 | `g2-standard-8` + NVIDIA L4 x1 |
| 컨테이너 | `pytorch-inference.cu125.0-4.ubuntu2204.py310` |
| replica | 1 |
| Endpoint 종류 | **dedicated** |

```bash
gcloud ai model-garden models deploy \
  --model=google/owlvit-base-patch32@owlvit-base-patch32 \
  --region=asia-northeast3 --project="$PROJECT_ID" \
  --machine-type=g2-standard-8 \
  --accelerator-type=NVIDIA_L4 --accelerator-count=1 \
  --endpoint-display-name=owlvit-endpoint --accept-eula --asynchronous
```

---

### MODEL-03 요청 스키마

```json
{"instances": [{"image": "<base64 JPEG>", "texts": ["a photo of a cargo", "..."]}]}
```

초기 구현이 틀렸던 점:

| 항목 | 잘못된 가정 | 실제 |
|---|---|---|
| 질의 필드명 | `text_queries` | `texts` |
| 이미지 형태 | `{"bytesBase64Encoded": "..."}` | base64 문자열 그대로 |
| 질의 구조 | 중첩 리스트 허용 | **평면 리스트만.** 중첩하면 422 |

`texts`가 아니면 422와 함께 `"loc": ["body","instances",0,"texts"], "msg": "Field required"`가 온다.
이 오류 메시지가 정확한 필드명을 알려주므로, 스키마를 모를 때 일부러 틀리게 보내 확인하면 된다.

---

### MODEL-04 응답 스키마 — 좌표는 절대 픽셀이다

```json
{"predictions": [
  {"box": {"xmin": 753, "ymin": 918, "xmax": 1050, "ymax": 1070},
   "label": "a photo of a box", "score": 0.1946}
]}
```

| 항목 | 잘못된 가정 | 실제 |
|---|---|---|
| 구조 | `{boxes[], scores[], labels[]}` 병렬 배열 | **객체의 평면 리스트** |
| 좌표계 | 정규화 0-1 | **요청에 실어 보낸 이미지의 절대 픽셀** |

**가장 위험했던 부분이다.** 초기 코드는 정규화 좌표로 가정하고 `xmin * image_width`를 곱하고 있었다.
그대로 붙였다면 박스가 완전히 어긋난 채 조용히 돌면서 CBM만 틀리게 나왔을 것이다.

전처리로 축소한 이미지를 보내므로 반환 좌표가 곧 depth map 좌표계와 같다. **스케일을 곱하지 않는다.**
`image_width`/`image_height`는 클리핑에만 쓴다.

---

### MODEL-05 프롬프트 템플릿이 없으면 탐지가 0건이다

실차 사진으로 확인한 결과:

| 질의 | 결과 |
|---|---|
| `cargo`, `freight`, `cardboard box`, `pallet`, ... (맨 단어 10종) | **0건** |
| `a photo of a box` | 6건 |
| `a photo of a door` | 2건 |
| `a photo of a floor` | 1건 |

서빙 컨테이너가 프롬프트 형태에 민감하다. `a photo of a {단어}` 템플릿을 씌워 보내고,
응답 `label`은 템플릿이 붙은 문자열로 오므로 기본 단어로 되돌려 기록한다.

**적용 위치** `vision-processor/model_clients/owlvit_client.py`의 `QUERY_TEMPLATE`

---

### MODEL-06 score 임계값 0.15는 너무 높다

실측 score 분포가 **0.10-0.23** 구간이다. 설계서가 정한 0.15로 자르면 탐지 대부분이 버려진다.

`OWLVIT_MIN_SCORE` 기본값을 0.10으로 낮췄다. 실차 데이터가 쌓이면 다시 조정할 값이다.

---

### MODEL-07 dedicated Endpoint는 전용 DNS로 호출해야 한다

Model Garden `deploy`가 만드는 Endpoint는 `dedicatedEndpointEnabled: true`다.

```
https://<endpoint-id>.<region>-<project-number>.prediction.vertexai.goog/v1/<resource>:predict
```

`google-cloud-aiplatform` SDK는 버전에 따라 dedicated 호출 인자가 다르다. 버전 차이로
**조용히 실패하면 geometry-only로 degrade해도 눈치채지 못하므로**, SDK 대신 `google.auth` +
`requests`로 REST를 직접 호출한다.

```bash
gcloud ai endpoints describe <ID> --region=<REGION> \
  --format='value(dedicatedEndpointEnabled,dedicatedEndpointDns)'
```

**적용 위치** `vision-processor/model_clients/owlvit_client.py`, `config.py`의 `OWLVIT_DEDICATED_DNS`

---

### MODEL-08 Depth 가중치를 이미지에 굽고 revision을 SHA로 고정한다

- **문제** 설계서 3.2는 "가중치를 이미지에 포함하고 요청 시 HF에서 다운로드하지 않는다"인데, 실제로는 콜드 스타트마다 HuggingFace에서 받고 있었다. revision도 `main` 태그라 같은 코드가 시점에 따라 다른 가중치를 쓸 수 있었다(설계서 5.6 재현성 위반).
- **대응**
  - Dockerfile 빌드 단계에서 `AutoImageProcessor`/`AutoModelForDepthEstimation`를 미리 받아 굽는다.
  - revision을 commit SHA로 고정: `8078d68a9c75a972131914f6afd0c1723be0da7f`
  - `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`로 런타임 다운로드를 차단한다. 캐시에 없는 것을 받으려 하면 즉시 실패하므로 **가중치 누락이 조용히 넘어가지 않는다.**
- **부작용** 빌드 시간이 늘어난다([ENV-11](01-environment.md#env-11-vision-이미지-빌드가-15분-걸린다)).
- **적용 위치** `vision-processor/Dockerfile`, `model_clients/depth_model.py`, `config.py`

---

### MODEL-09 Depth는 z-depth를 출력한다

Depth Anything V2 Metric 계열은 ray distance가 아니라 **z-depth**를 낸다.
unprojection 식이 달라지므로 `depth_to_camera_points(depth_type="z_depth")`로 명시 고정한다.
체크포인트를 바꾸면 이 가정을 반드시 재확인한다.

**적용 위치** `vision-processor/geometry_lite/point_cloud.py`

---

### MODEL-10 품질점수 가중치를 9개 항목으로 재배분했다

설계서 4.10이 나열한 8개 항목 중 `depth outlier 비율`이 빠져 있었다. 추가하면서 합이 1.0이
되도록 전체를 재배분했다.

| 항목 | 가중치 |
|---|---|
| blur | 0.13 |
| exposure | 0.05 |
| intrinsics 신뢰도 | 0.13 |
| 구조 평면 수 | 0.13 |
| RANSAC residual | 0.13 |
| W/H 정합(scale) | 0.09 |
| **depth outlier** | **0.10** |
| 관측 voxel 비율 | 0.14 |
| OWL coverage | 0.10 |

**주의** 기존 항목 가중치가 내려갔으므로 **같은 사진의 quality_score가 이전과 달라진다.**
ACCEPT 0.70 / LIMITED 0.50 임계값은 실차 데이터로 다시 봐야 한다.

depth outlier 비율은 세 가지를 합쳐 센다.
1. 비유효값(NaN/inf/0 이하)
2. 물리적 범위 밖: 화물칸 대각선의 2배 초과(문 밖 배경)
3. 통계적 이상치: median에서 MAD 3 스케일 초과. 표준편차 대신 MAD를 쓰는 이유는 depth map 자체가
   이미 오염됐을 수 있어 표준편차가 이상치에 끌려가기 때문이다.

**적용 위치** `vision-processor/geometry_lite/point_cloud.py`, `pipeline.py`

---

### 실측 참고값

같은 사진으로 측정한 값이다. 회귀를 감지하는 기준선으로 쓴다.

| 조건 | quality_score |
|---|---|
| OWL-ViT 없음(geometry-only), 기본 화각 | 0.499 |
| OWL-ViT 연결, 기본 화각 | 0.548 |
| OWL-ViT 연결 + depth outlier 항목 추가 | 0.526 |
| 위 + PWA가 보낸 EXIF intrinsics | **0.628** |

- OWL-ViT를 붙이면 `owl_coverage_ratio`가 살아나 약 +0.05
- EXIF intrinsics가 있으면 신뢰도가 0.2(기본 화각) → 0.95로 올라 약 +0.10
- 탐지 박스 수: 이 사진 기준 8개
- 단계별 latency: 모델 추론 약 1.0초, geometry 약 60-104초(**geometry가 지배적이다**)
