import json

from google.cloud import pubsub_v1

import config
from schemas import SpaceGeometryReadyEvent

_publisher: pubsub_v1.PublisherClient = None


def _get_publisher() -> pubsub_v1.PublisherClient:
    global _publisher
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def publish_space_geometry_ready(event: SpaceGeometryReadyEvent) -> str:
    """2.2 통신 계약: 원본 이미지/OWL box 전체/depth map/point cloud는 싣지 않고
    CBM/품질 요약만 space-geometry-ready 토픽으로 발행한다."""
    publisher = _get_publisher()
    topic_path = publisher.topic_path(config.PROJECT_ID, config.SPACE_GEOMETRY_TOPIC)
    payload = event.model_dump(by_alias=True, mode="json")
    data = json.dumps(payload).encode("utf-8")
    future = publisher.publish(topic_path, data=data, event_id=event.event_id, truck_id=event.truck_id)
    return future.result(timeout=10)