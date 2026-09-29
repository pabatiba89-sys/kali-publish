from __future__ import annotations

import json
import mimetypes
import re
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests


PLATFORM_CREDENTIALS = {
    7: {"platform": "x", "required": ("access_token",)},
    8: {"platform": "instagram", "required": ("access_token", "ig_user_id")},
    9: {"platform": "facebook", "required": ("access_token", "page_id")},
}


class CredentialError(ValueError):
    pass


class PlatformApiError(RuntimeError):
    pass


def validate_credentials(platform_type: int, credentials: dict[str, Any]) -> dict[str, Any]:
    schema = PLATFORM_CREDENTIALS.get(platform_type)
    if schema is None:
        raise CredentialError(f"Platform type {platform_type} does not use API credentials")
    if not isinstance(credentials, dict):
        raise CredentialError("credentials must be an object")

    normalized = dict(credentials)
    declared_platform = str(normalized.get("platform", schema["platform"])).strip().lower()
    if declared_platform != schema["platform"]:
        raise CredentialError(
            f"credentials platform must be {schema['platform']} for type {platform_type}"
        )
    normalized["platform"] = declared_platform

    version = normalized.get("graph_api_version")
    if version is not None and not re.fullmatch(r"v\d+\.\d+", str(version)):
        raise CredentialError("graph_api_version must look like v25.0")

    missing = [
        field
        for field in schema["required"]
        if not isinstance(normalized.get(field), str) or not normalized[field].strip()
    ]
    if missing:
        raise CredentialError(f"missing credential fields: {', '.join(missing)}")
    return normalized


