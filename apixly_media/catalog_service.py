"""Lazy, read-only model catalogs for the server operator's selected credentials."""

from __future__ import annotations

import json
import threading

from .catalog import (
    CatalogCache,
    CatalogError,
    build_catalog_snapshot,
    build_model_options,
    catalog_identity,
)
from .client import MAX_JSON_BYTES, USER_AGENT, HTTPXTransport

_BASES = {
    "manual": "https://apixly.ai/v1",
    "account": "https://apixly.ai/api/integrations/v1",
}


class CatalogService:
    def __init__(self, manager, *, transport=None, cache=None):
        self.manager = manager
        self.transport = transport or HTTPXTransport()
        self.cache = cache or CatalogCache()
        self._identity = None
        self._lock = threading.RLock()

    def clear(self):
        with self._lock:
            self.cache.clear()
            self._identity = None

    def close(self):
        self.clear()
        self.cache.close()

    def _scope(self):
        credential = self.manager.credentials()
        mode = credential.get("mode")
        if mode not in _BASES or credential.get("base_url") != _BASES[mode]:
            raise CatalogError(
                "Model catalogs may use only the official Apixly service."
            )
        if mode == "manual":
            identity = catalog_identity({"mode": "manual", "key": credential["token"]})
            scope = {"mode": mode, "selected_key_id": None, "selection_revision": None}
        else:
            public = self.manager.public()
            identity = catalog_identity(
                {
                    "mode": mode,
                    "connectionId": public.get("connection_id"),
                    "accountId": public.get("account", {}).get("id"),
                    "keyId": public.get("selected_key", {}).get("id"),
                    "revision": public.get("selection_revision"),
                }
            )
            scope = {
                "mode": mode,
                "selected_key_id": public.get("selected_key", {}).get("id"),
                "selection_revision": public.get("selection_revision"),
            }
        return credential, identity, scope

    def _get(self, credential, path):
        reply = self.transport.request(
            "GET",
            credential["base_url"] + path,
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
                "Authorization": "Bearer " + credential["token"],
            },
            timeout=30,
            max_bytes=MAX_JSON_BYTES,
        )
        if not 200 <= reply.status < 300:
            raise CatalogError("The model catalog could not be refreshed.")
        try:
            return json.loads(reply.body)
        except (ValueError, UnicodeError):
            raise CatalogError("The model catalog returned invalid JSON.") from None

    def _load(self, credential, identity):
        models = self._get(credential, "/models/list")
        try:
            videos = self._get(credential, "/video/config")
        except Exception:
            videos = None
        previous = self.cache.peek(identity).get("videos", [])
        return build_catalog_snapshot(models, videos, previous_videos=previous)

    @staticmethod
    def _result(snapshot, identity, scope):
        result = {**snapshot, **scope, "identity": identity}
        result["image_models"] = build_model_options(
            result.get("models", []), result.get("videos", []), "image"
        )
        result["video_models"] = build_model_options(
            result.get("models", []), result.get("videos", []), "video"
        )
        return result

    def read(self, *, force=False):
        refresh_error = False
        if self.manager.public().get("mode") == "account":
            try:
                self.manager.refresh()
            except Exception:
                refresh_error = True
        credential, identity, scope = self._scope()
        with self._lock:
            if self._identity is not None and self._identity != identity:
                self.cache.clear()
            self._identity = identity
        if refresh_error:
            snapshot = self.cache.peek(identity)
            snapshot.update(
                stale=True,
                error="Could not confirm the selected account Key. Select an active Key or refresh your account before loading models.",
            )
            return self._result(snapshot, identity, scope)
        snapshot = self.cache.read(
            identity, lambda: self._load(credential, identity), force=force
        )
        try:
            _, current, _ = self._scope()
        except Exception:
            current = None
        if current != identity:
            self.cache.invalidate(identity)
            return self._result(
                {
                    "models": [],
                    "videos": [],
                    "available": False,
                    "stale": True,
                    "refreshing": False,
                    "updatedAt": None,
                    "error": "Account or Key changed. Open the model picker again.",
                },
                identity,
                scope,
            )
        return self._result(snapshot, identity, scope)
