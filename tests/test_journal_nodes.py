import json
import sys
from pathlib import Path

import pytest

from apixly_media.client import ApixlyClient, UnknownSubmission
from apixly_media.journal import SubmissionJournal
from apixly_media.nodes import NODE_CLASS_MAPPINGS


def test_submission_journal_reuses_one_nonce_but_allows_an_explicit_new_action(
    tmp_path,
):
    journal = SubmissionJournal(tmp_path / "submissions.sqlite3")
    calls = []

    def submit():
        calls.append(1)
        return {"id": "201", "status": "queued"}

    first = journal.submit_once("fingerprint-nonce-1", submit)
    second = journal.submit_once("fingerprint-nonce-1", submit)
    journal.submit_once("fingerprint-nonce-2", submit)
    assert first == second
    assert len(calls) == 2
    assert (tmp_path / "submissions.sqlite3").stat().st_mode & 0o777 == 0o600


def test_uncertain_submission_is_persisted_and_never_reposted(tmp_path):
    journal = SubmissionJournal(tmp_path / "submissions.sqlite3")
    calls = []

    def submit():
        calls.append(1)
        raise UnknownSubmission("Unknown outcome. Do not submit again.")

    with pytest.raises(UnknownSubmission):
        journal.submit_once("uncertain", submit)
    with pytest.raises(UnknownSubmission, match="existing"):
        journal.submit_once("uncertain", submit)
    assert calls == [1]
    assert "unknown" in (tmp_path / "submissions.sqlite3").read_bytes().decode(
        errors="ignore"
    )


def test_known_rejected_nonce_does_not_repeat_a_paid_action(tmp_path):
    from apixly_media.client import ApixlyError

    journal = SubmissionJournal(tmp_path / "submissions.sqlite3")
    calls = []

    def submit():
        calls.append(1)
        raise ApixlyError("Rejected")

    for _ in range(2):
        with pytest.raises(ApixlyError):
            journal.submit_once("rejected", submit)
    assert calls == [1]


def test_journal_does_not_store_prompt_or_key_or_raw_receipt(tmp_path):
    journal = SubmissionJournal(tmp_path / "submissions.sqlite3")
    journal.submit_once(
        "digest-only",
        lambda: {
            "id": "202",
            "status": "queued",
            "prompt": "private-source-prompt",
            "key": "sk-private-key",
        },
    )
    raw = (tmp_path / "submissions.sqlite3").read_bytes()
    assert b"private-source-prompt" not in raw
    assert b"sk-private-key" not in raw


def test_all_nodes_have_no_secret_inputs_or_credential_outputs():
    assert len(NODE_CLASS_MAPPINGS) >= 5
    for node in NODE_CLASS_MAPPINGS.values():
        spec = node.INPUT_TYPES()
        names = (
            set(spec.get("required", {}))
            | set(spec.get("optional", {}))
            | set(spec.get("hidden", {}))
        )
        assert not any(
            "key" in name.lower()
            or "token" in name.lower()
            or "authorization" in name.lower()
            for name in names
        )
        assert not any(
            "key" in name.lower() or "token" in name.lower()
            for name in getattr(node, "RETURN_NAMES", ())
        )


def test_image_tensor_encoding_uses_every_reference_without_metadata():
    from io import BytesIO

    import numpy as np
    import torch
    from PIL import Image

    from apixly_media.nodes import encode_images

    images = torch.from_numpy(np.zeros((2, 8, 9, 3), dtype=np.float32))
    encoded = encode_images(images)
    assert len(encoded) == 2
    with Image.open(BytesIO(encoded[0])) as image:
        assert image.size == (9, 8)
        assert not image.info


def test_mask_follows_comfy_convention_one_means_repaint():
    from io import BytesIO

    import numpy as np
    import torch
    from PIL import Image

    from apixly_media.nodes import encode_mask

    data = torch.from_numpy(np.array([[[1.0, 0.0], [0.5, 1.0]]], dtype=np.float32))
    with Image.open(BytesIO(encode_mask(data, 2, 2))) as mask:
        assert mask.mode == "RGBA"
        assert mask.getpixel((0, 0))[3] == 0
        assert mask.getpixel((1, 0))[3] == 255


