import base64
import os
from dataclasses import dataclass
from typing import List, Optional

import google.auth
import google.auth.transport.requests
import requests

# 2.1 고정 query. Model Garden owlvit 서빙 컨테이너는 프롬프트 템플릿에 민감해서
# 맨 단어("cargo", "pallet")로는 실제 트럭 사진에서 탐지가 0건이었고,
# "a photo of a X" 형태에서만 박스가 나왔다. 라벨 매핑을 위해 원본 단어를 함께 들고 있는다.
BASE_QUERIES = [
    "cargo",
    "freight",
    "cardboard box",
    "pallet",
    "bag",
    "sack",
    "crate",
    "drum",
    "wrapped package",
    "roll",
]
QUERY_TEMPLATE = "a photo of a {}"
FIXED_QUERIES = [QUERY_TEMPLATE.format(q) for q in BASE_QUERIES]
_QUERY_TO_BASE = {QUERY_TEMPLATE.format(q): q for q in BASE_QUERIES}

# 실측 score 분포가 0.10~0.23 구간이라 0.15로 자르면 대부분 버려진다.
OWLVIT_MIN_SCORE = float(os.getenv("OWLVIT_MIN_SCORE", "0.10"))


@dataclass
class OwlBox:
    label: str
    score: float
    xmin: float
    ymin: float
    xmax: float
    ymax: float


class OwlVitTimeoutError(Exception):
    pass


class OwlVitClient:
    """3.1: Vertex AI Model Garden OWL-ViT Endpoint 클라이언트.
    2D bounding box + score만 반환하며 CBM 계산은 포함하지 않는다(V4 Geometry Lite의 책임).

    Model Garden `deploy`가 만드는 Endpoint는 dedicated endpoint라 전용 DNS로 호출해야 한다.
    google-cloud-aiplatform SDK 버전에 따라 dedicated 호출 인자가 달라서, 버전 차이로
    조용히 실패하지 않도록 REST를 직접 호출한다.
    """

    def __init__(self, project: str, location: str, endpoint_id: str = "", dedicated_dns: str = ""):
        self.project = project
        self.location = location
        self.endpoint_id = endpoint_id or os.getenv("OWLVIT_ENDPOINT_ID", "")
        self.dedicated_dns = dedicated_dns or os.getenv("OWLVIT_DEDICATED_DNS", "")
        self._credentials = None

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint_id)

    def _predict_url(self) -> str:
        path = (
            f"v1/projects/{self.project}/locations/{self.location}"
            f"/endpoints/{self.endpoint_id}:predict"
        )
        host = self.dedicated_dns or f"{self.location}-aiplatform.googleapis.com"
        return f"https://{host}/{path}"

    def _token(self) -> str:
        if self._credentials is None:
            self._credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        if not self._credentials.valid:
            self._credentials.refresh(google.auth.transport.requests.Request())
        return self._credentials.token

    def detect(
        self,
        image_bytes: bytes,
        image_width: int,
        image_height: int,
        timeout_s: float = 8.0,
        min_score: float = OWLVIT_MIN_SCORE,
    ) -> List[OwlBox]:
        """실측한 Endpoint 계약:
          요청  {"instances":[{"image": "<base64 JPEG>", "texts": [...]}]}
          응답  {"predictions":[{"box":{"xmin","ymin","xmax","ymax"},"label","score"}, ...]}

        box는 정규화 좌표가 아니라 **요청에 실어 보낸 이미지의 절대 픽셀** 좌표다.
        호출자는 전처리로 축소한 이미지를 넘기므로 반환 좌표가 곧 depth map 좌표계와 같고,
        따로 스케일을 곱하면 안 된다(image_width/height는 클리핑에만 쓴다).
        """
        if not self.enabled:
            return []

        payload = {
            "instances": [
                {
                    "image": base64.b64encode(image_bytes).decode("utf-8"),
                    "texts": FIXED_QUERIES,
                }
            ]
        }

        try:
            resp = requests.post(
                self._predict_url(),
                json=payload,
                headers={"Authorization": f"Bearer {self._token()}"},
                timeout=timeout_s,
            )
            if resp.status_code != 200:
                raise OwlVitTimeoutError(f"{resp.status_code} {resp.text[:300]}")
            predictions = resp.json().get("predictions", [])
        except OwlVitTimeoutError:
            raise
        except Exception as exc:  # noqa: BLE001 - 5.8: 상위에서 geometry-only로 degrade
            raise OwlVitTimeoutError(str(exc)) from exc

        results: List[OwlBox] = []
        for p in predictions:
            score = float(p.get("score", 0.0))
            if score < min_score:
                continue
            box = p.get("box") or {}
            try:
                xmin, ymin = float(box["xmin"]), float(box["ymin"])
                xmax, ymax = float(box["xmax"]), float(box["ymax"])
            except (KeyError, TypeError, ValueError):
                continue
            label = _QUERY_TO_BASE.get(p.get("label", ""), p.get("label", ""))
            results.append(
                OwlBox(
                    label=label,
                    score=score,
                    xmin=max(0.0, min(xmin, image_width)),
                    ymin=max(0.0, min(ymin, image_height)),
                    xmax=max(0.0, min(xmax, image_width)),
                    ymax=max(0.0, min(ymax, image_height)),
                )
            )
        return results
