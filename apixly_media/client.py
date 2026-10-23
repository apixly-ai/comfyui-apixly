"""Small, dependency-free client for the public Apixly media REST contract."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

BASE_URL = "https://apixly.ai/v1"
USER_AGENT = "comfyui-apixly/0.3.0"
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_VIDEO_BYTES = 256 * 1024 * 1024
PENDING = {
    "queued",
    "submitted",
    "pending",
    "in_progress",
    "processing",
    "running",
    "generating",
    "downloading",
    "accepted",
}
SUCCEEDED = {"succeeded", "completed", "success"}
TRANSIENT_HTTP = {408, 429, 500, 502, 503, 504, 524}
RESERVED = {
    "model",
    "prompt",
    "async",
    "image",
    "image[]",
    "images",
    "mask",
    "api_key",
    "authorization",
    "access_token",
    "callback_url",
}


class ApixlyError(RuntimeError):
    """A request or terminal task failed without any automatic paid retry."""


class UnknownSubmission(ApixlyError):
    """A paid POST may have reached the server; submitting again is unsafe."""


class PollTimeout(ApixlyError):
    """A task can still be running and must be resumed by its existing ID."""


class TransientReadError(ApixlyError):
    """A safe GET can be retried within the existing polling deadline."""


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict
    body: bytes


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class StandardTransport:
    """Never follows a redirect implicitly or retries a request."""

    def __init__(self):
        self.opener = urllib.request.build_opener(_NoRedirect())

    def request(
        self, method, url, *, headers, body=None, timeout=60, max_bytes=MAX_JSON_BYTES
    ):
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            stream = self.opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            stream = error
        with stream:
            chunks = []
            total = 0
            while True:
                chunk = stream.read(min(65536, max_bytes - total + 1))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise ApixlyError(
                        "Response exceeds the configured download size limit."
                    )
            data = b"".join(chunks)
            return Response(
                stream.code, {k.lower(): v for k, v in stream.headers.items()}, data
            )


class HTTPXTransport:
    """Bounded HTTP streaming; redirect handling stays with the caller."""

    def request(
        self, method, url, *, headers, body=None, timeout=60, max_bytes=MAX_JSON_BYTES
    ):
        import httpx

        with httpx.Client(follow_redirects=False, timeout=timeout) as client:
            with client.stream(method, url, headers=headers, content=body) as stream:
                chunks = []
                total = 0
                for chunk in stream.iter_bytes(65536):
                    total += len(chunk)
                    if total > max_bytes:
                        raise ApixlyError(
                            "Response exceeds the configured download size limit."
                        )
                    chunks.append(chunk)
                return Response(
                    stream.status_code, dict(stream.headers), b"".join(chunks)
                )


def task_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]*", value):
        raise ValueError("A positive numeric Apixly task ID is required.")
    return value


def checked_parameters(params):
    if params is None:
        return {}
    if not isinstance(params, dict):
        raise ValueError("Parameters must be a JSON object.")
    if any(not isinstance(key, str) or key.lower() in RESERVED for key in params):
        raise ValueError(
            "Parameters cannot override model, prompt, references, async, callbacks, or credentials."
        )
    # Reject NaN/Infinity before a paid action; leave model-specific fields intact.
    json.dumps(params, allow_nan=False)
    return dict(params)


def safe_media_url(value):
    if not isinstance(value, str):
        raise ApixlyError("A valid HTTPS media URL is required.")
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or any(ord(c) < 32 for c in value)
    ):
        raise ApixlyError(
            "Only HTTPS media URLs without embedded credentials are allowed."
        )
    if parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
        raise ApixlyError("Local media endpoints are not allowed.")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ApixlyError("Private media endpoints are not allowed.")
    return value


def public_receipt(job):
    """Only documented customer fields may enter node outputs/PNG metadata."""
    fields = {
        "id",
        "task_id",
        "status",
        "model",
        "progress",
        "created",
        "created_at",
        "completed_at",
        "usage",
        "url",
        "data",
        "error",
        "request_id",
        "seconds",
        "size",
        "output_cost",
        "input_video_cost",
        "input_image_cost",
        "input_seconds",
        "output_seconds",
        "billed_seconds",
        "input_image_count",
        "billed_images",
        "settlement_status",
        "parameter_adjustments",
        "effective_parameters",
    }
    return {key: value for key, value in job.items() if key in fields}


class ApixlyClient:
    def __init__(self, api_key, *, transport=None, auth_mode="manual", identity=None):
        if (
            not isinstance(api_key, str)
            or not api_key.strip()
            or "\n" in api_key
            or "\r" in api_key
        ):
            raise ValueError(
                "Set APIXLY_API_KEY in the ComfyUI server environment and restart ComfyUI."
            )
        self._api_key = api_key.strip()
        if auth_mode not in {"manual", "account"}:
            raise ValueError("Choose a supported Apixly authentication mode.")
        self.auth_mode = auth_mode
        if auth_mode == "account":
            if (
                not re.fullmatch(r"apc_[A-Za-z0-9_-]{43}", self._api_key)
                or not isinstance(identity, str)
                or not re.fullmatch(r"[a-f0-9]{64}", identity)
            ):
                raise ValueError(
                    "A scoped account connection and its identity are required."
                )
            self.base_url = "https://apixly.ai/api/integrations/v1"
            self.fingerprint_identity = bytes.fromhex(identity)
        else:
            self.base_url = BASE_URL
            self.fingerprint_identity = hashlib.sha256(self._api_key.encode()).digest()
        self.transport = transport or HTTPXTransport()

    @classmethod
    def from_environment(cls):
        from .account import AccountManager

        manager = AccountManager()
        if manager.store.load().get("mode") == "account":
            manager.refresh()
            credentials = manager.credentials()
            return cls(
                credentials["token"],
                auth_mode=credentials["mode"],
                identity=credentials["identity"],
            )
        return cls(os.environ.get("APIXLY_API_KEY", ""))

    def __repr__(self):
        return f"ApixlyClient(base_url={self.base_url!r}, credentials=<redacted>)"

    def _clean(self, message):
        return str(message).replace(self._api_key, "[redacted]")[:1000]

    def _json(self, method, path, payload=None, *, multipart=None, timeout=60):
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        body = None
        if multipart:
            body, content_type = multipart
            headers["Content-Type"] = content_type
        elif payload is not None:
            body = json.dumps(payload, allow_nan=False).encode()
            headers["Content-Type"] = "application/json"
        try:
            result = self.transport.request(
                method,
                self.base_url + path,
                headers=headers,
                body=body,
                timeout=timeout,
                max_bytes=MAX_JSON_BYTES,
            )
        except Exception:
            if method == "POST":
                raise UnknownSubmission(
                    "Submission outcome is unknown. Do not submit again; check your existing Apixly tasks before changing request_nonce."
                ) from None
            raise TransientReadError(
                "Status request could not be read; resume the existing task ID."
            ) from None
        if not 200 <= result.status < 300:
            message = f"Apixly HTTP {result.status}"
            try:
                error = json.loads(result.body).get("error", {})
                if isinstance(error, dict):
                    message += ": " + str(
                        error.get("message", error.get("code", "Request failed"))
                    )
            except (ValueError, TypeError, AttributeError):
                pass
            message = self._clean(message)
            if method == "POST" and (
                result.status >= 500 or result.status in {408, 302, 301, 303, 307, 308}
            ):
                raise UnknownSubmission(
                    message + ". Do not submit again; check your existing Apixly tasks."
                )
            if method == "GET" and result.status in TRANSIENT_HTTP:
                raise TransientReadError(message)
            raise ApixlyError(message)
        try:
            data = json.loads(result.body)
            if not isinstance(data, dict):
                raise ValueError("Expected object")
        except (ValueError, TypeError):
            if method == "POST":
                raise UnknownSubmission(
                    "Submission response is unreadable. Do not submit again; check your existing Apixly tasks."
                ) from None
            raise TransientReadError(
                "Status response is unreadable; resume the existing task ID."
            ) from None
        request_id = result.headers.get("x-request-id") or result.headers.get(
            "X-Request-ID"
        )
        if request_id:
            data["request_id"] = request_id
        if method == "POST":
            try:
                task_id(data.get("id"))
            except ValueError:
                raise UnknownSubmission(
                    "Submission response has no usable task ID. Do not submit again; check your existing Apixly tasks."
                ) from None
        # Even a remote error/success body that echoes the key must not place it
        # into a workflow receipt, a result URL, or a downstream image's metadata.
        return json.loads(json.dumps(data).replace(self._api_key, "[redacted]"))

    def submit_image(self, model, prompt, params=None, *, images=None, mask=None):
        parameters = checked_parameters(params)
        self._validate_model(model)
        if mask and not images:
            raise ValueError("A mask requires at least one reference image.")
        fields = {**parameters, "model": model, "prompt": prompt, "async": True}
        if not images:
            return self._json("POST", "/images/generations", fields)
        boundary = "apixly-" + uuid.uuid4().hex
        parts = []
        for name, value in fields.items():
            if not re.fullmatch(r"[a-zA-Z0-9_.-]+", name):
                raise ValueError(
                    "Multipart parameter names may contain only letters, numbers, dots, dashes, and underscores."
                )
            text = str(value).lower() if isinstance(value, bool) else str(value)
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{text}\r\n'.encode()
            )
        files = [
            ("image[]", f"reference-{index}.png", value)
            for index, value in enumerate(images)
        ]
        if mask:
            files.append(("mask", "mask.png", mask))
        for name, filename, value in files:
            if (
                not isinstance(value, bytes)
                or not value
                or len(value) > MAX_IMAGE_BYTES
            ):
                raise ValueError(
                    "Reference images must be nonempty PNG bytes within the 32 MiB limit."
                )
            parts.extend(
                [
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'.encode(),
                    value,
                    b"\r\n",
                ]
            )
        parts.append(f"--{boundary}--\r\n".encode())
        return self._json(
            "POST",
            "/images/edits",
            multipart=(b"".join(parts), f"multipart/form-data; boundary={boundary}"),
        )

    def submit_video(self, model, prompt, params=None, *, images=None):
        parameters = checked_parameters(params)
        self._validate_model(model)
        payload = {**parameters, "model": model, "prompt": prompt}
        if images:
            payload["images"] = list(images)
        return self._json("POST", "/videos", payload)

    @staticmethod
    def _validate_model(model):
        if not isinstance(model, str) or not model.strip() or model != model.strip():
            raise ValueError("Enter an exact model ID without surrounding whitespace.")

    def get_job(self, kind, identifier, *, timeout=60):
        identifier = task_id(identifier)
        if kind not in {"image", "video"}:
            raise ValueError("Task kind must be image or video.")
        endpoint = "/images/generations/" if kind == "image" else "/videos/"
        job = self._json("GET", endpoint + identifier, timeout=timeout)
        if "id" in job and str(job["id"]) != identifier:
            raise ApixlyError(
                "Status response task ID does not match the requested task."
            )
        job.setdefault("id", identifier)
        return job

    def wait_job(
        self,
        kind,
        identifier,
        *,
        timeout_seconds=600,
        poll_interval=3,
        clock=time.monotonic,
        sleep=time.sleep,
        on_progress=None,
    ):
        task_id(identifier)
        if not 0 < timeout_seconds <= 3600 or not 0 < poll_interval <= 60:
            raise ValueError(
                "Wait timeout must be 1–3600 seconds; poll interval must be 0–60 seconds."
            )
        deadline = clock() + timeout_seconds
        while clock() < deadline:
            try:
                job = self.get_job(
                    kind, identifier, timeout=max(0.001, min(60, deadline - clock()))
                )
            except TransientReadError:
                job = {"status": "in_progress"}
            if on_progress:
                on_progress(job)
            status = job.get("status")
            if status in SUCCEEDED:
                if kind == "video" or job.get("data"):
                    return job
                # Current gateway can temporarily succeed before signing a URL.
            elif status not in PENDING:
                detail = job.get("error", {})
                message = (
                    detail.get("message", str(status))
                    if isinstance(detail, dict)
                    else str(detail)
                )
                raise ApixlyError(
                    self._clean(
                        f"Apixly {kind} task {identifier}: {message}. No new generation was submitted."
                    )
                )
            remaining = deadline - clock()
            if remaining > 0:
                sleep(min(poll_interval, remaining))
        raise PollTimeout(
            f"Task {identifier} is not ready within {timeout_seconds}s. Resume this existing task ID with the Result node; no new generation was submitted."
        )

    def _media(self, url, *, authenticated=False, max_bytes):
        url = safe_media_url(url)
        for attempt in range(6):
            headers = {"User-Agent": USER_AGENT}
            if authenticated:
                parsed = urllib.parse.urlsplit(url)
                if (
                    parsed.scheme != "https"
                    or parsed.netloc != "apixly.ai"
                    or not re.fullmatch(
                        re.escape(urllib.parse.urlsplit(self.base_url).path)
                        + r"/videos/[1-9][0-9]*/content",
                        parsed.path,
                    )
                    or parsed.query
                ):
                    raise ApixlyError(
                        "Authenticated downloads are restricted to the Apixly task content endpoint."
                    )
                headers["Authorization"] = f"Bearer {self._api_key}"
            for read_attempt in range(3):
                try:
                    result = self.transport.request(
                        "GET", url, headers=headers, timeout=120, max_bytes=max_bytes
                    )
                    break
                except ApixlyError:
                    raise
                except Exception as error:
                    if read_attempt == 2:
                        raise ApixlyError(
                            f"Media download failed after three safe GET attempts ({type(error).__name__}). Resume the existing task ID; do not submit another generation."
                        ) from None
                    time.sleep(0.5 * (read_attempt + 1))
            if result.status in {301, 302, 303, 307, 308}:
                location = result.headers.get("location") or result.headers.get(
                    "Location"
                )
                if not location:
                    raise ApixlyError("Media redirect has no destination.")
                url = safe_media_url(urllib.parse.urljoin(url, location))
                authenticated = False  # Never forward API keys to any redirect.
                continue
            if not 200 <= result.status < 300:
                raise ApixlyError(
                    f"Media download returned HTTP {result.status}; query the existing task for a fresh URL."
                )
            if not result.body or len(result.body) > max_bytes:
                raise ApixlyError(
                    "Media body is empty or exceeds the download size limit."
                )
            return result
        raise ApixlyError("Media download exceeded the five-redirect limit.")

    def image_bytes(self, job):
        if job.get("status") not in SUCCEEDED or not job.get("data"):
            raise ApixlyError("Image task has no completed image result.")
        images = []
        for item in job["data"]:
            if item.get("url"):
                images.append(self._media(item["url"], max_bytes=MAX_IMAGE_BYTES).body)
            elif item.get("b64_json"):
                try:
                    value = base64.b64decode(item["b64_json"], validate=True)
                except ValueError:
                    raise ApixlyError("Image result contains invalid base64.") from None
                if not value or len(value) > MAX_IMAGE_BYTES:
                    raise ApixlyError("Image result exceeds the image size limit.")
                images.append(value)
            else:
                raise ApixlyError("Image result has no URL or base64 image.")
        return images

    def download_video(self, job, destination):
        if job.get("status") not in SUCCEEDED:
            raise ApixlyError(
                "Video task is not completed; query the existing task ID first."
            )
        identifier = task_id(job.get("id"))
        url = job.get("url") or self.base_url + f"/videos/{identifier}/content"
        result = self._media(
            url, authenticated=not bool(job.get("url")), max_bytes=MAX_VIDEO_BYTES
        )
        content_type = (
            result.headers.get("content-type", result.headers.get("Content-Type", ""))
            .split(";")[0]
            .lower()
        )
        signature = result.body[4:8] == b"ftyp" or result.body.startswith(
            b"\x1aE\xdf\xa3"
        )
        if not signature or (
            not content_type.startswith("video/")
            and content_type != "application/octet-stream"
        ):
            raise ApixlyError(
                "The result is not a recognizable MP4/MOV/WebM video; no file was saved."
            )
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink() or destination.exists():
            raise ApixlyError(
                "Video destination already exists; choose a fresh output filename."
            )
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix=".apixly-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(result.body)
            os.replace(temporary, destination)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        return destination
