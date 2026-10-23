import importlib
import json
from pathlib import Path

import pytest

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures/creative-golden-v1.json").read_text()
)


@pytest.mark.parametrize("case", FIXTURES["valid"], ids=lambda case: case["id"])
def test_shared_creative_valid(case):
    compiler = importlib.import_module("apixly_media.creative_compiler")
    assert compiler.compose_creative_prompt(case["input"]) == case["expected"]


@pytest.mark.parametrize("case", FIXTURES["invalid"], ids=lambda case: case["id"])
def test_shared_creative_invalid(case):
    compiler = importlib.import_module("apixly_media.creative_compiler")
    with pytest.raises(ValueError) as error:
        compiler.compose_creative_prompt(case["input"])
    assert error.value.field_path == case["error_path"]


def test_free_nodes_register_and_compose_without_key_client_or_state(
    monkeypatch, tmp_path
):
    from apixly_media.client import ApixlyClient
    from apixly_media.nodes import NODE_CLASS_MAPPINGS

    monkeypatch.delenv("APIXLY_API_KEY", raising=False)
    monkeypatch.setenv("APIXLY_STATE_DIR", str(tmp_path / "must-not-exist"))

    def no_client(*args, **kwargs):
        raise AssertionError("A free prompt tool must not access API credentials.")

    monkeypatch.setattr(ApixlyClient, "from_environment", no_client)
    angle = NODE_CLASS_MAPPINGS["ApixlyPromptViewpoint"]().build(
        enabled=True, yaw=90, pitch=30
    )
    lighting = NODE_CLASS_MAPPINGS["ApixlyPromptLighting"]().build(
        enabled=True, preset="goldenHour"
    )
    camera = NODE_CLASS_MAPPINGS["ApixlyPromptCamera"]().build(
        enabled=True, use_focal=True, focal=85, aperture="f/1.8"
    )
    result = NODE_CLASS_MAPPINGS["ApixlyPromptCompose"]().compose(
        "  Blue vase\n",
        "edit",
        angle["result"][0],
        lighting["result"][0],
        camera["result"][0],
    )
    payload = json.loads(result["result"][1])
    compiler = importlib.import_module("apixly_media.creative_compiler")
    expected = compiler.compose_creative_prompt(payload)
    assert result["result"][0] == expected["final_prompt"]
    assert result["ui"]["apixly_prompt"][0] == expected
    assert expected["applied_tools"] == ["angle", "lighting", "camera"]
    assert expected["final_prompt"].startswith("  Blue vase\n\n\nChange")
    assert "Preserve all subject" in expected["final_prompt"]
    assert not (tmp_path / "must-not-exist").exists()


def test_node_defaults_are_off_and_retain_inactive_choices():
    from apixly_media.nodes import NODE_CLASS_MAPPINGS

    for name in ["ApixlyPromptViewpoint", "ApixlyPromptLighting", "ApixlyPromptCamera"]:
        node = NODE_CLASS_MAPPINGS[name]()
        assert node.INPUT_TYPES()["required"]["enabled"][1]["default"] is False
        result = node.build()
        assert result["result"][0]["enabled"] is False
        assert result["result"][1] == ""
    lighting = NODE_CLASS_MAPPINGS["ApixlyPromptLighting"]().build(
        enabled=True, direction="legacy", key_light="left"
    )["result"][0]
    assert lighting["keyLight"] == "left" and "lightYaw" not in lighting
    orbit = NODE_CLASS_MAPPINGS["ApixlyPromptLighting"]().build(
        enabled=True, direction="orbit", key_light="left", light_yaw=0, light_pitch=0
    )
    assert orbit["result"][1] == ""
    assert "keyLight" not in orbit["result"][0]


def test_compose_rejects_forged_settings_and_preserves_disabled_base():
    from apixly_media.nodes import NODE_CLASS_MAPPINGS

    compose = NODE_CLASS_MAPPINGS["ApixlyPromptCompose"]().compose
    base = "\n  Preserve exact spaces 🌠\n "
    assert compose(base, "edit")["result"][0] == base
    with pytest.raises(ValueError):
        compose("base", "generate", angle={"enabled": True, "final_prompt": "forged"})


def test_lighting_view_is_explicitly_ui_only():
    from apixly_media.nodes import NODE_CLASS_MAPPINGS

    node = NODE_CLASS_MAPPINGS["ApixlyPromptLighting"]()
    front = node.build(enabled=True, preset="goldenHour", view="front")
    perspective = node.build(enabled=True, preset="goldenHour", view="perspective")
    assert front["result"][0]["view"] == "front"
    assert front["result"][1] == perspective["result"][1]


def test_creative_template_is_free_and_wires_real_typed_controls():
    path = Path(__file__).parents[1] / "example_workflows/creative-prompt.json"
    workflow = json.loads(path.read_text())
    types = {node["type"] for node in workflow["nodes"]}
    assert types == {
        "ApixlyPromptViewpoint",
        "ApixlyPromptLighting",
        "ApixlyPromptCamera",
        "ApixlyPromptCompose",
        "Note",
    }
    assert len(workflow["links"]) == 3
