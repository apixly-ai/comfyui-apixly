import json

import pytest

from apixly_media.client import (
    ApixlyClient,
    ApixlyError,
    PollTimeout,
    Response,
    UnknownSubmission,
)


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, *, headers, body=None, timeout=60, max_bytes=None):
        self.calls.append((method, url, headers, body, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def response(data, status=200, headers=None):
    return Response(
        status,
        headers or {"content-type": "application/json"},
        json.dumps(data).encode(),
    )


def client(responses):
    transport = Transport(responses)
    return ApixlyClient("secret-test-key", transport=transport), transport


def test_image_submission_preserves_model_and_all_parameters():
    api, transport = client([response({"id": "120", "status": "queued"})])
    job = api.submit_image(
        "exact/model-id", "a blue glass", {"quality": "high", "n": 2}
    )
    method, url, headers, body, _ = transport.calls[0]
    assert job["id"] == "120"
    assert (method, url) == ("POST", "https://apixly.ai/v1/images/generations")
    assert headers["Authorization"] == "Bearer secret-test-key"
    assert json.loads(body) == {
        "model": "exact/model-id",
        "prompt": "a blue glass",
        "async": True,
        "quality": "high",
        "n": 2,
    }


@pytest.mark.parametrize(
    "field",
    [
        "model",
        "prompt",
        "async",
        "image",
        "image[]",
        "mask",
        "api_key",
        "Authorization",
    ],
)
def test_image_parameters_cannot_override_credentials_or_core_fields(field):
    api, transport = client([])
    with pytest.raises(ValueError):
        api.submit_image("exact", "prompt", {field: "override"})
    assert not transport.calls


def test_reference_edit_uses_multipart_for_every_reference_and_mask():
    api, transport = client([response({"id": "121"})])
    api.submit_image(
        "gpt-image-exact",
        "edit",
        {"size": "1024x1024"},
        images=[b"first-png", b"second-png"],
        mask=b"mask-png",
    )
    _, url, headers, body, _ = transport.calls[0]
    assert url.endswith("/images/edits")
    assert headers["Content-Type"].startswith("multipart/form-data; boundary=")
    assert body.count(b'name="image[]";') == 2
    assert b'name="mask";' in body
    assert all(
        value in body
        for value in [
            b"first-png",
            b"second-png",
            b"mask-png",
            b"gpt-image-exact",
            b"true",
        ]
    )


def test_mask_without_reference_is_rejected_before_spending():
    api, transport = client([])
    with pytest.raises(ValueError, match="reference"):
        api.submit_image("model", "prompt", mask=b"mask")
    assert not transport.calls


@pytest.mark.parametrize(
    "result",
    [
        OSError("socket timed out secret-test-key"),
        response({}, 200),
        response({"error": {"message": "unavailable"}}, 502),
    ],
)
def test_uncertain_paid_post_is_attempted_once_and_redacts_key(result):
    api, transport = client([result])
    with pytest.raises(UnknownSubmission) as exc:
        api.submit_video("exact-video", "prompt", {"seconds": 5})
    assert len(transport.calls) == 1
    assert "secret-test-key" not in str(exc.value)
    assert "Do not submit again" in str(exc.value)


def test_submit_http_400_is_known_rejection_and_is_not_retried():
    api, transport = client(
        [
            response(
                {
                    "error": {
                        "code": "invalid_request_error",
                        "message": "wrong seconds",
                    }
                },
                400,
            )
        ]
    )
    with pytest.raises(ApixlyError, match="wrong seconds") as exc:
        api.submit_video("exact", "prompt")
    assert not isinstance(exc.value, UnknownSubmission)
    assert len(transport.calls) == 1


def test_video_submission_uses_current_flat_rest_contract_and_does_not_rename_model():
    api, transport = client([response({"id": "122", "status": "queued"})])
    api.submit_video(
        "seedance-2.5",
        "shot",
        {
            "seconds": 5,
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "videos": ["https://media.example/ref.mp4"],
        },
        images=["data:image/png;base64,eA=="],
    )
    assert transport.calls[0][1] == "https://apixly.ai/v1/videos"
    body = json.loads(transport.calls[0][3])
    assert body == {
        "model": "seedance-2.5",
        "prompt": "shot",
        "seconds": 5,
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "videos": ["https://media.example/ref.mp4"],
        "images": ["data:image/png;base64,eA=="],
    }


def test_wait_only_retries_safe_status_gets_and_respects_deadline():
    api, transport = client(
        [
            response({}, 503),
            response({"id": "123", "status": "in_progress"}),
            response(
                {
                    "id": "123",
                    "status": "completed",
                    "url": "https://media.example/a.mp4",
                }
            ),
        ]
    )
    ticks = [0.0]
    job = api.wait_job(
        "video",
        "123",
        timeout_seconds=20,
        poll_interval=2,
        clock=lambda: ticks[0],
        sleep=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds),
    )
    assert job["status"] == "completed"
    assert len(transport.calls) == 3
    assert all(call[0] == "GET" for call in transport.calls)


def test_timeout_keeps_task_id_and_never_resubmits():
    api, transport = client([response({"status": "in_progress"})] * 4)
    ticks = [0.0]
    with pytest.raises(PollTimeout, match="124"):
        api.wait_job(
            "image",
            "124",
            timeout_seconds=3,
            poll_interval=2,
            clock=lambda: ticks[0],
            sleep=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds),
        )
    assert all(call[0] == "GET" for call in transport.calls)
    assert ticks[0] <= 3


