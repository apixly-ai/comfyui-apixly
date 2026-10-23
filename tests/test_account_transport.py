import hashlib

import pytest

from apixly_media.account import AccountManager, ConnectionStore
from apixly_media.client import ApixlyClient, ApixlyError, Response, UnknownSubmission
from apixly_media.nodes import _fingerprint

TOKEN = "apc_" + "s" * 43
IDENTITY = hashlib.sha256(b"account:owner:studixly:1").hexdigest()


class Transport:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.replies.pop(0)


def account_client(transport=None, token=TOKEN, identity=IDENTITY):
    return ApixlyClient(
        token, auth_mode="account", identity=identity, transport=transport
    )


def test_account_calls_use_only_scoped_relay_not_direct_gateway():
    transport = Transport([Response(200, {}, b'{"data":[]}')])
    account_client(transport)._json("GET", "/models/list")
    method, url, request = transport.calls[0]
    assert (method, url) == ("GET", "https://apixly.ai/api/integrations/v1/models/list")
    assert request["headers"]["Authorization"] == "Bearer " + TOKEN
    assert TOKEN not in repr(account_client(Transport([])))


def test_account_video_fallback_strips_token_after_redirect(tmp_path):
    video = b"\x00\x00\x00\x18ftypmp42" + b"sample" * 8
    transport = Transport(
        [
            Response(302, {"location": "https://media.example/clip.mp4"}, b""),
            Response(200, {"content-type": "video/mp4"}, video),
        ]
    )
    account_client(transport).download_video(
        {"id": "123", "status": "succeeded"}, tmp_path / "clip.mp4"
    )
    assert (
        transport.calls[0][1]
        == "https://apixly.ai/api/integrations/v1/videos/123/content"
    )
    assert transport.calls[0][2]["headers"]["Authorization"] == "Bearer " + TOKEN
    assert "Authorization" not in transport.calls[1][2]["headers"]


def test_account_token_is_not_an_authentication_for_direct_or_foreign_content():
    transport = Transport([])
    for url in [
        "https://apixly.ai/v1/videos/123/content",
        "https://media.example/videos/123/content",
        "https://apixly.ai/api/integrations/v1/models/list",
    ]:
        with pytest.raises(ApixlyError):
            account_client(transport)._media(url, authenticated=True, max_bytes=100)
    assert not transport.calls


def test_manual_fingerprint_stays_exactly_compatible_and_account_rotation_is_stable():
    args = ("image", "gemini-3.1-flash-image", "car", {}, 1)
    assert (
        _fingerprint(ApixlyClient("offline-secret"), *args)
        == "b91d4d45d0c464e6ada34f4caa98480077cb479cbf767e4b623ed49c1ac48a06"
    )
    first = account_client(Transport([]))
    rotated = account_client(Transport([]), token="apc_" + "t" * 43)
    other_key = account_client(
        Transport([]), identity=hashlib.sha256(b"other-key").hexdigest()
    )
    assert _fingerprint(first, *args) == _fingerprint(rotated, *args)
    assert _fingerprint(first, *args) != _fingerprint(other_key, *args)


def test_environment_factory_respects_bound_account_and_never_falls_back(monkeypatch):
    monkeypatch.setenv("APIXLY_API_KEY", "legacy-environment-key")
    store = ConnectionStore()
    store.save(
        {
            "mode": "account",
            "binding": {
                "access_token": TOKEN,
                "expires_at": 4000000000,
                "connection_id": "own",
                "account": {"id": "owner"},
                "selected_key": {
                    "id": "studixly",
                    "name": "studixly-key",
                    "is_default": True,
                },
                "selection_revision": 1,
            },
        }
    )
    refreshed = []

    def refresh(manager):
        refreshed.append(True)
        state = manager.store.load()
        state["binding"]["selection_revision"] = 2
        manager.store.save(state)

    monkeypatch.setattr(AccountManager, "refresh", refresh)
    api = ApixlyClient.from_environment()
    assert refreshed == [True]
    assert (
        api.fingerprint_identity == hashlib.sha256(b"account:owner:studixly:2").digest()
    )
    assert api._api_key == TOKEN
    assert api.base_url == "https://apixly.ai/api/integrations/v1"
    state = store.load()
    state["binding"]["needs_reconnect"] = True
    store.save(state)
    with pytest.raises(ApixlyError, match="connect"):
        ApixlyClient.from_environment()


def test_broker_unknown_post_never_retries_or_exposes_token():
    transport = Transport(
        [
            Response(
                502,
                {},
                b'{"error":{"type":"submission_unknown","code":"submission_unknown"},"submission_outcome":"unknown","automatic_retry":false}',
            )
        ]
    )
    with pytest.raises(UnknownSubmission, match="submission_unknown") as error:
        account_client(transport).submit_image("grok-imagine-image", "car")
    assert len(transport.calls) == 1
    assert TOKEN not in str(error.value)
