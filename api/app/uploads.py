from collections import defaultdict, deque
from io import BytesIO
import logging
import time
from typing import BinaryIO
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from .config import Settings

MAX_PROFILE_PICTURE_BYTES = 2 * 1024 * 1024
MAX_PROFILE_PICTURE_UPLOADS_PER_MINUTE = 10
PROFILE_PICTURE_PREFIX = "profile-pictures"
READ_CHUNK_BYTES = 64 * 1024
RATE_LIMIT_WINDOW_SECONDS = 60

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
    "image/webp": (".webp",),
}

IMAGE_SAVE_FORMATS = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}

_upload_attempts: dict[str, deque[float]] = defaultdict(deque)
logger = logging.getLogger(__name__)


def check_profile_picture_rate_limit(user_id: str) -> None:
    now = time.monotonic()
    attempts = _upload_attempts[user_id]
    while attempts and attempts[0] <= now - RATE_LIMIT_WINDOW_SECONDS:
        attempts.popleft()

    if len(attempts) >= MAX_PROFILE_PICTURE_UPLOADS_PER_MINUTE:
        logger.warning("profile_picture_upload_rate_limited user_id=%s", user_id)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many upload attempts")

    attempts.append(now)


async def read_profile_picture_content(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0

    while chunk := await file.read(READ_CHUNK_BYTES):
        total += len(chunk)
        if total > MAX_PROFILE_PICTURE_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload rejected")
        chunks.append(chunk)

    return b"".join(chunks)


def validate_profile_picture(file: UploadFile, content: bytes) -> str:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload rejected")

    if len(content) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload rejected")

    if len(content) > MAX_PROFILE_PICTURE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload rejected")

    detected_type = detect_image_type(content)
    if detected_type is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload rejected")

    filename = file.filename.lower()
    if not filename.endswith(ALLOWED_IMAGE_TYPES[detected_type]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload rejected")

    return detected_type


def sanitize_profile_picture(content: bytes, content_type: str) -> bytes:
    try:
        with Image.open(BytesIO(content)) as image:
            image.load()
            if content_type == "image/jpeg" and image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            output = BytesIO()
            image.save(output, format=IMAGE_SAVE_FORMATS[content_type])
    except (OSError, UnidentifiedImageError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload rejected") from exc

    sanitized = output.getvalue()
    if len(sanitized) > MAX_PROFILE_PICTURE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload rejected")
    return sanitized


def detect_image_type(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def profile_picture_storage_key(user_id: str, content_type: str) -> str:
    extension = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }[content_type]
    return f"{PROFILE_PICTURE_PREFIX}/{user_id}/{uuid4()}.{extension}"


def get_s3_client(settings: Settings):
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def put_upload_object(settings: Settings, storage_key: str, content: bytes, content_type: str) -> None:
    try:
        get_s3_client(settings).put_object(
            Bucket=settings.uploads_bucket,
            Key=storage_key,
            Body=content,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to store upload") from exc


def get_upload_object(settings: Settings, storage_key: str) -> tuple[BinaryIO, str]:
    try:
        response = get_s3_client(settings).get_object(Bucket=settings.uploads_bucket, Key=storage_key)
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile picture not found") from exc

    return response["Body"], response.get("ContentType") or "application/octet-stream"
