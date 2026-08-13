FROM python:3.10-slim

WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    TMPDIR=/tmp \
    YOLO_CONFIG_DIR=/tmp/Ultralytics \
    TORCH_HUB_DIR=/tmp/torch_hub \
    HF_HOME=/tmp/hf \
    TRANSFORMERS_CACHE=/tmp/hf

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

COPY requirements.txt .

# 레이어 분리 + 즉시 캐시 삭제 → 빌드 피크 디스크 완화
# Depth HF 가중치는 이미지에 굽지 않음(첫 요청 시 /tmp)
# torch/torchvision 동일 CPU 휠. requirements(ultralytics)가 torchvision을 올려도 마지막에 재고정.
RUN pip install --upgrade pip \
 && pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu \
 && rm -rf /root/.cache/pip /tmp/pip-* /tmp/* \
 && pip install -r requirements.txt \
 && pip install --force-reinstall --no-deps torch torchvision --index-url https://download.pytorch.org/whl/cpu \
 && rm -rf /root/.cache/pip /tmp/pip-* /tmp/* \
 && python -c "import torch, torchvision; from torchvision.ops import nms; print(torch.__version__, torchvision.__version__, 'nms-ok')"

COPY . .

# YOLO nano만 (~7MB). torchvision은 ultralytics 의존으로 설치됨
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n-seg.pt')" \
 && rm -rf /root/.cache /tmp/Ultralytics/*.bak 2>/dev/null || true

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
