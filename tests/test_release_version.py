import json
import re
from pathlib import Path

from apixly_media.client import ApixlyClient, Response


def test_release_version_matches_api_and_media_user_agents():
    calls = []

    class Transport:
        def request(self, method, url, **kwargs):
            calls.append(kwargs["headers"])
            if "/video/config" in url:
                return Response(200, {}, json.dumps({"data": []}).encode())
            return Response(
                200, {"content-type": "image/png"}, b"\x89PNG\r\n\x1a\nfixture"
            )

    api = ApixlyClient("offline-test-key", transport=Transport())
    api._json("GET", "/video/config")
    api._media("https://media.example/image.png", max_bytes=100)
    metadata = (Path(__file__).parents[1] / "pyproject.toml").read_text()
    version_match = re.search(r'^version = "([^"]+)"$', metadata, re.MULTILINE)
    assert version_match is not None
    version = version_match.group(1)
    assert [headers["User-Agent"] for headers in calls] == [
        f"comfyui-apixly/{version}",
        f"comfyui-apixly/{version}",
    ]
