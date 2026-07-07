import mimetypes
import os
from functools import lru_cache
from typing import Iterable, Optional, Tuple


TRUTHY = {"1", "true", "yes", "on"}


def r2_enabled() -> bool:
    return os.environ.get("R2_ENABLED", "").strip().lower() in TRUTHY


def local_storage_enabled() -> bool:
    return os.environ.get("LOCAL_STORAGE_ENABLED", "true").strip().lower() in TRUTHY


def r2_prefix() -> str:
    return os.environ.get("R2_PREFIX", "").strip().strip("/")


def get_r2_endpoint() -> str:
    explicit = os.environ.get("R2_ENDPOINT_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")

    account_id = os.environ.get("R2_ACCOUNT_ID", "").strip()
    if not account_id:
        raise RuntimeError("Set R2_ENDPOINT_URL or R2_ACCOUNT_ID for Cloudflare R2 uploads")
    return f"https://{account_id}.r2.cloudflarestorage.com"


@lru_cache(maxsize=1)
def get_r2_client():
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError("Install boto3 to upload to Cloudflare R2: pip install -r requirements.txt") from exc

    access_key = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    if not access_key or not secret_key:
        raise RuntimeError("Set R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY for Cloudflare R2 uploads")

    return boto3.client(
        "s3",
        endpoint_url=get_r2_endpoint(),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.environ.get("R2_REGION", "auto"),
        config=Config(
            signature_version="s3v4",
            connect_timeout=float(os.environ.get("R2_CONNECT_TIMEOUT", "3")),
            read_timeout=float(os.environ.get("R2_READ_TIMEOUT", "8")),
            retries={"max_attempts": int(os.environ.get("R2_MAX_ATTEMPTS", "2"))},
        ),
    )


def object_key(relative_path: str) -> str:
    normalized = relative_path.replace(os.sep, "/").lstrip("/")
    prefix = r2_prefix()
    return f"{prefix}/{normalized}" if prefix else normalized


def iter_existing_files(paths: Iterable[Tuple[str, str]]):
    for local_path, relative_path in paths:
        if os.path.isfile(local_path):
            yield local_path, relative_path


def upload_file(client, bucket: str, local_path: str, relative_path: str) -> str:
    content_type = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
    key = object_key(relative_path)
    client.upload_file(
        local_path,
        bucket,
        key,
        ExtraArgs={
            "ContentType": content_type,
            "CacheControl": os.environ.get("R2_CACHE_CONTROL", "public, max-age=60"),
        },
    )
    return key


def put_bytes(relative_path: str, data: bytes, content_type: Optional[str] = None) -> str:
    bucket = os.environ.get("R2_BUCKET", "").strip()
    if not bucket:
        raise RuntimeError("Set R2_BUCKET for Cloudflare R2 uploads")

    key = object_key(relative_path)
    if content_type is None:
        content_type = mimetypes.guess_type(relative_path)[0] or "application/octet-stream"

    get_r2_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
        CacheControl=os.environ.get("R2_CACHE_CONTROL", "public, max-age=60"),
    )
    print(f"Wrote r2://{bucket}/{key}")
    return key


def get_bytes(relative_path: str) -> Optional[bytes]:
    bucket = os.environ.get("R2_BUCKET", "").strip()
    if not bucket:
        raise RuntimeError("Set R2_BUCKET for Cloudflare R2 uploads")

    try:
        obj = get_r2_client().get_object(Bucket=bucket, Key=object_key(relative_path))
        return obj["Body"].read()
    except Exception as exc:
        response = getattr(exc, "response", {})
        code = response.get("Error", {}).get("Code")
        if code in {"NoSuchKey", "404", "NotFound"}:
            return None
        raise


def get_json(relative_path: str):
    data = get_bytes(relative_path)
    if data is None:
        return None

    import json
    return json.loads(data.decode("utf-8"))


def upload_paths(paths: Iterable[Tuple[str, str]], require_enabled: bool = False) -> int:
    if not r2_enabled() and not require_enabled:
        return 0

    bucket = os.environ.get("R2_BUCKET", "").strip()
    if not bucket:
        raise RuntimeError("Set R2_BUCKET for Cloudflare R2 uploads")

    client = get_r2_client()
    uploaded = 0
    for local_path, relative_path in iter_existing_files(paths):
        key = upload_file(client, bucket, local_path, relative_path)
        uploaded += 1
        print(f"Uploaded {local_path} to r2://{bucket}/{key}")
    return uploaded


def sync_uploads_dir(uploads_dir: str, include_root_files: Optional[Iterable[str]] = None) -> int:
    paths = []
    rates_dir = os.path.join(uploads_dir, "rates")
    if os.path.isdir(rates_dir):
        for root, _, files in os.walk(rates_dir):
            files.sort()
            for filename in files:
                local_path = os.path.join(root, filename)
                relative_path = os.path.relpath(local_path, uploads_dir)
                paths.append((local_path, relative_path))

    for filename in include_root_files or ():
        local_path = os.path.join(uploads_dir, filename)
        paths.append((local_path, filename))

    return upload_paths(paths, require_enabled=True)
