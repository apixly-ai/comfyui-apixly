"""Offline feature behavior. Oracle executes pinned Studixly TS, not this port."""

import importlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures/free-tools-v2/golden.json").read_text()
)
V1 = json.loads(
    (Path(__file__).parent / "fixtures/creative-golden-v1.json").read_text()
)


def tool():
    return importlib.import_module("apixly_media.free_tools_v2")


@pytest.mark.parametrize("case", GOLDEN["emotion"])
def test_emotion_matches_real_website_all_25_cells_and_target_trim(case):
    assert tool().build_emotion_prompt(case["input"]) == case["expected"]


@pytest.mark.parametrize("case", GOLDEN["character"])
def test_character_plan_matches_all_nine_original_sheets_without_auto_execution(case):
    actual = tool().build_character_shots(case["input"])
    assert actual == case["expected"]


@pytest.mark.parametrize("case", GOLDEN["enhancement"])
def test_enhancement_uses_website_preservation_prompt_and_model_parameters(case):
    assert tool().build_enhancement_plan(**case["input"]) == case["expected"]


@pytest.mark.parametrize("case", V1["valid"], ids=lambda c: c["id"])
def test_compose_v2_preserves_every_v1_final_byte_when_emotion_inactive(case):
    data = case["input"]
    base = tool().compose_creative_prompt_v2(data)
    assert base["contract_version"] == "2.0.0"
    assert {k: v for k, v in base.items() if k != "contract_version"} == case[
        "expected"
    ]
    for setting in (
        {"enabled": False, "arousal": 2, "affinity": -2},
        {"arousal": 0, "affinity": 0},
    ):
        data = {
            **case["input"],
            "tools": {**case["input"].get("tools", {}), "emotion": setting},
        }
        assert (
            tool().compose_creative_prompt_v2(data)["final_prompt"]
            == case["expected"]["final_prompt"]
        )


def test_v2_order_edit_guard_once_and_no_forged_emotion_packet():
    payload = {
        "prompt": "  same subject\n",
        "mode": "edit",
        "tools": {
            "angle": {"enabled": True, "yaw": 90, "pitch": 30},
            "lighting": {"enabled": True, "preset": "goldenHour"},
            "emotion": {
                "enabled": True,
                "arousal": 2,
                "affinity": 2,
                "targetLabel": "the man",
            },
            "camera": {"enabled": True, "focal": 85},
        },
    }
    result = tool().compose_creative_prompt_v2(payload)
    assert result["applied_tools"] == ["angle", "lighting", "emotion", "camera"]
    assert result["final_prompt"].startswith("  same subject\n\n\nChange")
    assert (
        "Change the subject's expression: the man with elated" in result["final_prompt"]
    )
    assert result["final_prompt"].count(tool().EDIT_GUARD) == 1
    for bad in [
        {"arousal": True},
        {"affinity": 3},
        {"arousal": 0.5},
        {"final_prompt": "forged"},
        {"targetLabel": 7},
    ]:
        with pytest.raises(ValueError):
            tool().compose_creative_prompt_v2(
                {"prompt": "x", "tools": {"emotion": bad}}
            )
    with pytest.raises(ValueError):
        tool().compose_creative_prompt_v2({"contract_version": "1.0.0", "prompt": "x"})


@pytest.mark.parametrize(
    "width,height,rows,columns",
    [(11, 7, 2, 3), (1, 7, 7, 1), (9, 1, 1, 9), (16, 12, 3, 4)],
)
def test_grid_tiles_cover_original_exactly_in_row_major_for_multibatch_rgba(
    width, height, rows, columns
):
    image = np.arange(2 * height * width * 4, dtype=np.float32).reshape(
        2, height, width, 4
    )
    pieces, metadata = tool().split_image_grid(image, rows=rows, columns=columns)
    restored = np.zeros_like(image)
    assert len(pieces) == 2 * rows * columns
    assert len(metadata["tiles"]) == len(pieces)
    for tile, piece in zip(metadata["tiles"], pieces):
        b, y, x, h, w = (tile[k] for k in ["batch", "y", "x", "height", "width"])
        assert piece.shape == (1, h, w, 4)
        assert np.array_equal(piece, image[b : b + 1, y : y + h, x : x + w, :])
        restored[b : b + 1, y : y + h, x : x + w, :] = piece
    assert np.array_equal(restored, image)
    assert [(t["batch"], t["row"], t["column"]) for t in metadata["tiles"]] == [
        (b, r, c) for b in range(2) for r in range(rows) for c in range(columns)
    ]


