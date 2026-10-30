"""Local or private Supabase Storage for uploaded resumes, JDs, and documents."""
import mimetypes
from pathlib import Path
from urllib.parse import quote

import requests

from config import Config


class FileStorageError(RuntimeError):
    pass


def uses_remote_storage():
    return Config.FILE_STORAGE_BACKEND == "supabase"


def _validate_key(storage_key):
    if not isinstance(storage_key, str) or not storage_key or storage_key in {".", ".."}:
        raise ValueError("Invalid file storage key.")
    if "/" in storage_key or "\\" in storage_key or ".." in storage_key:
        raise ValueError("Invalid file storage key.")
    return storage_key


def _remote_request(storage_key):
    if not Config.SUPABASE_URL or not Config.SUPABASE_STORAGE_BUCKET or not Config.SUPABASE_SERVICE_ROLE_KEY:
        raise FileStorageError("Supabase Storage is enabled but its URL, bucket, or server key is missing.")
    key = quote(_validate_key(storage_key), safe="")
    bucket = quote(Config.SUPABASE_STORAGE_BUCKET, safe="")
    url = f"{Config.SUPABASE_URL}/storage/v1/object/{bucket}/{key}"
    headers = {
        "apikey": Config.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {Config.SUPABASE_SERVICE_ROLE_KEY}",
    }
    return url, headers


def store_file(storage_key, source_path, content_type=None):
    """Store an already-staged upload; local storage remains the local-dev default."""
    _validate_key(storage_key)
    if not uses_remote_storage():
        destination = Path(Config.UPLOAD_FOLDER) / storage_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        if Path(source_path).resolve() != destination.resolve():
            with open(source_path, "rb") as source, open(destination, "wb") as target:
                target.write(source.read())
        return

    url, headers = _remote_request(storage_key)
    headers["Content-Type"] = content_type or mimetypes.guess_type(storage_key)[0] or "application/octet-stream"
    headers["x-upsert"] = "false"
    try:
        with open(source_path, "rb") as source:
            response = requests.post(url, headers=headers, data=source, timeout=(10, 90))
        response.raise_for_status()
    except requests.RequestException as error:
        raise FileStorageError("The file could not be saved to remote storage.") from error


def store_bytes(storage_key, contents, content_type=None):
    _validate_key(storage_key)
    if not uses_remote_storage():
        destination = Path(Config.UPLOAD_FOLDER) / storage_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
        return

    url, headers = _remote_request(storage_key)
    headers["Content-Type"] = content_type or mimetypes.guess_type(storage_key)[0] or "application/octet-stream"
    headers["x-upsert"] = "false"
    try:
        response = requests.post(url, headers=headers, data=contents, timeout=(10, 90))
        response.raise_for_status()
    except requests.RequestException as error:
        raise FileStorageError("The file could not be saved to remote storage.") from error


def retrieve_file(storage_key):
    """Return (bytes, content type), or None when the object does not exist."""
    _validate_key(storage_key)
    if not uses_remote_storage():
        path = Path(Config.UPLOAD_FOLDER) / storage_key
        if not path.is_file():
            return None
        return path.read_bytes(), mimetypes.guess_type(storage_key)[0] or "application/octet-stream"

    url, headers = _remote_request(storage_key)
    url = url.replace("/storage/v1/object/", "/storage/v1/object/authenticated/", 1)
    try:
        response = requests.get(url, headers=headers, timeout=(10, 90))
    except requests.RequestException as error:
        raise FileStorageError("The file could not be retrieved from remote storage.") from error
    if response.status_code == 404:
        return None
    try:
        response.raise_for_status()
    except requests.RequestException as error:
        raise FileStorageError("The file could not be retrieved from remote storage.") from error
    return response.content, response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0]
