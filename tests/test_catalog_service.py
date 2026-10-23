import json
import threading

import pytest

from apixly_media.catalog_service import CatalogService
from apixly_media.client import Response


class Manager:
    def __init__(self):
        self.mode = "account"
        self.revision = 1
        self.refreshes = 0
        self.refresh_error = False

    def public(self):
        return {
            "mode": self.mode,
            "connected": True,
            "connection_id": "connection-a",
            "account": {"id": "7"},
            "selected_key": {"id": "studixly"},
            "selection_revision": self.revision,
        }

    def refresh(self):
        self.refreshes += 1
        if self.refresh_error:
            raise RuntimeError("private credential must not be exposed")
        return self.public()

    def credentials(self):
        return {
            "mode": self.mode,
            "token": "private-connection-token"
            if self.mode == "account"
            else "private-manual-key",
            "base_url": "https://apixly.ai/api/integrations/v1"
            if self.mode == "account"
            else "https://apixly.ai/v1",
        }


class Transport:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.block = None

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.block and url.endswith("/models/list"):
            self.block.wait(2)
        if self.fail:
            raise RuntimeError("private-manual-key leaked network exception")
        data = (
            [
                {"id": "image-exact", "type": "image", "name": "Image"},
                {"id": "video-exact", "type": "video", "name": "Video"},
            ]
            if url.endswith("/models/list")
            else [{"model": "video-exact", "modes": ["text2video"]}]
        )
        return Response(200, {}, json.dumps({"data": data}).encode())


def test_catalog_is_lazy_current_key_scoped_and_never_generates():
    manager, transport = Manager(), Transport()
    service = CatalogService(manager, transport=transport)
    assert not transport.calls
    result = service.read()
    assert [row["id"] for row in result["image_models"]] == ["image-exact"]
    assert [row["id"] for row in result["video_models"]] == ["video-exact"]
    assert manager.refreshes == 1
    assert all(call[0] == "GET" for call in transport.calls)
    assert "private-connection-token" not in json.dumps(result)
    service.read()
    assert manager.refreshes == 2
    assert len(transport.calls) == 2
    manager.revision = 2
    changed = service.read()
    assert changed["identity"] != result["identity"]
    assert len(transport.calls) == 4
    service.close()


def test_failed_refresh_keeps_only_same_identity_stale_options_without_secret_errors():
    manager, transport = Manager(), Transport()
    service = CatalogService(manager, transport=transport)
    initial = service.read()
    transport.fail = True
    failed = service.read(force=True)
    assert failed["stale"] and failed["image_models"] == initial["image_models"]
    assert "private" not in json.dumps(failed)
    manager.refresh_error = True
    account_failed = service.read()
    assert account_failed["stale"] and account_failed["error"]
    manager.revision = 2
    changed = service.read()
    assert not changed["image_models"]
    service.close()


def test_old_inflight_response_is_discarded_after_key_changes():
    manager, transport = Manager(), Transport()
    service = CatalogService(manager, transport=transport)
    gate = threading.Event()
    transport.block = gate
    results = []
    worker = threading.Thread(target=lambda: results.append(service.read()))
    worker.start()
    while not transport.calls:
        threading.Event().wait(0.001)
    manager.revision = 2
    gate.set()
    worker.join(3)
    assert results and not results[0]["available"]
    assert results[0]["image_models"] == []
    service.close()


def test_manual_mode_does_not_refresh_account_or_accept_other_credential_hosts():
    manager, transport = Manager(), Transport()
    manager.mode = "manual"
    service = CatalogService(manager, transport=transport)
    service.read()
    assert manager.refreshes == 0
    manager.credentials = lambda: {
        "mode": "manual",
        "token": "private-manual-key",
        "base_url": "https://attacker.test/v1",
    }
    with pytest.raises(ValueError, match="official Apixly"):
        service.read(force=True)
    assert len(transport.calls) == 2
    service.close()