def test_image_submit_node_round_trip_and_no_resubmit_on_repeat(tmp_path, monkeypatch):
    import numpy as np
    import torch

    calls = []
    api = ApixlyClient("secret")
    api.submit_image = lambda model, prompt, params, **kw: (
        calls.append((model, prompt, params, kw)) or {"id": "203", "status": "queued"}
    )
    monkeypatch.setattr(ApixlyClient, "from_environment", classmethod(lambda cls: api))
    monkeypatch.setenv("APIXLY_STATE_DIR", str(tmp_path))
    node = NODE_CLASS_MAPPINGS["ApixlyImageEdit"]()
    images = torch.from_numpy(np.zeros((1, 8, 8, 3), dtype=np.float32))
    a = node.submit(
        "gpt-image-exact", "prompt", '{"quality":"high"}', 1, reference_images=images
    )
    b = node.submit(
        "gpt-image-exact", "prompt", '{"quality":"high"}', 1, reference_images=images
    )
    c = node.submit(
        "gpt-image-exact", "prompt", '{"quality":"high"}', 2, reference_images=images
    )
    assert a["result"][0] == b["result"][0] == c["result"][0] == "203"
    assert len(calls) == 2
    assert "secret" not in json.dumps(a)
    assert calls[0][3]["images"][0].startswith(b"\x89PNG")


def test_image_result_has_native_thumbnail_and_receipt(tmp_path, monkeypatch):
    import types

    import numpy as np
    import torch

    from apixly_media import nodes

    api = ApixlyClient("secret")
    api.wait_job = lambda *args, **kwargs: {
        "id": "205",
        "status": "succeeded",
        "data": [{"url": "https://media.example/image.png"}],
    }
    api.image_bytes = lambda job: nodes.encode_images(
        torch.from_numpy(np.zeros((1, 8, 8, 3), dtype=np.float32))
    )
    monkeypatch.setattr(ApixlyClient, "from_environment", classmethod(lambda cls: api))
    monkeypatch.setitem(
        sys.modules,
        "folder_paths",
        types.SimpleNamespace(get_temp_directory=lambda: str(tmp_path)),
    )
    result = nodes.ApixlyImageResult().result("205")
    preview = result["ui"]["images"][0]
    assert (tmp_path / preview["subfolder"] / preview["filename"]).exists()
    assert preview["type"] == "temp"
    assert result["ui"]["apixly"][0]["task_id"] == "205"
    assert result["result"][0].shape == (1, 8, 8, 3)


def test_video_result_uses_native_video_preview_and_download_location(
    tmp_path, monkeypatch
):
    import types

    from apixly_media import nodes

    api = ApixlyClient("secret")
    api.wait_job = lambda *args, **kwargs: {
        "id": "206",
        "status": "completed",
        "url": "https://media.example/video.mp4",
    }

    def download(job, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"video")
        return path

    api.download_video = download
    monkeypatch.setattr(ApixlyClient, "from_environment", classmethod(lambda cls: api))
    monkeypatch.setitem(
        sys.modules,
        "folder_paths",
        types.SimpleNamespace(get_output_directory=lambda: str(tmp_path)),
    )
    result = nodes.ApixlyVideoResult().result("206")
    assert result["ui"]["animated"] == [True]
    assert result["ui"]["images"][0]["type"] == "output"
    assert Path(result["result"][0]).exists()


def test_edit_node_recommends_explicit_qualified_model_and_requires_reference():
    node = NODE_CLASS_MAPPINGS["ApixlyImageEdit"]
    required = node.INPUT_TYPES()["required"]
    assert required["model"][1]["default"] == "gemini-3.1-flash-image"
    assert required["reference_images"][0] == "IMAGE"


def test_video_node_exposes_duration_resolution_and_aspect_ratio():
    required = NODE_CLASS_MAPPINGS["ApixlyVideoSubmit"].INPUT_TYPES()["required"]
    assert required["seconds"][1]["default"] == 3
    assert "720p" in required["resolution"][0]
    assert "16:9" in required["aspect_ratio"][0]


