import os
import threading
from typing import Optional

import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForDepthEstimation

DEPTH_MODEL_ID = os.getenv("DEPTH_MODEL_ID", "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf")
# 3.2: Dockerfile이 이 revision을 빌드 단계에서 캐시에 구워 넣고 HF_HUB_OFFLINE=1로 잠근다.
# 기본값을 commit SHA로 두는 이유는, 태그(main)로 두면 같은 코드가 시점에 따라 다른 가중치를
# 쓰게 되어 5.6이 요구하는 재현성이 깨지기 때문이다.
DEPTH_MODEL_REVISION = os.getenv("DEPTH_MODEL_REVISION", "8078d68a9c75a972131914f6afd0c1723be0da7f")


class DepthModel:
    """2.1/3.2: Depth Anything V2 Metric Indoor Small. 범용 LLM/LMM이 아닌
    indoor metric depth estimation 전용 체크포인트만 사용한다."""

    def __init__(self, model_id: str = DEPTH_MODEL_ID, revision: str = DEPTH_MODEL_REVISION):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.dtype = torch.float16 if self.device == "cuda" else torch.float32

        self.processor = AutoImageProcessor.from_pretrained(model_id, revision=revision)
        self.model = (
            AutoModelForDepthEstimation.from_pretrained(model_id, revision=revision, torch_dtype=self.dtype)
            .to(self.device)
            .eval()
        )
        self.model_id = model_id
        self.revision = revision

    @torch.inference_mode()
    def predict_metric_depth(self, image: Image.Image) -> np.ndarray:
        """반환값: 입력 이미지와 동일 해상도의 metric z-depth map(단위: meter).
        Depth Anything V2 Metric 계열 체크포인트는 z-depth를 직접 출력한다."""
        inputs = self.processor(images=image, return_tensors="pt")
        inputs = {k: v.to(self.device, self.dtype) if v.is_floating_point() else v.to(self.device) for k, v in inputs.items()}
        outputs = self.model(**inputs)

        post_processed = self.processor.post_process_depth_estimation(
            outputs, target_sizes=[(image.height, image.width)]
        )
        depth = post_processed[0]["predicted_depth"]
        return depth.to(torch.float32).cpu().numpy()


_model_lock = threading.Lock()
_model_instance: Optional[DepthModel] = None


def get_depth_model() -> DepthModel:
    """5.4: 컨테이너 시작 시 1회 로드하고 전역 재사용한다."""
    global _model_instance
    if _model_instance is None:
        with _model_lock:
            if _model_instance is None:
                _model_instance = DepthModel()
    return _model_instance
