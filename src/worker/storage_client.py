"""S3 download and upload helpers for worker jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import boto3


class S3StorageClient:
    def __init__(self, s3_client: Optional[object] = None):
        self._client = s3_client or boto3.client("s3")

    def download_file(self, *, bucket: str, key: str, destination_path: Path) -> Path:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(bucket, key, str(destination_path))
        return destination_path

    def upload_file(self, *, source_path: Path, bucket: str, key: str) -> None:
        self._client.upload_file(str(source_path), bucket, key)