def test_task_identity_survives_comfy_cached_ui_asset_id_cleanup():
    from apixly_media.nodes import _ui_result

    ui = _ui_result(("207",), {"id": "207", "status": "queued"}, "video")["ui"]
    # ComfyUI comfy_execution.asset_enrichment._strip_ids removes top-level `id`
    # from every dictionary in every UI list when replaying cached outputs.
    for entries in ui.values():
        if isinstance(entries, (list, tuple)):
            for entry in entries:
                if isinstance(entry, dict):
                    entry.pop("id", None)
    assert ui["apixly"][0]["task_id"] == "207"


def test_first_release_does_not_expose_unqualified_mask_inputs():
    for name in ["ApixlyImageSubmit", "ApixlyImageEdit"]:
        specification = NODE_CLASS_MAPPINGS[name].INPUT_TYPES()
        assert "mask" not in specification.get("required", {})
        assert "mask" not in specification.get("optional", {})


def test_unsupported_mask_node_call_is_rejected_before_any_paid_action():
    node = NODE_CLASS_MAPPINGS["ApixlyImageEdit"]()
    with pytest.raises(ValueError, match="not available"):
        node.submit("gpt-image-2", "prompt", "{}", 1, mask=object())


def test_image_generation_node_rejects_references_before_any_paid_action():
    node = NODE_CLASS_MAPPINGS["ApixlyImageSubmit"]()
    specification = node.INPUT_TYPES()
    assert "reference_images" not in specification.get("optional", {})
    with pytest.raises(ValueError, match="Image: Edit"):
        node.submit("grok-imagine-image", "prompt", "{}", 1, reference_images=object())


def test_image_edit_node_requires_a_reference_before_any_paid_action():
    with pytest.raises(ValueError, match="reference"):
        NODE_CLASS_MAPPINGS["ApixlyImageEdit"]().submit(
            "gemini-3.1-flash-image", "prompt", "{}", 1
        )


@pytest.mark.parametrize("known", [True, False])
def test_video_reference_preflight_never_replaces_an_explicit_model(
    tmp_path, monkeypatch, known
):
    import types

    import numpy as np
    import torch

    from apixly_media.client import Response

    model = "grok-imagine-video" if known else "new-model-not-in-capabilities"
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        data = (
            {"data": [{"model": "grok-imagine-video", "modes": ["text2video"]}]}
            if method == "GET"
            else {"id": "208", "status": "queued"}
        )
        return Response(200, {}, json.dumps(data).encode())

    api = ApixlyClient("secret", transport=types.SimpleNamespace(request=request))
    monkeypatch.setattr(ApixlyClient, "from_environment", classmethod(lambda cls: api))
    monkeypatch.setenv("APIXLY_STATE_DIR", str(tmp_path))
    images = torch.from_numpy(np.zeros((1, 8, 8, 3), dtype=np.float32))
    node = NODE_CLASS_MAPPINGS["ApixlyVideoSubmit"]()
    if known:
        with pytest.raises(ValueError, match="grok-imagine-video-1.5-preview"):
            node.submit(model, "prompt", "{}", 1, reference_images=images)
        assert [call[0] for call in calls] == ["GET"]
        assert not list(tmp_path.glob("*.sqlite3"))
    else:
        result = node.submit(model, "prompt", "{}", 1, reference_images=images)
        assert result["result"][0] == "208"
        assert [call[0] for call in calls] == ["GET", "POST"]
        assert json.loads(calls[1][2]["body"])["model"] == model


def test_url_only_video_route_rejects_local_image_before_any_network():
    node = NODE_CLASS_MAPPINGS["ApixlyVideoSubmit"]()
    with pytest.raises(ValueError, match="reference_image_urls"):
        node.submit(
            "grok-imagine-video-1.5-preview",
            "prompt",
            "{}",
            1,
            reference_images=object(),
        )


