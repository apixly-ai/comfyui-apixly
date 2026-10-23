import json
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "name,submit_type,mode",
    [
        ("creative-image-generation", "ApixlyImageSubmit", "generate"),
        ("creative-reference-edit", "ApixlyImageEdit", "edit"),
        ("creative-video-generation", "ApixlyVideoSubmit", "generate"),
    ],
)
def test_creative_paid_starters_require_explicit_unmute_and_preserve_safe_links(
    name, submit_type, mode
):
    path = Path(__file__).parents[1] / "example_workflows" / (name + ".json")
    graph = json.loads(path.read_text())
    nodes = {node["id"]: node for node in graph["nodes"]}
    compose = next(
        node for node in nodes.values() if node["type"] == "ApixlyPromptCompose"
    )
    submit = next(node for node in nodes.values() if node["type"] == submit_type)
    assert compose["widgets_values"][1] == mode
    assert submit["mode"] == 2
    assert submit["widgets_values"][3:5] == [0, "fixed"]
    prompt = next(item for item in submit["inputs"] if item["name"] == "prompt")
    link = next(link for link in graph["links"] if link[0] == prompt["link"])
    assert link[1:3] == [compose["id"], 0] and link[3:5] == [
        submit["id"],
        submit["inputs"].index(prompt),
    ]
    for node in nodes.values():
        if (
            node["type"].startswith("ApixlyPrompt")
            and node["type"] != "ApixlyPromptCompose"
        ):
            assert node["widgets_values"][0] is False
        elif node["type"] not in {"Note", "ApixlyPromptCompose"}:
            assert node["mode"] == 2
    assert (
        "https://" not in path.read_text()
        and "access_token" not in path.read_text()
        and "api_key" not in path.read_text()
    )
    assert "unmute" in path.read_text().lower() and "paid" in path.read_text().lower()
