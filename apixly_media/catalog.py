"""Portable catalog v1 parser and identity-scoped cache. Standard library; no I/O."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any


class CatalogError(ValueError):
    """A safe catalog validation error; never includes the supplied value."""


def _invalid() -> CatalogError:
    return CatalogError(
        "The model catalog response was invalid. Refresh models or enter an exact model ID."
    )


def _identifier(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value.encode("utf-16-le", errors="surrogatepass")) // 2 <= 500
        and not any(ord(c) < 32 for c in value)
    )


def parse_model_catalog(payload: Any) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise _invalid()
    seen = set()
    for row in payload["data"]:
        if (
            not isinstance(row, dict)
            or not _identifier(row.get("id"))
            or not isinstance(row.get("type"), str)
            or not row["type"]
            or row["id"] in seen
        ):
            raise _invalid()
        seen.add(row["id"])
    return copy.deepcopy(payload)


def parse_model_list(payload: Any) -> list[dict]:
    return parse_model_catalog(payload)["data"]


def parse_video_config(payload: Any) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise _invalid()
    seen = set()
    for row in payload["data"]:
        if not isinstance(row, dict) or not _identifier(row.get("model")) or row["model"] in seen:
            raise _invalid()
        seen.add(row["model"])
        for field in ("modes", "resolutions", "aspect_ratios"):
            if field in row and (
                not isinstance(row[field], list)
                or any(not isinstance(item, str) for item in row[field])
            ):
                raise _invalid()
    return copy.deepcopy(payload["data"])


def build_model_options(models: list, configs: list, kind: str) -> list[dict]:
    rows = parse_model_list({"data": models})
    capabilities = {row["model"]: row for row in parse_video_config({"data": configs})}
    if kind == "video":
        return [
            {**row, "videoCapability": capabilities.get(row["id"])}
            for row in rows
            if row["type"] == "video" or row["id"] in capabilities
        ]
    return [{**row, "videoCapability": None} for row in rows if row["type"] == "image"]


def build_catalog_snapshot(
    models_payload: Any, video_payload: Any, *, previous_videos: list | tuple = ()
) -> dict:
    """Keep current authorized model rows even if the capability request failed."""
    envelope = parse_model_catalog(models_payload)
    models = envelope.pop("data")
    allowed = {row["id"] for row in models}
    error = None
    try:
        videos = parse_video_config(video_payload)
    except CatalogError:
        try:
            videos = parse_video_config({"data": list(previous_videos)})
        except CatalogError:
            videos = []
        error = (
            "Video parameters are unavailable. Showing saved video parameters; try Refresh models."
            if videos
            else "Video parameters are unavailable. Image models are ready; try Refresh models for video controls."
        )
    videos = [row for row in videos if row["model"] in allowed]
    return {"models": models, "videos": videos, "metadata": envelope, "capabilitiesError": error}


def catalog_identity(value: Mapping[str, Any]) -> str:
    if value.get("mode") == "manual" and isinstance(value.get("key"), str) and value["key"]:
        return "manual:" + hashlib.sha256(value["key"].encode()).hexdigest()
    if value.get("mode") == "account" and all(
        field in value for field in ("connectionId", "accountId", "keyId", "revision")
    ):
        fields = [value[field] for field in ("connectionId", "accountId", "keyId", "revision")]
        # Connection metadata is validated by each host's account adapter.
        encoded = json.dumps(
            [str(field) for field in fields], ensure_ascii=False, separators=(",", ":")
        )
        return "account:" + hashlib.sha256(encoded.encode()).hexdigest()
    raise CatalogError("Connect an account or configure an API key to load models.")


@dataclass
class _Entry:
    snapshot: dict | None = None
    updated_at: float | None = None
    observed_at_ms: int | None = None
    error: str | None = None
    future: Future | None = None
    valid: bool = True


class CatalogCache:
    """Ten-minute SWR with one refresh per identity; raw secrets never key entries.

    The loader is supplied by the host and must bound its own I/O. Cache state is
    process-local. Multiple plugin workers have independent caches.
    """

    def __init__(
        self,
        *,
        ttl: float = 600,
        now: Callable[[], float] = time.monotonic,
        wall_now: Callable[[], float] = time.time,
    ):
        self.ttl, self.now = ttl, now
        self.wall_now = wall_now
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="apixly-catalog")

    def _entry(self, identity: str) -> _Entry:
        if not isinstance(identity, str) or not re.fullmatch(
            r"(?:manual|account):[a-f0-9]{64}", identity
        ):
            raise CatalogError("Invalid catalog identity.")
        return self._entries.setdefault(identity, _Entry())

    def _status(self, entry: _Entry | None) -> dict:
        available = entry is not None and entry.valid and entry.snapshot is not None
        snapshot = copy.deepcopy(entry.snapshot) if available else {"models": [], "videos": []}
        return {
            **snapshot,
            "available": available,
            "updatedAt": entry.observed_at_ms if available else None,
            "stale": bool(
                entry.error
                or snapshot.get("capabilitiesError")
                or self.now() - entry.updated_at >= self.ttl
            )
            if available
            else True,
            "refreshing": bool(entry and entry.valid and entry.future),
            "error": entry.error if entry and entry.valid else None,
        }

    def peek(self, identity: str) -> dict:
        with self._lock:
            return self._status(self._entries.get(identity))

    def _load(self, entry: _Entry, loader: Callable[[], dict]) -> dict:
        try:
            snapshot = loader()
            if (
                not isinstance(snapshot, dict)
                or not isinstance(snapshot.get("models"), list)
                or not isinstance(snapshot.get("videos"), list)
            ):
                raise _invalid()
            snapshot = copy.deepcopy(snapshot)
            with self._lock:
                if entry.valid:
                    entry.snapshot, entry.updated_at, entry.error = snapshot, self.now(), None
                    entry.observed_at_ms = int(self.wall_now() * 1000)
        except Exception:
            with self._lock:
                if entry.valid:
                    entry.error = "Could not refresh the model catalog. Saved options may be out of date. Try Refresh models."
        with self._lock:
            entry.future = None
            return self._status(entry)

    def read(
        self,
        identity: str,
        loader: Callable[[], dict],
        *,
        force: bool = False,
        on_update: Callable[[dict], None] | None = None,
    ) -> dict:
        with self._lock:
            entry = self._entry(identity)
            warm = entry.snapshot is not None and not force
            if warm and not self._status(entry)["stale"]:
                self._subscribe(entry.future, on_update)
                return self._status(entry)
            if entry.future is None:
                entry.future = self._executor.submit(self._load, entry, loader)
            pending = entry.future
            if warm:
                self._subscribe(pending, on_update)
                return self._status(entry)
        return pending.result()

    @staticmethod
    def _subscribe(pending: Future | None, on_update: Callable[[dict], None] | None) -> None:
        if pending is None or on_update is None:
            return

        def notify(future: Future) -> None:
            try:
                on_update(future.result())
            except Exception:
                pass

        pending.add_done_callback(notify)

    def settled(self, identity: str, *, timeout: float | None = None) -> dict:
        with self._lock:
            entry = self._entries.get(identity)
            pending = entry.future if entry else None
        if pending:
            pending.result(timeout=timeout)
        with self._lock:
            return self._status(entry)

    def invalidate(self, identity: str) -> None:
        with self._lock:
            entry = self._entries.pop(identity, None)
            if entry:
                entry.valid, entry.snapshot = False, None

    def clear(self) -> None:
        with self._lock:
            for entry in self._entries.values():
                entry.valid, entry.snapshot = False, None
            self._entries.clear()

    def close(self) -> None:
        self.clear()
        self._executor.shutdown(wait=True)