def test_public_reference_urls_are_forwarded_as_urls_without_local_upload(
    tmp_path, monkeypatch
):
    import io
    import types

    from PIL import Image

    from apixly_media.client import Response

    calls = []
    image = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(image, format="PNG")

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == "GET" and "/video/config" not in url:
            return Response(200, {"content-type": "image/png"}, image.getvalue())
        data = (
            {
                "data": [
                    {
                        "model": "grok-imagine-video-1.5-preview",
                        "modes": ["image2video"],
                    }
                ]
            }
            if method == "GET"
            else {"id": "209", "status": "queued"}
        )
        return Response(200, {}, json.dumps(data).encode())

    api = ApixlyClient("secret", transport=types.SimpleNamespace(request=request))
    monkeypatch.setattr(ApixlyClient, "from_environment", classmethod(lambda cls: api))
    monkeypatch.setenv("APIXLY_STATE_DIR", str(tmp_path))
    references = ["https://apixly.ai/v1/images/content?ref=signed-reference"]
    result = NODE_CLASS_MAPPINGS["ApixlyVideoSubmit"]().submit(
        "grok-imagine-video-1.5-preview",
        "prompt",
        "{}",
        1,
        reference_image_urls=json.dumps(references),
        seconds=3,
        resolution="model_default",
        aspect_ratio="model_default",
    )
    assert result["result"][0] == "209"
    assert [call[0] for call in calls] == ["GET", "GET", "POST"]
    assert "Authorization" not in calls[1][2]["headers"]
    body = json.loads(calls[2][2]["body"])
    assert body["model"] == "grok-imagine-video-1.5-preview"
    assert body["images"] == references
    assert "resolution" not in body
    assert "aspect_ratio" not in body
    assert not any("upload" in call[1] or "assets" in call[1] for call in calls)

    refreshed = ["https://apixly.ai/v1/images/content?ref=fresh-signed-reference"]
    repeated = NODE_CLASS_MAPPINGS["ApixlyVideoSubmit"]().submit(
        "grok-imagine-video-1.5-preview",
        "prompt",
        "{}",
        1,
        reference_image_urls=json.dumps(refreshed),
        seconds=3,
        resolution="model_default",
        aspect_ratio="model_default",
    )
    assert repeated["result"][0] == "209"
    assert len([call for call in calls if call[0] == "POST"]) == 1


@pytest.mark.parametrize(
    "value", ['["data:image/png;base64,eA=="]', "http://example.com/image.png"]
)
def test_video_reference_url_field_requires_public_https_urls(value):
    with pytest.raises(ValueError, match="HTTPS"):
        NODE_CLASS_MAPPINGS["ApixlyVideoSubmit"]().submit(
            "grok-imagine-video-1.5-preview",
            "prompt",
            "{}",
            1,
            reference_image_urls=value,
        )


@pytest.mark.parametrize(
    "value", ["[{}]", '[""]', '["https://media.example/image.png",42]']
)
def test_invalid_reference_members_are_never_silently_discarded(value):
    with pytest.raises(ValueError, match="HTTPS"):
        NODE_CLASS_MAPPINGS["ApixlyVideoSubmit"]().submit(
            "grok-imagine-video", "prompt", "{}", 1, reference_image_urls=value
        )


def test_reference_video_template_uses_an_explicit_url_link():
    path = (
        Path(__file__).parents[1]
        / "example_workflows"
        / "reference-image-to-video.json"
    )
    graph = json.loads(path.read_text())
    submit = next(
        node for node in graph["nodes"] if node["type"] == "ApixlyVideoSubmit"
    )
    assert submit["widgets_values"][0] == "grok-imagine-video-1.5-preview"
    assert (
        next(
            item for item in submit["inputs"] if item["name"] == "reference_image_urls"
        )["link"]
        is not None
    )


