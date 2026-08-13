FROM python:3.11-slim
WORKDIR /app

# Open3D의 네이티브 렌더링/GUI 의존 공유 라이브러리(headless 컨테이너에도 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libx11-6 libxext6 libsm6 libxrender1 libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3.2/5.4: Depth 가중치를 이미지에 굽는다. revision은 commit SHA로 고정한다(5.6 기록 대상).
# 태그(main)로 두면 같은 이미지가 시점에 따라 다른 가중치를 받아 재현성이 깨진다.
ARG DEPTH_MODEL_ID=depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf
ARG DEPTH_MODEL_REVISION=8078d68a9c75a972131914f6afd0c1723be0da7f
ENV DEPTH_MODEL_ID=${DEPTH_MODEL_ID}
ENV DEPTH_MODEL_REVISION=${DEPTH_MODEL_REVISION}
ENV HF_HOME=/opt/hf
RUN python -c "\
import os;\
from transformers import AutoImageProcessor, AutoModelForDepthEstimation;\
mid=os.environ['DEPTH_MODEL_ID']; rev=os.environ['DEPTH_MODEL_REVISION'];\
AutoImageProcessor.from_pretrained(mid, revision=rev);\
AutoModelForDepthEstimation.from_pretrained(mid, revision=rev);\
print('baked', mid, rev)"

# 3.2: "요청 시 Hugging Face에서 다운로드하지 않는다"를 런타임에서 강제한다.
# 캐시에 없는 것을 받으려 하면 즉시 실패하므로, 가중치 누락이 조용히 넘어가지 않는다.
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
