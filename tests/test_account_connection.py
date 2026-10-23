import base64
import hashlib
import json
import os

import pytest

from apixly_media.account import AccountError, AccountManager, ConnectionStore
from apixly_media.client import Response

TOKEN = "apc_" + "s" * 43
META = {
    "connection_id": "connection-one",
    "account": {"id": "owner-one", "name": "QA user", "email": "qa@example.invalid"},
    "selected_key": {
        "id": "1709",
        "name": "studixly-key",
        "masked": "sk-***1234",
        "is_default": True,
    },
    "selection_revision": 1,
}


class Transport:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        status, body = self.replies.pop(0)
        return Response(status, {}, json.dumps(body).encode())


def ready_store(tmp_path):
    store = ConnectionStore(tmp_path / "private" / "connection.json")
    store.save(
        {
            "mode": "account",
            "binding": {"access_token": TOKEN, "expires_at": 10000, **META},
        }
    )
    return store


def test_store_keeps_only_scoped_connection_in_private_atomic_file(tmp_path):
    store = ready_store(tmp_path)
    assert store.load()["binding"]["access_token"] == TOKEN
    if os.name != "nt":
        assert store.path.stat().st_mode & 0o777 == 0o600
        assert store.path.parent.stat().st_mode & 0o777 == 0o700
    assert len(list(store.path.parent.iterdir())) == 1
    with pytest.raises(AccountError):
        store.save(
            {"mode": "account", "binding": {"access_token": TOKEN, "password": "bad"}}
        )


def test_store_refuses_symlinks_without_changing_target(tmp_path):
    target = tmp_path / "target.json"
    target.write_text("keep")
    path = tmp_path / "link.json"
    path.symlink_to(target)
    with pytest.raises(AccountError):
        ConnectionStore(path).load()
    with pytest.raises(AccountError):
        ConnectionStore(path).save({"mode": "manual"})
    assert target.read_text() == "keep"