def test_unreadable_reference_does_not_submit_a_video_or_claim_the_nonce(
    tmp_path, monkeypatch
):
    api = ApixlyClient("secret")
    api._json = lambda *args, **kwargs: {
        "data": [{"model": "grok-imagine-video-1.5-preview", "modes": ["image2video"]}]
    }

    def fail(*args, **kwargs):
        from apixly_media.client import ApixlyError

        raise ApixlyError("Reference expired")

    api._media = fail
    api.submit_video = lambda *args, **kwargs: pytest.fail("Paid POST must not run")
    monkeypatch.setattr(ApixlyClient, "from_environment", classmethod(lambda cls: api))
    monkeypatch.setenv("APIXLY_STATE_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="no generation was submitted"):
        NODE_CLASS_MAPPINGS["ApixlyVideoSubmit"]().submit(
            "grok-imagine-video-1.5-preview",
            "prompt",
            "{}",
            1,
            reference_image_urls="https://media.example/expired.png",
        )
    assert not list(tmp_path.glob("*.sqlite3"))


@pytest.mark.parametrize(
    "parameters,resolution,aspect",
    [
        ("{}", "720p", "16:9"),
        ('{"resolution":"720p"}', "model_default", "model_default"),
    ],
)
def test_reference_video_rejects_unqualified_explicit_geometry_before_network(
    parameters, resolution, aspect
):
    with pytest.raises(ValueError, match="not qualified"):
        NODE_CLASS_MAPPINGS["ApixlyVideoSubmit"]().submit(
            "grok-imagine-video-1.5-preview",
            "prompt",
            parameters,
            1,
            reference_image_urls="https://media.example/image.png",
            resolution=resolution,
            aspect_ratio=aspect,
        )


def test_video_ui_offers_explicit_model_default_geometry():
    required = NODE_CLASS_MAPPINGS["ApixlyVideoSubmit"].INPUT_TYPES()["required"]
    assert "model_default" in required["resolution"][0]
    assert "model_default" in required["aspect_ratio"][0]


def test_examples_are_importable_graphs_with_exact_registered_node_types():
    examples = Path(__file__).parents[1] / "example_workflows"
    paths = list(examples.glob("*.json"))
    assert len(paths) >= 3
    for path in paths:
        graph = json.loads(path.read_text())
        assert graph["version"] == 0.4
        assert graph["nodes"]
        ids = {node["id"] for node in graph["nodes"]}
        for node in graph["nodes"]:
            assert node["type"] in NODE_CLASS_MAPPINGS or node["type"] in {
                "LoadImage",
                "PreviewImage",
                "SaveImage",
                "Note",
            }
        for link in graph["links"]:
            assert link[1] in ids and link[3] in ids
        assert "api_key" not in path.read_text().lower()


def test_linked_task_widget_placeholders_keep_wait_parameters_in_their_slots():
    examples = Path(__file__).parents[1] / "example_workflows"
    for path in examples.glob("*.json"):
        for node in json.loads(path.read_text())["nodes"]:
            if node["type"] == "ApixlyImageResult":
                assert node["widgets_values"] == ["", 600, 3.0]
            if node["type"] == "ApixlyVideoResult":
                assert node["widgets_values"] == ["", 900, 3.0, True]


def test_comfy_importlib_entrypoint_loads_without_network_calls():
    import importlib.util

    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location(
        "comfy_apixly_entry",
        root / "__init__.py",
        submodule_search_locations=[str(root)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        assert set(module.NODE_CLASS_MAPPINGS) == set(NODE_CLASS_MAPPINGS)
    finally:
        for name in list(sys.modules):
            if name == spec.name or name.startswith(spec.name + "."):
                del sys.modules[name]


def test_concurrent_reexecution_cannot_post_twice(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    path = tmp_path / "guard.sqlite3"
    entered = Event()
    finish = Event()
    calls = []

    def submit():
        calls.append(1)
        entered.set()
        assert finish.wait(5)
        return {"id": "204", "status": "queued"}

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(SubmissionJournal(path).submit_once, "same-action", submit)
        assert entered.wait(5)
        try:
            with pytest.raises(UnknownSubmission):
                SubmissionJournal(path).submit_once("same-action", submit)
        finally:
            finish.set()
        assert first.result()["id"] == "204"
    assert calls == [1]