@pytest.mark.parametrize("status", ["failed", "expired", "unknown_future_status"])
def test_terminal_or_unknown_status_does_not_loop(status):
    api, transport = client(
        [
            response(
                {
                    "id": "125",
                    "status": status,
                    "error": {"message": "terminal problem"},
                }
            )
        ]
    )
    with pytest.raises(ApixlyError):
        api.wait_job("image", "125", timeout_seconds=10)
    assert len(transport.calls) == 1


def test_completed_image_without_signed_url_can_be_queried_again():
    api, transport = client(
        [
            response({"id": "126", "status": "succeeded"}),
            response(
                {
                    "id": "126",
                    "status": "succeeded",
                    "data": [{"url": "https://media.example/a.png"}],
                }
            ),
        ]
    )
    job = api.wait_job("image", "126", timeout_seconds=5, poll_interval=0.01)
    assert job["data"][0]["url"].endswith("a.png")
    assert len(transport.calls) == 2


@pytest.mark.parametrize(
    "task_id", ["../9", "9?secret", "9/evil", "", "9\n", "https://evil.example"]
)
def test_task_ids_cannot_change_the_authenticated_request_path(task_id):
    api, transport = client([])
    with pytest.raises(ValueError):
        api.get_job("video", task_id)
    assert not transport.calls


def test_public_media_redirects_never_receive_authorization(tmp_path):
    api, transport = client(
        [
            Response(302, {"location": "https://cdn.example/clip.mp4"}, b""),
            Response(
                200, {"content-type": "video/mp4"}, b"\x00\x00\x00\x18ftypisomvideo"
            ),
        ]
    )
    destination = tmp_path / "clip.mp4"
    api.download_video(
        {
            "id": "127",
            "status": "completed",
            "url": "https://apixly.ai/v1/videos/content?ref=signed",
        },
        destination,
    )
    assert destination.read_bytes().endswith(b"video")
    assert len(transport.calls) == 2
    assert all("Authorization" not in call[2] for call in transport.calls)


def test_authenticated_content_fallback_does_not_forward_key_on_redirect(tmp_path):
    api, transport = client(
        [
            Response(302, {"location": "https://cdn.example/clip.mp4"}, b""),
            Response(
                200, {"content-type": "video/mp4"}, b"\x00\x00\x00\x18ftypisomvideo"
            ),
        ]
    )
    api.download_video({"id": "128", "status": "completed"}, tmp_path / "clip.mp4")
    assert transport.calls[0][1] == "https://apixly.ai/v1/videos/128/content"
    assert transport.calls[0][2]["Authorization"] == "Bearer secret-test-key"
    assert "Authorization" not in transport.calls[1][2]


@pytest.mark.parametrize(
    "location",
    [
        "http://cdn.example/clip.mp4",
        "file:///etc/passwd",
        "https://user:password@cdn.example/clip.mp4",
    ],
)
def test_unsafe_download_redirect_is_blocked(tmp_path, location):
    api, transport = client([Response(302, {"location": location}, b"")])
    with pytest.raises(ApixlyError):
        api.download_video(
            {
                "id": "129",
                "status": "completed",
                "url": "https://media.example/clip.mp4",
            },
            tmp_path / "clip.mp4",
        )
    assert len(transport.calls) == 1
    assert not (tmp_path / "clip.mp4").exists()


def test_non_video_body_is_not_delivered_as_a_terminal_video(tmp_path):
    api, _ = client(
        [Response(200, {"content-type": "text/html"}, b"<html>login</html>")]
    )
    with pytest.raises(ApixlyError, match="video"):
        api.download_video(
            {
                "id": "130",
                "status": "completed",
                "url": "https://media.example/clip.mp4",
            },
            tmp_path / "clip.mp4",
        )
    assert not list(tmp_path.iterdir())