def test_custom_cuts_use_js_half_up_round_and_leave_no_gaps():
    tiles = tool().grid_geometry(
        5, 7, rows=1, columns=1, horizontal_lines=[0.5], vertical_lines=[0.5]
    )
    assert [(t["x"], t["y"], t["width"], t["height"]) for t in tiles] == [
        (0, 0, 3, 4),
        (3, 0, 2, 4),
        (0, 4, 3, 3),
        (3, 4, 2, 3),
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"rows": 0},
        {"rows": True},
        {"rows": 13},
        {"rows": 1.5},
        {"columns": 5},
        {"vertical_lines": [0.2, 0.2]},
        {"vertical_lines": [0.2, 0.21]},
        {"vertical_lines": [0]},
        {"vertical_lines": [1]},
        {"vertical_lines": [math.nan]},
        {"horizontal_lines": [math.inf]},
        {"vertical_lines": "0.5"},
        {"rows": 2, "columns": 2, "max_tiles": 3},
    ],
)
def test_invalid_or_overbudget_grid_is_rejected_before_any_tile_allocation(kwargs):
    with pytest.raises(ValueError):
        tool().grid_geometry(4, 4, **kwargs)


def test_full_grid_budget_counts_every_batch_before_slicing():
    image = np.zeros((16, 12, 12, 3), dtype=np.float32)
    with pytest.raises(ValueError):
        tool().split_image_grid(image, rows=12, columns=12, max_tiles=144)


def test_grid_off_preserves_one_whole_input_batch_and_downstream_execution_count():
    image = np.arange(3 * 7 * 11 * 4).reshape(3, 7, 11, 4)
    pieces, metadata = tool().split_image_grid(
        image, enabled=False, rows=12, columns=12
    )
    assert len(pieces) == 1
    assert pieces[0] is image
    assert pieces[0].shape == (3, 7, 11, 4)
    assert metadata["order"] == "input-batch"
    assert metadata["batch_count"] == 3
    assert metadata["tiles"] == [
        {
            "batch_start": 0,
            "batch_count": 3,
            "row": 0,
            "column": 0,
            "x": 0,
            "y": 0,
            "width": 11,
            "height": 7,
        }
    ]


