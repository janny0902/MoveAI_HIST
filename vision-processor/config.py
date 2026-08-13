import os

PROJECT_ID = os.getenv("GCP_PROJECT", "moveai-504903")
LOCATION = os.getenv("GCP_LOCATION", "asia-northeast3")

BUCKET_NAME = os.getenv("VISION_BUCKET", f"truck-vision-{PROJECT_ID}")
RESULTS_BUCKET_NAME = os.getenv("VISION_RESULTS_BUCKET", BUCKET_NAME)
SA_EMAIL = os.getenv("VISION_SA_EMAIL", f"vision-sa@{PROJECT_ID}.iam.gserviceaccount.com")

SPACE_GEOMETRY_TOPIC = os.getenv("SPACE_GEOMETRY_TOPIC", "space-geometry-ready")

# ---------------------------------------------------------------------------
# 기본 목적지
# ---------------------------------------------------------------------------
# 기사가 촬영할 때 목적지를 바꾸지 않으면 이 값으로 설정한다.
# Matching M2 경로 회랑은 현재 위치와 목적지가 둘 다 있어야 만들 수 있어서, 목적지가
# 비어 있으면 can_load=false로 끝난다. 기본값을 두어 그 경우를 없앤다.
#
# 위치: 물류산업진흥재단(KLIP), 서울특별시 마포구 마포대로 34
# 좌표는 카카오 Local 키워드 검색이 돌려준 실제 장소 좌표다(도로 근사값이 아니다).
DEFAULT_DESTINATION_ADDRESS = os.getenv(
    "DEFAULT_DESTINATION_ADDRESS", "서울 마포구 마포대로 34 (물류산업진흥재단)"
)
DEFAULT_DESTINATION_LAT = float(os.getenv("DEFAULT_DESTINATION_LAT", "37.5392307181078"))
DEFAULT_DESTINATION_LNG = float(os.getenv("DEFAULT_DESTINATION_LNG", "126.946186411624"))

# 주소 검색용 카카오 REST API 키(developers.kakao.com에서 발급).
# 없으면 검색 엔드포인트가 503을 반환하고, 프론트는 기본 목적지만 쓰도록 degrade한다.
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")

# 버킷 최상단에 바로 올라온 이미지처럼 경로/메타데이터에서 truck_id를 복원할 수 없을 때 사용한다.
# 'photos/{truck_id}/{photo_id}.jpg' 규칙으로 업로드되면 이 값은 쓰이지 않는다.
# Firestore `trucks` 컬렉션의 실제 문서 ID 형식은 'T-000001'(6자리)이다. 여기에 없는 ID를 쓰면
# get_truck_spec()이 None을 반환해 파이프라인이 422로 중단된다.
DEFAULT_TRUCK_ID = os.getenv("DEFAULT_TRUCK_ID", "T-000001")

# 3.1: Model Garden OWL-ViT Endpoint.
# 설계서는 jax-owl-vit-v2(b16, ST/FT_ens)를 지정하지만 그 모델은 현재 배포 경로가 없다:
# gcloud의 model-garden deploy가 지원하지 않고, 공식 노트북이 쓰는 사전 변환 SavedModel
# 버킷(gs://scenic-bucket)이 비공개로 바뀌어 익명 401 / 인증 403이 난다.
# 대신 같은 Model Garden의 owlvit-base-patch32를 Vertex Endpoint로 배포했다.
# 5.6에 따라 실제로 추론한 모델을 그대로 기록한다.
OWLVIT_ENDPOINT_ID = os.getenv("OWLVIT_ENDPOINT_ID", "")
# Model Garden deploy가 만드는 Endpoint는 dedicated endpoint라 전용 DNS로 호출해야 한다.
OWLVIT_DEDICATED_DNS = os.getenv("OWLVIT_DEDICATED_DNS", "")
OWLVIT_DETECTOR_VERSION = os.getenv(
    "OWLVIT_DETECTOR_VERSION", "google/owlvit-base-patch32@owlvit-base-patch32"
)

# 3.2: Vision Cloud Run 이미지에 pinned weights 포함. Dockerfile이 이 revision을 굽는다.
DEPTH_MODEL_REVISION = os.getenv("DEPTH_MODEL_REVISION", "8078d68a9c75a972131914f6afd0c1723be0da7f")
DEPTH_MODEL_VERSION = f"Depth-Anything-V2-Metric-Indoor-Small-hf@{DEPTH_MODEL_REVISION}"

GEOMETRY_LITE_VERSION = "geometry-lite-v1"

# 4.8/4.9
VOXEL_EDGE_M = float(os.getenv("VOXEL_EDGE_M", "0.20"))
SAFETY_FACTOR = float(os.getenv("SAFETY_FACTOR", "0.70"))

# 4.10
QUALITY_ACCEPT_THRESHOLD = 0.70
QUALITY_LIMITED_THRESHOLD = 0.50