def load_credentials(account_file: str | Path, platform_type: int) -> dict[str, Any]:
    path = Path(account_file)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CredentialError(f"credential file not found: {path.name}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise CredentialError(f"invalid credential file: {path.name}") from exc
    return validate_credentials(platform_type, payload)


def build_caption(title: str, tags: list[str] | None) -> str:
    clean_tags = [
        f"#{str(tag).strip().lstrip('#')}" for tag in (tags or []) if str(tag).strip()
    ]
    return " ".join(part for part in [title.strip(), " ".join(clean_tags)] if part).strip()


def require_upload_url(url: str, expected_host: str) -> str:
    parsed = urlparse(str(url))
    if parsed.scheme != "https" or parsed.hostname != expected_host:
        raise PlatformApiError(f"Unexpected upload host; expected {expected_host}")
    return str(url)


class OfficialApiPublisher:
    def __init__(
        self,
        credentials: dict[str, Any],
        *,
        session: requests.Session | None = None,
        timeout: int = 600,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.credentials = credentials
        self.session = session or requests.Session()
        self.timeout = timeout
        self.sleep = sleep

    def _request_json(self, method: str, url: str, **kwargs) -> dict[str, Any]:
        kwargs.setdefault("timeout", self.timeout)
        response = self.session.request(method, url, **kwargs)
        if 200 <= response.status_code < 300 and not getattr(response, "content", b"body"):
            return {}
        try:
            data = response.json()
        except ValueError as exc:
            raise PlatformApiError(
                f"Platform API returned HTTP {response.status_code} with a non-JSON response"
            ) from exc
        if not 200 <= response.status_code < 300:
            message = data.get("error", data)
            if isinstance(message, dict):
                message = message.get("message") or message.get("detail") or message
            raise PlatformApiError(f"Platform API HTTP {response.status_code}: {message}")
        return data


class XVideoPublisher(OfficialApiPublisher):
    API_BASE = "https://api.x.com/2"
    CHUNK_SIZE = 4 * 1024 * 1024

    def publish(self, video_path: str | Path, text: str) -> dict[str, Any]:
        path = Path(video_path)
        token = self.credentials["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        media_type = mimetypes.guess_type(path.name)[0] or "video/mp4"

        initialized = self._request_json(
            "POST",
            f"{self.API_BASE}/media/upload/initialize",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "media_type": media_type,
                "total_bytes": path.stat().st_size,
                "media_category": "tweet_video",
            },
        )
        media_id = str(initialized.get("data", {}).get("id", ""))
        if not media_id:
            raise PlatformApiError("X media initialization did not return a media id")

        with path.open("rb") as source:
            segment_index = 0
            while chunk := source.read(self.CHUNK_SIZE):
                self._request_json(
                    "POST",
                    f"{self.API_BASE}/media/upload/{media_id}/append",
                    headers=headers,
                    data={"segment_index": str(segment_index)},
                    files={"media": (path.name, chunk, "application/octet-stream")},
                )
                segment_index += 1

        finalized = self._request_json(
            "POST",
            f"{self.API_BASE}/media/upload/{media_id}/finalize",
            headers=headers,
        )
        self._wait_until_ready(media_id, finalized, headers)
        return self._request_json(
            "POST",
            f"{self.API_BASE}/tweets",
            headers={**headers, "Content-Type": "application/json"},
            json={"text": text, "media": {"media_ids": [media_id]}},
        )

    def _wait_until_ready(
        self, media_id: str, response: dict[str, Any], headers: dict[str, str]
    ) -> None:
        processing = response.get("data", {}).get("processing_info")
        for _ in range(120):
            if not processing:
                return
            state = processing.get("state")
            if state == "succeeded":
                return
            if state == "failed":
                error = processing.get("error", {})
                raise PlatformApiError(f"X media processing failed: {error}")
            self.sleep(max(1, min(int(processing.get("check_after_secs", 1)), 30)))
            response = self._request_json(
                "GET",
                f"{self.API_BASE}/media/upload",
                headers=headers,
                params={"command": "STATUS", "media_id": media_id},
            )
            processing = response.get("data", {}).get("processing_info")
        raise PlatformApiError("X media processing timed out")


class InstagramReelPublisher(OfficialApiPublisher):
    def publish(self, video_path: str | Path, caption: str) -> dict[str, Any]:
        path = Path(video_path)
        token = self.credentials["access_token"]
        user_id = self.credentials["ig_user_id"]
        version = self.credentials.get("graph_api_version", "v25.0")
        graph_base = f"https://graph.facebook.com/{version}"
        bearer_headers = {"Authorization": f"Bearer {token}"}

        container = self._request_json(
            "POST",
            f"{graph_base}/{user_id}/media",
            headers=bearer_headers,
            data={
                "media_type": "REELS",
                "upload_type": "resumable",
                "caption": caption,
                "share_to_feed": "true",
            },
        )
        container_id = str(container.get("id", ""))
        if not container_id:
            raise PlatformApiError("Instagram did not return a media container id")
        upload_url = container.get("uri") or (
            f"https://rupload.facebook.com/ig-api-upload/{version}/{container_id}"
        )
        upload_url = require_upload_url(upload_url, "rupload.facebook.com")

        with path.open("rb") as source:
            self._request_json(
                "POST",
                upload_url,
                headers={
                    "Authorization": f"OAuth {token}",
                    "Content-Type": mimetypes.guess_type(path.name)[0] or "video/mp4",
                    "offset": "0",
                    "file_size": str(path.stat().st_size),
                },
                data=source,
            )

        self._wait_for_container(graph_base, container_id, bearer_headers)
        return self._request_json(
            "POST",
            f"{graph_base}/{user_id}/media_publish",
            headers=bearer_headers,
            data={"creation_id": container_id},
        )

    def _wait_for_container(
        self, graph_base: str, container_id: str, headers: dict[str, str]
    ) -> None:
        for _ in range(60):
            result = self._request_json(
                "GET",
                f"{graph_base}/{container_id}",
                headers=headers,
                params={"fields": "status_code,status"},
            )
            status = result.get("status_code")
            if status in {"FINISHED", "PUBLISHED"}:
                return
            if status in {"ERROR", "EXPIRED"}:
                raise PlatformApiError(
                    f"Instagram media processing failed: {result.get('status')}"
                )
            self.sleep(5)
        raise PlatformApiError("Instagram media processing timed out")


class FacebookReelPublisher(OfficialApiPublisher):
    def publish(
        self,
        video_path: str | Path,
        caption: str,
        publish_date=None,
    ) -> dict[str, Any]:
        path = Path(video_path)
        token = self.credentials["access_token"]
        page_id = self.credentials["page_id"]
        version = self.credentials.get("graph_api_version", "v25.0")
        graph_base = f"https://graph.facebook.com/{version}"
        endpoint = f"{graph_base}/{page_id}/video_reels"
        bearer_headers = {"Authorization": f"Bearer {token}"}

        initialized = self._request_json(
            "POST",
            endpoint,
            headers=bearer_headers,
            data={"upload_phase": "start"},
        )
        video_id = str(initialized.get("video_id", ""))
        upload_url = initialized.get("upload_url")
        if not video_id or not upload_url:
            raise PlatformApiError("Facebook did not return a video id and upload URL")
        upload_url = require_upload_url(upload_url, "rupload.facebook.com")

        with path.open("rb") as source:
            self._request_json(
                "POST",
                upload_url,
                headers={
                    "Authorization": f"OAuth {token}",
                    "Content-Type": "application/octet-stream",
                    "offset": "0",
                    "file_size": str(path.stat().st_size),
                },
                data=source,
            )

        finish = {
            "video_id": video_id,
            "upload_phase": "finish",
            "video_state": "SCHEDULED" if publish_date else "PUBLISHED",
            "description": caption,
            "title": caption[:255],
        }
        if publish_date:
            finish["scheduled_publish_time"] = str(int(publish_date.timestamp()))
        return self._request_json(
            "POST",
            endpoint,
            headers=bearer_headers,
            data=finish,
        )
