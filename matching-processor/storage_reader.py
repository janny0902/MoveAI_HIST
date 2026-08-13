"""운송장 적재 파일만 읽는 GCS 클라이언트.

설계서 1.3/5.9는 "Matching은 이미지와 depth map을 읽지 않는다"이고, 그 경계를 IAM으로
강제한다. 그래서 matching-sa에는 **적재 버킷 하나에 대한 읽기 권한만** 준다.
사진 버킷에는 접근 권한이 없어 이 클라이언트로도 사진을 읽을 수 없다.
"""
from functools import lru_cache

from google.cloud import storage

import config


@lru_cache(maxsize=1)
def _client() -> storage.Client:
    return storage.Client(project=config.PROJECT_ID)


# 운송장 파일은 화주사가 엑셀에서 "CSV(쉼표로 분리)"로 저장해 올린다. 한국어 Windows
# 엑셀의 기본 인코딩은 UTF-8이 아니라 CP949다. UTF-8로만 읽으면 한글 헤더에서
# UnicodeDecodeError가 나 파일 전체가 버려진다. 순서대로 시도한다.
_ENCODINGS = ("utf-8-sig", "cp949", "utf-16")


def decode(raw: bytes) -> str:
    for encoding in _ENCODINGS:
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    # 전부 실패하면 깨진 글자를 치환해서라도 넘긴다. 헤더가 깨지면 뒤에서
    # "컬럼을 알아볼 수 없다"는 사유로 걸러지므로 조용히 잘못 적재되지는 않는다.
    return raw.decode("utf-8", errors="replace")


def download_text(bucket_name: str, blob_name: str) -> str:
    """적재 버킷의 텍스트 파일을 읽는다. 다른 버킷 요청은 거부한다.

    버킷 이름을 검사하는 이유는 IAM 위에 한 겹 더 두기 위해서다. Eventarc 트리거가
    잘못 설정돼 사진 버킷 이벤트가 들어와도 여기서 먼저 막힌다.
    """
    if bucket_name != config.CARGO_INGEST_BUCKET:
        raise PermissionError(
            f"적재 버킷이 아닙니다: {bucket_name} (허용: {config.CARGO_INGEST_BUCKET})"
        )
    blob = _client().bucket(bucket_name).blob(blob_name)
    return decode(blob.download_as_bytes())
