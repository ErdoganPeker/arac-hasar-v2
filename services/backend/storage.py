"""
backend/storage.py
S3-uyumlu (AWS S3, Cloudflare R2, MinIO) goruntu storage.

Render production'da harici S3 (AWS / R2) onerilir; dev'de MinIO.
Endpoint URL bos birakilirsa boto3 default AWS endpoint'ini kullanir.

Sundugu API:
  - upload_image(content, key, content_type=None) -> str           (async, public URL)
  - download_image(url_or_key) -> bytes                            (sync)
  - get_image_url(key) -> str                                      (public read URL)
  - get_presigned_url(key, expires_in=None) -> str                 (gecici GET)
  - ensure_bucket()                                                 (startup'ta)
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Optional
from urllib.parse import urlparse

import boto3
import botocore
import requests
from botocore.client import Config

from config import settings


logger = logging.getLogger(__name__)


# ============================ Client ============================

@lru_cache(maxsize=1)
def _client():
    """boto3 S3 client — cached singleton.

    AWS S3 default'larini kullanmak icin S3_ENDPOINT bos birakilabilir.
    """
    endpoint = settings.s3_endpoint or None  # None => boto3 default (AWS)
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
        region_name=settings.s3_region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


@lru_cache(maxsize=1)
def _public_client():
    """Presigned URL'lerin frontend tarafindan erisilebilir host'u icermesi icin
    ayri bir client. signing host'a baglidir; reverse-proxy senaryosu icin sart.
    """
    endpoint = settings.s3_public_endpoint or settings.s3_endpoint or None
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
        region_name=settings.s3_region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
        ),
    )


# ============================ Upload / download ============================

async def upload_image(
    content: bytes,
    key: str,
    content_type: Optional[str] = None,
) -> str:
    """Goruntuyu S3'e yukle, browser/mobile'in erisecegi public URL'i dondur.

    boto3 senkron — asyncio.to_thread ile event-loop'u bloke etmiyoruz.
    """
    # B2/MinIO uyumlulugu: boto3 1.36+ default'unda streaming chunked PUT
    # ("Seed signature" / "IncompleteBody" hatalari). ContentLength + BytesIO
    # ile explicit length veriliyor, payload tek seferde imzalaniyor.
    import io as _io
    extra_args: dict = {"ContentLength": len(content)}
    if content_type:
        extra_args["ContentType"] = content_type

    def _put():
        _client().put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=_io.BytesIO(content),
            **extra_args,
        )

    try:
        await asyncio.to_thread(_put)
    except botocore.exceptions.ClientError as e:
        logger.error("S3 upload basarisiz key=%s err=%s", key, e)
        raise

    return get_image_url(key)


def _is_allowed_s3_host(parsed) -> bool:
    """download_image SSRF korumasi: yalnizca configured S3 endpoint'leri kabul et."""
    allowed = []
    for ep in (settings.s3_endpoint, settings.s3_public_endpoint):
        if not ep:
            continue
        try:
            host = urlparse(ep).netloc.lower()
            if host:
                allowed.append(host)
        except Exception:
            continue
    return parsed.netloc.lower() in allowed if allowed else False


def download_image(url_or_key: str) -> bytes:
    """Bir URL veya S3 key'inden goruntuyu indir.

    SSRF korumasi: harici HTTP fetch yalnizca configured S3 endpoint'lerine
    izinli; aksi halde reddedilir (kullanici kontrollu URL ile internal/metadata
    servislerine erisim engellenir).
    """
    # S3 key ise direkt boto
    parsed = urlparse(url_or_key)
    if not parsed.scheme:
        # Saf key
        obj = _client().get_object(Bucket=settings.s3_bucket, Key=url_or_key)
        return obj["Body"].read()

    # Bucket adi path'te varsa key cikar (S3-uyumlu URL)
    if settings.s3_bucket and f"/{settings.s3_bucket}/" in url_or_key:
        key = url_or_key.split(f"/{settings.s3_bucket}/", 1)[-1]
        obj = _client().get_object(Bucket=settings.s3_bucket, Key=key)
        return obj["Body"].read()

    # Generic HTTP — yalnizca configured S3 host'una izin (SSRF guard).
    if parsed.scheme not in ("http", "https") or not _is_allowed_s3_host(parsed):
        raise ValueError(
            "download_image: yalnizca configured S3 endpoint'lerinden veya saf "
            "S3 key'inden indirme yapilabilir (SSRF korumasi)"
        )
    response = requests.get(url_or_key, timeout=30, allow_redirects=False)
    response.raise_for_status()
    return response.content


def get_image_url(key: str) -> str:
    """Public read URL — virtual-hosted ya da path-style endpoint'i kullanir."""
    base = settings.s3_public_endpoint or settings.s3_endpoint or "https://s3.amazonaws.com"
    return f"{base.rstrip('/')}/{settings.s3_bucket}/{key}"


def get_presigned_url(key: str, expires_in: Optional[int] = None) -> str:
    """Gecici (presigned) GET URL'i — varsayilan ~15dk."""
    expires = expires_in or settings.s3_presign_expiry
    return _public_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires,
    )


def ensure_bucket() -> None:
    """Bucket yoksa olustur (MinIO dev senaryosunda yararli). AWS S3'te
    permission yoksa sessizce gec."""
    try:
        _client().head_bucket(Bucket=settings.s3_bucket)
        return
    except botocore.exceptions.ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchBucket"):
            try:
                _client().create_bucket(Bucket=settings.s3_bucket)
                logger.info("Bucket olusturuldu: %s", settings.s3_bucket)
            except Exception as ce:
                logger.warning("Bucket olusturulamadi: %s", ce)
        else:
            logger.warning("Bucket head failed (%s): %s", code, e)
    except Exception as e:
        logger.warning("S3 erisimi yok, storage devre disi olabilir: %s", e)