# 사진에서 잰 적재함 크기가 등록 제원과 얼마나 어긋나도 되는가. **2단계**로 본다.
#
# build_truck_frame이 내는 scale은 "관측한 상자를 등록 제원에 맞추려면 몇 배 해야 하는가"다.
# Depth 모델이 미터 단위 깊이를 내므로 정상이면 1.0 근처여야 한다.
#
#   WARN 범위 안         정상. 그대로 계산한다.
#   WARN 밖 ~ REJECT 안  계산은 하되 품질을 깎는다. 화물칸이 일부만 보이거나 비스듬히
#                        찍혀 치수 추정이 흔들린 경우가 여기다 - 답을 못 줄 이유는 없고,
#                        대신 LIMITED로 떨어져 추가 안전계수가 붙는다.
#   REJECT 밖            물리적으로 말이 안 되는 값. 숫자를 내지 않는다(설계서 5.8).
#
# **REJECT 범위를 넓게 잡은 이유.** 처음엔 0.6~1.7로 조였다가 실제 사진이 전부 걸렸다.
# 로그를 보니 scale이 매번 1보다 작았고(0.27 / 0.38 / 0.43 / 0.55 / 0.67) 무작위가
# 아니라 일관된 편향이었다.
#
# build_truck_frame은 관측 상자를 **등록 제원에 맞춰 다시 스케일링**하는 함수다. 그래서
# scale은 "초점거리를 얼마나 잘못 가정했는가"의 지표이지 "다른 물체를 쟀는가"의 지표가
# 아니다. EXIF 없는 사진은 초점거리가 기본값이라 1에서 벗어나는 게 정상이고, 스케일링
# 뒤에는 어차피 등록 제원 기준으로 정규화된다. 이 값으로 판정을 끊으면 EXIF 없는 사진을
# 통째로 막게 된다.
#
# 처음 문제였던 "빈 적재함에 유령 화물 4.8CBM"의 원인은 scale이 아니라 OWL이 주변
# 건물·차량을 화물로 잡은 것이었다(owl_coverage 0.44). 그건 이 게이트로 막을 수 없고,
# 남은 과제였고, cargo_points.py의 평면 제외 누락을 고쳐 해결했다.
# RANSAC 평면 검출. 단안 depth로 만든 점군은 스테레오/LiDAR보다 훨씬 거칠어서, 3cm
# 두께로 평면을 찾으면 벽과 바닥이 뻔히 보이는 사진에서도 평면이 하나도 안 잡힌다.
# 실제로 "적재함의 벽과 바닥을 찾지 못했습니다"가 계속 났다. 두께를 넓혀 잡는다.
PLANE_DISTANCE_THRESHOLD_M = float(os.getenv("PLANE_DISTANCE_THRESHOLD_M", "0.08"))
# 전체 점 대비 이 비율보다 작은 평면은 버린다. 낮출수록 작은 면도 주워 담는다.
PLANE_MIN_INLIER_RATIO = float(os.getenv("PLANE_MIN_INLIER_RATIO", "0.02"))
# 바닥 normal과 이 각도 이상 벌어지면 벽으로 본다. 비스듬히 찍으면 90도에서 많이 벗어나
# 70도로는 벽을 놓친다.
PLANE_WALL_ANGLE_DEG = float(os.getenv("PLANE_WALL_ANGLE_DEG", "55"))

SCALE_WARN_MIN = float(os.getenv("SCALE_WARN_MIN", "0.70"))
SCALE_WARN_MAX = float(os.getenv("SCALE_WARN_MAX", "1.50"))
SCALE_MIN = float(os.getenv("SCALE_MIN", "0.15"))
SCALE_MAX = float(os.getenv("SCALE_MAX", "6.0"))
# WARN 구간에서 품질점수에 곱하는 계수. 0.70/0.50 문턱을 감안하면 ACCEPT였던 사진이
# LIMITED로 내려앉는 정도다.
SCALE_WARN_QUALITY_FACTOR = float(os.getenv("SCALE_WARN_QUALITY_FACTOR", "0.75"))
# 그 페널티를 적용할 최소 초점거리 신뢰도. EXIF가 없으면 신뢰도가 0.2라 페널티가 붙지
# 않는다 - 초점거리를 모르면 scale이 어긋나는 게 당연해서 새로운 정보가 아니기 때문이다.
SCALE_PENALTY_MIN_INTRINSICS_CONFIDENCE = float(
    os.getenv("SCALE_PENALTY_MIN_INTRINSICS_CONFIDENCE", "0.5")
)
# OWL 검출 채택 기준.
#
# min score를 0.15로 두니 한 장에서 34개가 잡혔고, 대부분 배경(건물·옆 차·간판)이었다.
# 박스는 2D 사각형이라 배경 검출이 화면을 덮으면 그 안의 적재함 표면까지 화물로 끌어온다.
# 평면 제외 필터를 함께 걸었지만, 애초에 오검출을 줄이는 편이 낫다.
OWL_MIN_SCORE = float(os.getenv("OWL_MIN_SCORE", "0.30"))
# 화면의 이 비율보다 큰 박스는 버린다. 택배 상자 하나가 프레임의 3분의 1을 넘을 수 없다.
OWL_MAX_BOX_AREA_RATIO = float(os.getenv("OWL_MAX_BOX_AREA_RATIO", "0.35"))