def test_device_start_keeps_verifier_and_device_code_out_of_public_state(tmp_path):
    transport = Transport(
        [
            (
                200,
                {
                    "flow_id": "flow-one",
                    "device_code": "private-device-code",
                    "user_code": "ABCD1234",
                    "verification_uri": "https://apixly.ai/connect/flow-one",
                    "verification_uri_complete": "https://apixly.ai/connect/flow-one?code=ABCD1234",
                    "expires_in": 600,
                    "interval": 5,
                },
            )
        ]
    )
    store = ConnectionStore(tmp_path / "private" / "connection.json")
    manager = AccountManager(store, transport=transport, now=lambda: 1000)
    public = manager.start()
    assert public["user_code"] == "ABCD1234"
    assert "private-device-code" not in json.dumps(public)
    assert "code_verifier" not in json.dumps(public)
    pending = store.load()["pending"]
    sent = json.loads(transport.calls[0][2]["body"])
    challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(pending["code_verifier"].encode()).digest()
        )
        .decode()
        .rstrip("=")
    )
    assert sent == {
        "client_id": "comfyui",
        "flow": "device",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    assert sent["code_challenge"] != pending["code_verifier"]
    assert manager.start() == public
    assert len(transport.calls) == 1


def test_pending_poll_respects_interval_then_saves_only_connection_token(tmp_path):
    clock = [1000]
    replies = [
        (
            200,
            {
                "flow_id": "flow-one",
                "device_code": "device-secret",
                "user_code": "ABCD1234",
                "verification_uri": "https://apixly.ai/connect/flow-one",
                "verification_uri_complete": "https://apixly.ai/connect/flow-one?code=ABCD1234",
                "expires_in": 600,
                "interval": 5,
            },
        ),
        (400, {"error": "authorization_pending"}),
        (
            200,
            {
                "access_token": TOKEN,
                "token_type": "Bearer",
                "expires_in": 7776000,
                **META,
            },
        ),
    ]
    transport = Transport(replies)
    store = ConnectionStore(tmp_path / "private" / "connection.json")
    manager = AccountManager(store, transport=transport, now=lambda: clock[0])
    manager.start()
    assert manager.poll()["status"] == "pending"
    assert manager.poll()["status"] == "pending"
    assert len(transport.calls) == 2
    clock[0] += 5
    public = manager.poll()
    assert public["connected"] is True
    assert public["selected_key"]["id"] == "1709"
    assert TOKEN not in json.dumps(public)
    assert "pending" not in store.load()
    assert manager.credentials()["token"] == TOKEN
    assert manager.credentials()["base_url"] == "https://apixly.ai/api/integrations/v1"
    assert "s" * 43 not in repr(manager)


def test_expired_binding_never_silently_uses_environment_key(tmp_path, monkeypatch):
    monkeypatch.setenv("APIXLY_API_KEY", "manual-env-key")
    store = ready_store(tmp_path)
    manager = AccountManager(store, transport=Transport([]), now=lambda: 20000)
    with pytest.raises(AccountError, match="connect"):
        manager.credentials()
    assert store.load()["mode"] == "account"
    manager.use_manual()
    assert manager.credentials()["token"] == "manual-env-key"
    assert manager.credentials()["base_url"] == "https://apixly.ai/v1"


def test_key_selection_updates_only_metadata_and_cache_identity(tmp_path):
    store = ready_store(tmp_path)
    changed = {
        **META,
        "selected_key": {
            "id": "1710",
            "name": "Image tests",
            "masked": "sk-***5678",
            "is_default": False,
        },
        "selection_revision": 2,
    }
    transport = Transport([(200, changed)])
    manager = AccountManager(store, transport=transport, now=lambda: 1000)
    old_identity = manager.credentials()["identity"]
    public = manager.select_key("1710")
    assert public["selected_key"]["name"] == "Image tests"
    assert manager.credentials()["identity"] != old_identity
    assert manager.credentials()["token"] == TOKEN
    assert json.loads(transport.calls[0][2]["body"]) == {"key_id": "1710"}
    assert transport.calls[0][2]["headers"]["Authorization"] == "Bearer " + TOKEN
    assert TOKEN not in json.dumps(public)


def test_failed_disconnect_does_not_claim_remote_revocation(tmp_path):
    store = ready_store(tmp_path)
    transport = Transport([(503, {"error": "unavailable"})])
    manager = AccountManager(store, transport=transport, now=lambda: 1000)
    with pytest.raises(AccountError):
        manager.disconnect()
    assert store.load()["binding"]["access_token"] == TOKEN


def test_disconnect_revokes_only_current_connection_and_erases_private_state(tmp_path):
    store = ready_store(tmp_path)
    transport = Transport([(204, {})])
    manager = AccountManager(store, transport=transport, now=lambda: 1000)
    public = manager.disconnect()
    assert public["connected"] is False
    assert "binding" not in store.load()
    assert transport.calls[0][0:2] == (
        "DELETE",
        "https://apixly.ai/api/integrations/connection",
    )
    assert transport.calls[0][2]["headers"]["Authorization"] == "Bearer " + TOKEN


def test_untrusted_verification_uri_never_reaches_ui_or_store(tmp_path):
    transport = Transport(
        [
            (
                200,
                {
                    "flow_id": "flow",
                    "device_code": "device",
                    "user_code": "ABCDEFGH",
                    "verification_uri": "https://evil.example/connect",
                    "verification_uri_complete": "https://evil.example/connect",
                    "expires_in": 600,
                    "interval": 5,
                },
            )
        ]
    )
    store = ConnectionStore(tmp_path / "private" / "connection.json")
    with pytest.raises(AccountError):
        AccountManager(store, transport=transport).start()
    assert "pending" not in store.load()


def test_errors_redact_all_saved_proofs_and_do_not_create_inference_calls(tmp_path):
    store = ready_store(tmp_path)
    transport = Transport([(400, {"error": {"message": "secret=" + TOKEN}})])
    manager = AccountManager(store, transport=transport, now=lambda: 1000)
    with pytest.raises(AccountError) as caught:
        manager.select_key("1710")
    assert TOKEN not in str(caught.value)
    assert len(transport.calls) == 1
    assert all("/v1/" not in call[1] for call in transport.calls)


def test_manual_mode_cannot_use_an_api_key_as_an_account_credential(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("APIXLY_API_KEY", "manual-env-key")
    transport = Transport([])
    manager = AccountManager(
        ConnectionStore(tmp_path / "private" / "connection.json"), transport=transport
    )
    with pytest.raises(AccountError, match="connect|Connect"):
        manager.keys()
    assert transport.calls == []


def test_revoked_account_marks_reconnect_and_never_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APIXLY_API_KEY", "manual-env-key")
    store = ready_store(tmp_path)
    manager = AccountManager(
        store, transport=Transport([(401, {"error": "revoked"})]), now=lambda: 1000
    )
    with pytest.raises(AccountError, match="revoked"):
        manager.refresh()
    assert manager.public()["connected"] is False
    with pytest.raises(AccountError, match="connect"):
        manager.credentials()


def test_authorization_denial_allows_a_new_connection_without_waiting_for_expiry(
    tmp_path,
):
    start = {
        "flow_id": "flow",
        "device_code": "device",
        "user_code": "ABCDEFGH",
        "verification_uri": "https://apixly.ai/connect/flow",
        "verification_uri_complete": "https://apixly.ai/connect/flow",
        "expires_in": 600,
        "interval": 5,
    }
    transport = Transport(
        [
            (200, start),
            (400, {"error": "access_denied"}),
            (200, {**start, "flow_id": "new-flow"}),
        ]
    )
    store = ConnectionStore(tmp_path / "private" / "connection.json")
    manager = AccountManager(store, transport=transport, now=lambda: 1000)
    manager.start()
    with pytest.raises(AccountError):
        manager.poll()
    assert "pending" not in store.load()
    assert manager.start()["flow_id"] == "new-flow"


def test_malformed_credential_types_have_clear_errors_without_value_echo(tmp_path):
    store = ConnectionStore(tmp_path / "private" / "connection.json")
    for patch in [
        {"access_token": 123},
        {"connection_id": ""},
        {"account": {"id": None}},
    ]:
        with pytest.raises(AccountError):
            store.save(
                {
                    "mode": "account",
                    "binding": {
                        "access_token": TOKEN,
                        "expires_at": 10000,
                        **META,
                        **patch,
                    },
                }
            )


def test_verification_url_cannot_embed_a_private_proof(tmp_path):
    start = {
        "flow_id": "flow",
        "device_code": "secret-device",
        "user_code": "ABCDEFGH",
        "verification_uri": "https://apixly.ai/connect/flow",
        "verification_uri_complete": "https://apixly.ai/connect/flow?device_code=secret-device",
        "expires_in": 600,
        "interval": 5,
    }
    store = ConnectionStore(tmp_path / "private" / "connection.json")
    with pytest.raises(AccountError):
        AccountManager(store, transport=Transport([(200, start)])).start()
    assert "pending" not in store.load()


def test_manual_switch_can_restore_the_same_saved_account_without_reauthorization(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("APIXLY_API_KEY", "manual-env-key")
    manager = AccountManager(
        ready_store(tmp_path), transport=Transport([]), now=lambda: 1000
    )
    manager.use_manual()
    assert manager.credentials()["mode"] == "manual"
    manager.use_account()
    assert manager.credentials()["token"] == TOKEN
    assert manager.public()["selected_key"]["id"] == "1709"


def test_pending_public_descriptor_can_resume_and_cancel_without_exposing_proofs(
    tmp_path,
):
    start = {
        "flow_id": "flow",
        "device_code": "device-secret",
        "user_code": "ABCDEFGH",
        "verification_uri": "https://apixly.ai/connect/flow",
        "verification_uri_complete": "https://apixly.ai/connect/flow",
        "expires_in": 600,
        "interval": 5,
    }
    store = ConnectionStore(tmp_path / "private" / "connection.json")
    manager = AccountManager(
        store, transport=Transport([(200, start)]), now=lambda: 1000
    )
    descriptor = manager.start()
    assert manager.public()["authorization"] == descriptor
    assert "device-secret" not in json.dumps(manager.public())
    assert "code_verifier" not in json.dumps(manager.public())
    assert manager.cancel()["connected"] is False
    assert "pending" not in store.load()


def test_disconnect_cannot_silently_activate_a_different_manual_key(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("APIXLY_API_KEY", "a-different-billing-key")
    manager = AccountManager(
        ready_store(tmp_path), transport=Transport([(204, {})]), now=lambda: 1000
    )
    manager.disconnect()
    with pytest.raises(AccountError, match="connect"):
        manager.credentials()
    manager.use_manual()
    assert manager.credentials()["token"] == "a-different-billing-key"


def test_already_revoked_connection_can_be_removed_locally(tmp_path):
    manager = AccountManager(
        ready_store(tmp_path),
        transport=Transport([(401, {"error": "invalid_token"})]),
        now=lambda: 1000,
    )
    assert manager.disconnect()["connected"] is False
    assert "binding" not in manager.store.load()
