"""New starter graphs are reviewable and cannot enqueue paid work by default."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
NAMES = [
    "expression-prompt-v2",
    "image-grid-split",
    "image-enhancement-prompt",
    "character-sheet-plan",
]
PAID = {"ApixlyImageSubmit", "ApixlyImageEdit", "ApixlyVideoSubmit"}


@pytest.mark.parametrize("name", NAMES)
def test_new_starters_keep_every_paid_node_muted_and_every_new_control_off(name):
    raw = (ROOT / "example_workflows" / (name + ".json")).read_text()
    graph = json.loads(raw)
    for node in graph["nodes"]:
        if node["type"] in PAID:
            assert node["mode"] == 2
            assert node["widgets_values"][3:5] == [0, "fixed"]
        if node["type"] in {
            "ApixlyPromptEmotion",
            "ApixlyImageGridSplit",
            "ApixlyEnhancementPrompt",
            "ApixlyCharacterSheetPlan",
        }:
            assert node["widgets_values"][0] is False
    assert not any(
        word in raw.lower()
        for word in ["apc_", "api_key", "access_token", "http://", "https://"]
    )
    assert "free" in raw.lower()


def test_v2_expression_graph_keeps_legacy_control_socket_types():
    graph = json.loads(
        (ROOT / "example_workflows/expression-prompt-v2.json").read_text()
    )
    compose = next(n for n in graph["nodes"] if n["type"] == "ApixlyPromptComposeV2")
    assert [(i["name"], i["type"]) for i in compose["inputs"]] == [
        ("angle", "APIXLY_ANGLE"),
        ("lighting", "APIXLY_LIGHTING"),
        ("emotion", "APIXLY_EMOTION_V2"),
        ("camera", "APIXLY_CAMERA"),
    ]
    assert len(graph["links"]) == 4


def test_enhancement_wires_the_same_exact_model_and_parameters_to_the_muted_edit():
    graph = json.loads(
        (ROOT / "example_workflows/image-enhancement-prompt.json").read_text()
    )
    nodes = {n["id"]: n for n in graph["nodes"]}
    plan = next(n for n in nodes.values() if n["type"] == "ApixlyEnhancementPrompt")
    edit = next(n for n in nodes.values() if n["type"] == "ApixlyImageEdit")
    slots = {"prompt": 0, "parameters_json": 1, "model": 3}
    for name, slot in slots.items():
        inp = next(i for i in edit["inputs"] if i["name"] == name)
        link = next(item for item in graph["links"] if item[0] == inp["link"])
        assert link[1:3] == [plan["id"], slot]
    assert edit["mode"] == 2


def test_character_starter_outputs_one_selected_shot_and_contains_no_paid_node():
    graph = json.loads(
        (ROOT / "example_workflows/character-sheet-plan.json").read_text()
    )
    assert {n["type"] for n in graph["nodes"]} == {"ApixlyCharacterSheetPlan", "Note"}
    plan = graph["nodes"][0]
    assert json.loads(plan["widgets_values"][3]) == ["seedance-pack"]
    assert plan["widgets_values"][5] == -1