def test_api_redirects_are_rejected_without_following_them():
    api, transport = client([Response(307, {"location": "https://evil.example"}, b"")])
    with pytest.raises(UnknownSubmission):
        api.submit_video("exact", "prompt")
    assert len(transport.calls) == 1


def test_environment_key_is_read_only_when_executing(monkeypatch):
    monkeypatch.delenv("APIXLY_API_KEY", raising=False)
    with pytest.raises(ValueError, match="APIXLY_API_KEY"):
        ApixlyClient.from_environment()
    monkeypatch.setenv("APIXLY_API_KEY", "private-env-key")
    assert "private-env-key" not in repr(ApixlyClient.from_environment())


def test_successful_status_payload_cannot_echo_the_api_key_into_receipts():
    api, _ = client(
        [
            response(
                {
                    "id": "131",
                    "status": "failed",
                    "error": {"message": "rejected secret-test-key"},
                }
            )
        ]
    )
    job = api.get_job("video", "131")
    assert "secret-test-key" not in json.dumps(job)


def test_standard_transport_really_stops_redirects_and_bounds_response_bytes():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from apixly_media.client import StandardTransport

    paths = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/secret-target")
                self.end_headers()
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"too-large-body")

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        transport = StandardTransport()
        url = f"http://127.0.0.1:{server.server_port}"
        result = transport.request(
            "GET", url + "/redirect", headers={"Authorization": "Bearer sentinel"}
        )
        assert result.status == 302
        assert paths == ["/redirect"]
        with pytest.raises(ApixlyError, match="size limit"):
            transport.request("GET", url + "/large", headers={}, max_bytes=4)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert not thread.is_alive()


def test_transport_reads_large_media_incrementally_instead_of_one_large_read():
    from io import BytesIO

    from apixly_media.client import StandardTransport

    class Stream(BytesIO):
        code = 200
        headers = {"content-type": "image/jpeg"}

        def read(self, size=-1):
            assert 0 < size <= 65536
            return super().read(size)

    class Opener:
        def open(self, request, timeout):
            return Stream(b"x" * 103582)

    transport = StandardTransport()
    transport.opener = Opener()
    result = transport.request(
        "GET", "https://media.example/image", headers={}, max_bytes=200000
    )
    assert len(result.body) == 103582


def test_interrupted_media_get_can_retry_without_any_generation_post(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("apixly_media.client.time.sleep", lambda _: None)
    api, transport = client(
        [
            OSError("interrupted transfer"),
            Response(
                200, {"content-type": "video/mp4"}, b"\x00\x00\x00\x18ftypisomvideo"
            ),
        ]
    )
    path = api.download_video(
        {"id": "132", "status": "completed", "url": "https://media.example/clip.mp4"},
        tmp_path / "clip.mp4",
    )
    assert path.exists()
    assert len(transport.calls) == 2
    assert all(
        call[0] == "GET" and "Authorization" not in call[2] for call in transport.calls
    )


def test_default_httpx_transport_handles_real_redirect_responses_without_leaking_key(
    tmp_path, monkeypatch
):
    import httpx

    from apixly_media.client import HTTPXTransport

    actual_client = httpx.Client
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path == "/v1/images/generations":
            return httpx.Response(200, json={"id": "133", "status": "queued"})
        if request.url.host == "media.example":
            return httpx.Response(
                302, headers={"location": "https://cdn.example/clip.mp4"}
            )
        return httpx.Response(
            200,
            headers={"content-type": "video/mp4"},
            content=b"\x00\x00\x00\x18ftypisomvideo",
        )

    def factory(**kwargs):
        assert kwargs["follow_redirects"] is False
        return actual_client(**kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(httpx, "Client", factory)
    api = ApixlyClient("sentinel-test-key")
    assert isinstance(api.transport, HTTPXTransport)
    assert api.submit_image("exact", "prompt")["id"] == "133"
    api.download_video(
        {"id": "133", "status": "completed", "url": "https://media.example/clip.mp4"},
        tmp_path / "clip.mp4",
    )
    assert len(requests) == 3
    assert requests[0].headers["authorization"] == "Bearer sentinel-test-key"
    assert all("authorization" not in request.headers for request in requests[1:])


def test_wait_reports_actual_task_progress_without_any_extra_post():
    api, transport = client(
        [
            response({"id": "134", "status": "in_progress", "progress": 35}),
            response({"id": "134", "status": "completed", "progress": 100}),
        ]
    )
    seen = []
    api.wait_job(
        "video",
        "134",
        poll_interval=0.01,
        on_progress=lambda job: seen.append(job.get("progress")),
    )
    assert seen == [35, 100]
    assert all(call[0] == "GET" for call in transport.calls)
