"""Image storage, abstracted behind an interface (spec F8 / R1a).

Images are only persisted when the user consents to training use. S3 in
production (same AWS account as SES); local disk for dev. Swappable like the
email sender.
"""
from __future__ import annotations

import abc
import os
import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class ImageStorage(abc.ABC):
    """Backend-agnostic image store interface (S3 or local disk)."""

    @abc.abstractmethod
    def put(self, user_id: str, data: bytes, content_type: str = "image/jpeg") -> str:
        """Persist one image; return an opaque storage key."""

    @abc.abstractmethod
    def delete(self, key: str) -> None:
        """Delete by key (supports F8 account/data deletion)."""


class S3ImageStorage(ImageStorage):
    """Production backend: S3 with server-side encryption, keyed per user."""

    def __init__(self, bucket: str, region: str, prefix: str = "captures/"):
        self._bucket = bucket
        self._prefix = prefix
        self._client = boto3.client("s3", region_name=region)

    def put(self, user_id: str, data: bytes, content_type: str = "image/jpeg") -> str:
        key = f"{self._prefix}{user_id}/{uuid.uuid4()}.jpg"
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data,
                ContentType=content_type, ServerSideEncryption="AES256",  # F8: encryption at rest
            )
        except (BotoCoreError, ClientError) as exc:  # pragma: no cover - network path
            raise RuntimeError(f"S3 put failed: {exc}") from exc
        return key

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:  # pragma: no cover
            raise RuntimeError(f"S3 delete failed: {exc}") from exc


class LocalImageStorage(ImageStorage):
    """Writes under a local directory. Dev only."""

    def __init__(self, root: str):
        self._root = root
        os.makedirs(root, exist_ok=True)

    def put(self, user_id: str, data: bytes, content_type: str = "image/jpeg") -> str:
        user_dir = os.path.join(self._root, user_id)
        os.makedirs(user_dir, exist_ok=True)
        key = os.path.join(user_id, f"{uuid.uuid4()}.jpg")
        with open(os.path.join(self._root, key), "wb") as fh:
            fh.write(data)
        return key

    def delete(self, key: str) -> None:
        path = os.path.join(self._root, key)
        if os.path.exists(path):
            os.remove(path)


_storage: ImageStorage | None = None


def build_image_storage(settings) -> ImageStorage:
    """Build (once) and return the storage backend selected by settings."""
    global _storage
    if _storage is None:
        if settings.image_storage_backend == "s3":
            _storage = S3ImageStorage(settings.s3_bucket, settings.aws_region)
        else:
            _storage = LocalImageStorage(settings.local_image_dir)
    return _storage