def test_free_nodes_do_not_create_clients_credentials_network_or_journal(
    monkeypatch, tmp_path
):
    import socket

    from apixly_media.client import ApixlyClient

    def forbidden(*args, **kwargs):
        raise AssertionError("Free utility attempted I/O")

    monkeypatch.setattr(ApixlyClient, "from_environment", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.delenv("APIXLY_API_KEY", raising=False)
    monkeypatch.setenv("APIXLY_STATE_DIR", str(tmp_path / "must-not-exist"))
    nodes = importlib.import_module("apixly_media.free_nodes_v2")
    emotion = nodes.ApixlyPromptEmotion().build()
    assert emotion["result"] == (
        {"enabled": False, "arousal": 0, "affinity": 0, "targetLabel": ""},
        "",
    )
    compose = nodes.ApixlyPromptComposeV2().compose(
        "  untouched\n", "edit", emotion=emotion["result"][0]
    )
    assert compose["result"][0] == "  untouched\n"
    enhance = nodes.ApixlyEnhancementPrompt().build()
    assert enhance["result"][0] == "" and json.loads(enhance["result"][1]) == {}
    character = nodes.ApixlyCharacterSheetPlan().build()
    assert character["result"][1:] == ("", "auto")
    selected = nodes.ApixlyCharacterSheetPlan().build(
        enabled=True, character="Ada", sheet_ids_json='["seedance-pack"]', shot_index=1
    )
    plan = json.loads(selected["result"][0])
    assert len(plan["shots"]) == 3
    assert "Three-quarter view" in selected["result"][1]
    assert not getattr(nodes.ApixlyCharacterSheetPlan, "OUTPUT_IS_LIST", (False,))[0]
    image = np.zeros((1, 7, 11, 3), dtype=np.float32)
    split = nodes.ApixlyImageGridSplit().split(image, enabled=True, rows=2, columns=3)
    assert len(split["result"][0]) == 6
    off = nodes.ApixlyImageGridSplit().split(image, enabled=False)
    assert len(off["result"][0]) == 1 and np.array_equal(off["result"][0][0], image)
    assert nodes.ApixlyImageGridSplit.OUTPUT_IS_LIST == (True, False)
    assert not (tmp_path / "must-not-exist").exists()


def test_selected_character_shot_requires_exact_valid_index_and_bounded_plan():
    with pytest.raises(ValueError):
        tool().select_character_plan(
            {"character": "Ada", "sheetIds": ["key-visual"]}, enabled=True, shot_index=1
        )
    with pytest.raises(ValueError):
        tool().select_character_plan(
            {"character": "Ada", "sheetIds": ["seedance-pack"] * 12},
            enabled=True,
            shot_index=0,
        )


def test_oversized_numeric_fields_fail_as_clear_validation_errors():
    with pytest.raises(ValueError):
        tool().grid_geometry(10**1000, 4)
    with pytest.raises(ValueError):
        tool().build_emotion_prompt({"arousal": 10**1000})


def test_enhancement_selected_exact_model_is_connectable_to_avoid_parameter_mismatch():
    nodes = importlib.import_module("apixly_media.free_nodes_v2")
    node = nodes.ApixlyEnhancementPrompt()
    assert "model" in node.RETURN_NAMES
    result = node.build(
        enabled=True, model="grok-imagine-image", width=1536, height=1024
    )
    assert result["result"][node.RETURN_NAMES.index("model")] == "grok-imagine-image"
    assert json.loads(result["result"][1]) == {"aspect_ratio": "3:2"}


def test_enhancement_uses_actual_connected_reference_dimensions_not_stale_widgets():
    nodes = importlib.import_module("apixly_media.free_nodes_v2")
    image = np.zeros((1, 512, 1024, 4), dtype=np.float32)
    node = nodes.ApixlyEnhancementPrompt()
    result = node.build(
        enabled=True,
        model="gemini-3.1-flash-image",
        width=1024,
        height=1024,
        reference_image=image,
    )
    assert result["result"][2] == "16:9"
    assert json.loads(result["result"][1]) == {
        "aspect_ratio": "16:9",
        "resolution": "1K",
    }


def test_character_template_inserts_user_text_literally_without_recursive_tokens():
    regressions = json.loads(
        (
            Path(__file__).parent
            / "fixtures/free-tools-v2/literal-interpolation-regressions.json"
        ).read_text()
    )
    for case in regressions["cases"]:
        assert tool().build_character_shots(case["input"]) == case["expected"]


def test_character_no_selection_is_safe_off_and_explicit_error_when_enabled():
    data = {"character": "Ada", "sheetIds": ["key-visual"]}
    off = tool().select_character_plan(data, enabled=False, shot_index=-1)
    assert off["selected_prompt"] == "" and off["selected_index"] == -1
    with pytest.raises(ValueError, match="Choose one shot"):
        tool().select_character_plan(data, enabled=True, shot_index=-1)


def test_public_registry_contains_all_fifteen_nodes_and_preserves_the_original_ten():
    from apixly_media.free_nodes_v2 import FREE_V2_NODE_CLASS_MAPPINGS
    from apixly_media.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

    assert len(NODE_CLASS_MAPPINGS) == 15
    assert set(FREE_V2_NODE_CLASS_MAPPINGS) <= set(NODE_CLASS_MAPPINGS)
    assert set(NODE_CLASS_MAPPINGS) == set(NODE_DISPLAY_NAME_MAPPINGS)
    assert (
        NODE_CLASS_MAPPINGS["ApixlyPromptCompose"]().compose("  exact\n")["result"][0]
        == "  exact\n"
    )
