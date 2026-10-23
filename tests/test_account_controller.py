import json

import pytest

from apixly_media.server import AccountController, ControllerError


class Manager:
    def __init__(self):
        self.calls = []
        self.mode = "manual"
        self.revision = 1

    def public(self):
        return {
            "mode": self.mode,
            "connected": self.mode == "account",
            "account": {"id": "7"},
            "selected_key": {"id": "studixly"},
            "selection_revision": self.revision,
        }

    def keys(self):
        self.calls.append("keys")
        return {
            "data": [
                {
                    "id": "studixly",
                    "name": "Default",
                    "masked": "••••1234",
                    "status": "active",
                    "is_default": True,
                }
            ],
            "selected_key_id": "studixly",
            "selection_revision": self.revision,
        }

    def start(self):
        self.calls.append("begin")

    def poll(self):
        self.calls.append("poll")
        self.mode = "account"

    def cancel(self):
        self.calls.append("cancel")

    def refresh(self):
        self.calls.append("refresh")

    def select_key(self, key_id):
        self.calls.append(("select_key", key_id))
        self.revision += 1

    def disconnect(self):
        self.calls.append("disconnect")
        self.mode = "account"

    def use_manual(self):
        self.calls.append("use_manual")
        self.mode = "manual"

    def use_account(self):
        self.calls.append("use_account")
        self.mode = "account"


LOCAL = {"host": "127.0.0.1:8189", "remote": "127.0.0.1", "origin": None}


def test_state_projects_only_metadata_and_server_manual_key_availability(monkeypatch):
    monkeypatch.setenv("APIXLY_API_KEY", "never-browser-key")
    manager = Manager()
    controller = AccountController(manager)
    result = controller.state(**LOCAL)
    assert result["manual_key_available"] is True
    assert len(result["csrf_token"]) >= 32
    assert "never-browser-key" not in json.dumps(result)
    assert not manager.calls
    assert controller.state(**LOCAL)["csrf_token"] == result["csrf_token"]


@pytest.mark.parametrize(
    "origin,remote",
    [
        ("https://evil.test", "127.0.0.1"),
        ("null", "127.0.0.1"),
        (None, "192.0.2.9"),
        ("http://127.0.0.1:8190", "127.0.0.1"),
    ],
)
def test_foreign_origins_and_nonlocal_no_origin_cannot_read_state(origin, remote):
    controller = AccountController(Manager())
    with pytest.raises(ControllerError):
        controller.state(origin=origin, remote=remote, host="127.0.0.1:8189")


def test_actions_need_csrf_and_explicit_allowlist_then_use_native_manager_methods():
    manager = Manager()
    controller = AccountController(manager)
    nonce = controller.state(**LOCAL)["csrf_token"]
    with pytest.raises(ControllerError):
        controller.action({"action": "begin"}, csrf="wrong", **LOCAL)
    with pytest.raises(ControllerError):
        controller.action(
            {"action": "begin", "api_key": "injected"}, csrf=nonce, **LOCAL
        )
    assert not manager.calls
    for action in ("begin", "poll", "cancel", "refresh", "use_manual", "use_account"):
        result = controller.action({"action": action}, csrf=nonce, **LOCAL)
        assert "account" in result
        if action == "poll":
            assert "keys" in result
    controller.action({"action": "select_key", "key_id": "42"}, csrf=nonce, **LOCAL)
    assert ("select_key", "42") in manager.calls
    assert not any("generate" in str(call) for call in manager.calls)
    controller.action({"action": "disconnect"}, csrf=nonce, **LOCAL)
    assert "disconnect" in manager.calls


def test_same_origin_and_ipv6_loopback_work_but_get_keys_remains_opt_in():
    manager = Manager()
    controller = AccountController(manager)
    manager.mode = "account"
    result = controller.state(
        host="localhost:8189",
        origin="http://localhost:8189",
        remote="::1",
        include_keys=True,
    )
    assert result["keys"]["selected_key_id"] == "studixly"
    assert manager.calls == ["keys"]
