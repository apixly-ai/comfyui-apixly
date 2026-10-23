"""Private server-operator connection to the existing Apixly account service.

Only scoped connection tokens are stored here. Browser widgets receive the
explicit metadata projection, never account JWTs, API keys or device proofs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import secrets
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

from .client import USER_AGENT, ApixlyError, HTTPXTransport

ORIGIN = "https://apixly.ai"
ACCOUNT_BASE = ORIGIN + "/api/integrations"
TOKEN_PATTERN = re.compile(r"apc_[A-Za-z0-9_-]{43}")


class AccountError(ApixlyError):
    """A connection needs attention; no inference request is retried."""


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _text(value, maximum=256):
    return (
        isinstance(value, str)
        and len(value) <= maximum
        and "\r" not in value
        and "\n" not in value
    )


def _token(value):
    return isinstance(value, str) and TOKEN_PATTERN.fullmatch(value)


def _metadata(value):
    if not isinstance(value, dict):
        raise AccountError("The account service returned invalid connection metadata.")
    account, key = value.get("account"), value.get("selected_key")
    if not isinstance(account, dict) or not isinstance(key, dict):
        raise AccountError(
            "The account service returned incomplete account or Key metadata."
        )
    if not all(
        (type(part) is int and part > 0)
        or (isinstance(part, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", part))
        for part in (account.get("id"), key.get("id"))
    ):
        raise AccountError("The account service returned invalid identifiers.")
    revision = value.get("selection_revision")
    if (
        type(revision) is not int
        or revision < 0
        or not _text(value.get("connection_id"), 128)
        or not value["connection_id"]
    ):
        raise AccountError("The account service returned invalid connection identity.")
    mask = key.get("masked", "")
    return {
        "connection_id": value["connection_id"],
        "account": {
            "id": str(account["id"]),
            "name": str(account.get("name", ""))[:256],
            "email": str(account.get("email", ""))[:256],
        },
        "selected_key": {
            "id": str(key["id"]),
            "name": str(key.get("name", ""))[:256],
            "masked": mask if _text(mask) and ("*" in mask or "•" in mask) else "••••",
            "is_default": key.get("is_default") is True,
        },
        "selection_revision": revision,
    }


class ConnectionStore:
    """Atomic, user-private state outside ComfyUI's browser-readable userdata."""

    def __init__(self, path=None):
        if path is None:
            override = os.environ.get("APIXLY_CONNECTION_DIR")
            if override:
                path = Path(override) / "connection.json"
            else:
                root = Path(
                    os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")
                )
                path = root / "apixly" / "comfyui" / "connection.json"
        self.path = Path(path)

    def _validate(self, state):
        if (
            not isinstance(state, dict)
            or set(state) - {"mode", "binding", "pending"}
            or state.get("mode", "manual") not in {"manual", "account"}
        ):
            raise AccountError(
                "Private connection state is invalid; reconnect your account."
            )
        binding = state.get("binding")
        if binding is not None:
            if not isinstance(binding, dict) or set(binding) - {
                "access_token",
                "expires_at",
                "connection_id",
                "account",
                "selected_key",
                "selection_revision",
                "needs_reconnect",
            }:
                raise AccountError(
                    "Only scoped account connection credentials may be stored."
                )
            if not _token(binding.get("access_token")) or not _number(
                binding.get("expires_at")
            ):
                raise AccountError(
                    "Private connection credentials are invalid; reconnect your account."
                )
            _metadata(binding)
        pending = state.get("pending")
        if pending is not None:
            allowed = {
                "flow_id",
                "device_code",
                "code_verifier",
                "user_code",
                "verification_uri",
                "verification_uri_complete",
                "expires_at",
                "interval",
                "next_poll_at",
            }
            if not isinstance(pending, dict) or set(pending) - allowed:
                raise AccountError(
                    "Private authorization state is invalid; start a new connection."
                )
            if not all(
                _text(pending.get(field), 2048)
                for field in (
                    "flow_id",
                    "device_code",
                    "code_verifier",
                    "user_code",
                    "verification_uri",
                    "verification_uri_complete",
                )
            ):
                raise AccountError("Private authorization state is incomplete.")
            if not all(
                _number(pending.get(field))
                for field in ("expires_at", "interval", "next_poll_at")
            ):
                raise AccountError("Private authorization timing is invalid.")
        return state

    def load(self):
        if self.path.is_symlink():
            raise AccountError("The private connection file must not be a symlink.")
        try:
            if os.name != "nt" and self.path.stat().st_mode & 0o077:
                raise AccountError(
                    "The private connection file must be readable only by its owner."
                )
            return self._validate(json.loads(self.path.read_text()))
        except FileNotFoundError:
            return {"mode": "manual"}
        except (OSError, ValueError) as error:
            if isinstance(error, AccountError):
                raise
            raise AccountError(
                "Private connection state could not be read; reconnect your account."
            ) from None

    def save(self, state):
        self._validate(state)
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise AccountError("Private connection state must not use symlinks.")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        fd, temporary = tempfile.mkstemp(prefix=".connection-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(state, stream, ensure_ascii=True, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class AccountManager:
    def __init__(self, store=None, *, transport=None, now=time.time):
        self.store = store or ConnectionStore()
        self.transport = transport or HTTPXTransport()
        self.now = now
        self.lock = threading.RLock()

    def _clean(self, value):
        message = str(value)
        state = self.store.load()
        for group, fields in (
            ("binding", ("access_token",)),
            ("pending", ("device_code", "code_verifier")),
        ):
            for field in fields:
                secret = state.get(group, {}).get(field)
                if isinstance(secret, str) and secret:
                    message = message.replace(secret, "[redacted]")
        return message[:400]

    def _request(self, method, route, payload=None, *, token=None, accept_error=False):
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if token:
            headers["Authorization"] = "Bearer " + token
        if payload is not None:
            headers["Content-Type"] = "application/json"
        try:
            reply = self.transport.request(
                method,
                ACCOUNT_BASE + route,
                headers=headers,
                body=json.dumps(payload, allow_nan=False).encode()
                if payload is not None
                else None,
                timeout=30,
                max_bytes=1024 * 1024,
            )
            data = json.loads(reply.body) if reply.body else {}
        except Exception as error:
            raise AccountError(
                "Account request failed: " + self._clean(error)
            ) from None
        if not isinstance(data, dict):
            raise AccountError("The account service returned invalid JSON.")
        if not 200 <= reply.status < 300 and not accept_error:
            raw = data.get("error", "Account request was not accepted.")
            if isinstance(raw, dict):
                raw = raw.get("message", "Account request was not accepted.")
            raise AccountError(
                f"Account request failed ({reply.status}): {self._clean(raw)}"
            )
        return reply.status, data

    def public(self):
        state = self.store.load()
        binding = state.get("binding")
        if not binding:
            result = {"mode": state.get("mode", "manual"), "connected": False}
        else:
            result = {
                "mode": state.get("mode", "manual"),
                "connected": binding["expires_at"] > self.now()
                and not binding.get("needs_reconnect"),
                "expires_at": binding["expires_at"],
                **_metadata(binding),
            }
        pending = state.get("pending")
        if pending and pending["expires_at"] > self.now():
            result["authorization"] = self._pending_public(pending)
        return result

    def _pending_public(self, pending):
        return {
            "status": "pending",
            **{
                field: pending[field]
                for field in (
                    "flow_id",
                    "user_code",
                    "verification_uri",
                    "verification_uri_complete",
                    "expires_at",
                    "interval",
                )
            },
        }

    def start(self):
        with self.lock:
            state = self.store.load()
            if state.get("pending", {}).get("expires_at", 0) > self.now():
                return self._pending_public(state["pending"])
            verifier = secrets.token_urlsafe(32)
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .decode()
                .rstrip("=")
            )
            _, data = self._request(
                "POST",
                "/connect",
                {
                    "client_id": "comfyui",
                    "flow": "device",
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                },
            )
            for field in ("verification_uri", "verification_uri_complete"):
                uri = data.get(field)
                if not _text(uri, 2048):
                    raise AccountError("The authorization address is invalid.")
                parsed = urllib.parse.urlsplit(uri)
                if (
                    parsed.scheme != "https"
                    or parsed.netloc != "apixly.ai"
                    or not parsed.path.startswith("/connect/")
                    or parsed.fragment
                ):
                    raise AccountError(
                        "Only the official Apixly authorization page is allowed."
                    )
                query = urllib.parse.parse_qs(parsed.query)
                if {key.lower() for key in query} & {
                    "device_code",
                    "code_verifier",
                    "access_token",
                    "api_key",
                } or any(
                    isinstance(proof, str)
                    and proof
                    and proof in urllib.parse.unquote(uri)
                    for proof in (data.get("device_code"), verifier)
                ):
                    raise AccountError(
                        "Private authorization proofs cannot appear in a browser address."
                    )
            if (
                not _number(data.get("expires_in"))
                or not 0 < data["expires_in"] <= 600
                or not _number(data.get("interval"))
                or not 1 <= data["interval"] <= 60
            ):
                raise AccountError(
                    "The authorization expiry or polling interval is invalid."
                )
            pending = {
                field: data.get(field)
                for field in (
                    "flow_id",
                    "device_code",
                    "user_code",
                    "verification_uri",
                    "verification_uri_complete",
                )
            }
            pending.update(
                code_verifier=verifier,
                expires_at=self.now() + data["expires_in"],
                interval=data["interval"],
                next_poll_at=self.now(),
            )
            state["pending"] = pending
            self.store.save(state)
            return self._pending_public(pending)

    def poll(self):
        with self.lock:
            state = self.store.load()
            pending = state.get("pending")
            if not pending:
                return self.public()
            if pending["expires_at"] <= self.now():
                state.pop("pending")
                self.store.save(state)
                raise AccountError("Authorization expired; connect your account again.")
            if pending["next_poll_at"] > self.now():
                return self._pending_public(pending)
            pending["next_poll_at"] = self.now() + pending["interval"]
            self.store.save(state)
            status, data = self._request(
                "POST",
                "/token",
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": "comfyui",
                    "device_code": pending["device_code"],
                    "code_verifier": pending["code_verifier"],
                },
                accept_error=True,
            )
            if status != 200:
                error = data.get("error")
                if error in {"authorization_pending", "slow_down"}:
                    if error == "slow_down":
                        pending["interval"] = min(60, pending["interval"] + 5)
                        pending["next_poll_at"] = self.now() + pending["interval"]
                        self.store.save(state)
                    return self._pending_public(pending)
                if error in {
                    "access_denied",
                    "expired_token",
                    "invalid_grant",
                    "invalid_request",
                }:
                    state.pop("pending")
                    self.store.save(state)
                raise AccountError(
                    "Authorization was not completed; connect your account again."
                )
            if (
                not _token(data.get("access_token"))
                or not _number(data.get("expires_in"))
                or not 0 < data["expires_in"] <= 7776000
            ):
                raise AccountError(
                    "The account service returned invalid scoped credentials."
                )
            state["binding"] = {
                "access_token": data["access_token"],
                "expires_at": self.now() + data["expires_in"],
                **_metadata(data),
            }
            state["mode"] = "account"
            state.pop("pending")
            self.store.save(state)
            return self.public()

    def credentials(self):
        state = self.store.load()
        if state.get("mode", "manual") == "account":
            binding = state.get("binding")
            if (
                not binding
                or binding["expires_at"] <= self.now()
                or binding.get("needs_reconnect")
            ):
                raise AccountError(
                    "Please connect your Apixly account again before generating."
                )
            identity = f"account:{binding['account']['id']}:{binding['selected_key']['id']}:{binding['selection_revision']}"
            return {
                "mode": "account",
                "token": binding["access_token"],
                "base_url": ACCOUNT_BASE + "/v1",
                "identity": hashlib.sha256(identity.encode()).hexdigest(),
            }
        key = os.environ.get("APIXLY_API_KEY", "").strip()
        if not key or "\r" in key or "\n" in key:
            raise AccountError(
                "Connect an Apixly account or set the server APIXLY_API_KEY."
            )
        return {
            "mode": "manual",
            "token": key,
            "base_url": ORIGIN + "/v1",
            "identity": hashlib.sha256(key.encode()).hexdigest(),
        }

    def use_manual(self):
        with self.lock:
            state = self.store.load()
            state["mode"] = "manual"
            self.store.save(state)
            return self.public()

    def use_account(self):
        with self.lock:
            state = self.store.load()
            binding = state.get("binding")
            if (
                not binding
                or binding["expires_at"] <= self.now()
                or binding.get("needs_reconnect")
            ):
                raise AccountError("Please connect your Apixly account again.")
            state["mode"] = "account"
            self.store.save(state)
            return self.public()

    def cancel(self):
        with self.lock:
            state = self.store.load()
            state.pop("pending", None)
            self.store.save(state)
            return self.public()

    def refresh(self):
        with self.lock:
            state = self.store.load()
            binding = state.get("binding")
            if not binding:
                return self.public()
            status, data = self._request(
                "GET", "/account", token=binding["access_token"], accept_error=True
            )
            if status == 401:
                binding["needs_reconnect"] = True
                self.store.save(state)
                raise AccountError(
                    "This account connection expired or was revoked; connect again."
                )
            if status != 200:
                raise AccountError("Account metadata could not be refreshed.")
            state["binding"] = {
                "access_token": binding["access_token"],
                "expires_at": binding["expires_at"],
                **_metadata(data),
            }
            self.store.save(state)
            return self.public()

    def keys(self):
        credential = self.credentials()
        if credential["mode"] != "account":
            raise AccountError("Connect an account before selecting its Key.")
        _, data = self._request("GET", "/keys", token=credential["token"])
        if not isinstance(data.get("data"), list):
            raise AccountError("The account service returned an invalid Key list.")
        return {
            "data": [
                {
                    field: entry.get(field)
                    for field in (
                        "id",
                        "name",
                        "masked",
                        "status",
                        "expires_at",
                        "is_default",
                    )
                }
                for entry in data["data"]
                if isinstance(entry, dict)
            ],
            "selected_key_id": data.get("selected_key_id"),
            "selection_revision": data.get("selection_revision"),
        }

    def select_key(self, key_id):
        if not isinstance(key_id, str) or not (
            key_id == "studixly" or re.fullmatch(r"[1-9][0-9]{0,19}", key_id)
        ):
            raise AccountError("Select an existing account Key.")
        with self.lock:
            credential = self.credentials()
            if credential["mode"] != "account":
                raise AccountError("Connect an account before selecting its Key.")
            _, data = self._request(
                "PUT", "/key", {"key_id": key_id}, token=credential["token"]
            )
            metadata = _metadata(data)
            state = self.store.load()
            state["binding"].update(metadata)
            self.store.save(state)
            return self.public()

    def disconnect(self):
        with self.lock:
            state = self.store.load()
            binding = state.get("binding")
            if binding:
                status, _ = self._request(
                    "DELETE",
                    "/connection",
                    token=binding["access_token"],
                    accept_error=True,
                )
                if status not in {200, 204, 401}:
                    raise AccountError(
                        "Remote disconnection could not be confirmed; retry when the service is available."
                    )
            self.store.save({"mode": "account"})
            return self.public()
