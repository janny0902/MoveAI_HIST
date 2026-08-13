import json
from datetime import timedelta
from functools import lru_cache
from typing import Optional

import google.auth
from google.auth.impersonated_credentials import Credentials as ImpersonatedCredentials
from google.cloud import storage

import config


@lru_cache(maxsize=1)
def _client() -> storage.Client:
    """Cloud Run 리비전이 이미 vision-sa로 실행되므로 ADC를 그대로 쓴다.
    자기 자신을 impersonate하면 GCS 호출마다 IAM 토큰 교환이 끼어들고,
    읽기/쓰기가 iam.serviceAccounts.getAccessToken 권한에 불필요하게 묶인다."""
    return storage.Client(project=config.PROJECT_ID)


@lru_cache(maxsize=1)
def _signing_client() -> storage.Client:
    """V4 signed URL만 서명 키가 필요하다. 메타데이터 서버 ADC에는 개인키가 없으므로
    IAM signBlob으로 대신 서명해 주는 impersonated credentials를 쓴다.
    (vision-sa가 자기 자신에 대해 roles/iam.serviceAccountTokenCreator를 가져야 한다.)"""
    source_creds, _ = google.auth.default()
    impersonated_creds = ImpersonatedCredentials(
        source_credentials=source_creds,
        target_principal=config.SA_EMAIL,
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return storage.Client(credentials=impersonated_creds, project=config.PROJECT_ID)


def generate_upload_url(blob_name: str, content_type: str, bucket_name: str = config.BUCKET_NAME) -> str:
    bucket = _signing_client().bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=15),
        method="PUT",
        content_type=content_type,
    )


def _parse_gcs_uri(uri: str) -> tuple:
    assert uri.startswith("gs://"), f"invalid GCS uri: {uri}"
    bucket_name, _, blob_name = uri[len("gs://") :].partition("/")
    return bucket_name, blob_name


def download_bytes(object_uri: str) -> bytes:
    bucket_name, blob_name = _parse_gcs_uri(object_uri)
    return _client().bucket(bucket_name).blob(blob_name).download_as_bytes()


def upload_json(bucket_name: str, blob_name: str, payload: dict) -> str:
    blob = _client().bucket(bucket_name).blob(blob_name)
    blob.upload_from_string(json.dumps(payload), content_type="application/json")
    return f"gs://{bucket_name}/{blob_name}"


def download_json(bucket_name: str, blob_name: str) -> Optional[dict]:
    blob = _client().bucket(bucket_name).blob(blob_name)
    if not blob.exists():
        return None
    return json.loads(blob.download_as_bytes())