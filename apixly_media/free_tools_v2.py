"""Offline utilities from Studixly 381eaaa; no account, network or task state.

V2 extends composition with expression direction. V1 remains byte-identical.
Image enhancement is an editing instruction, never a super-resolution claim.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .creative_compiler import EDIT_GUARD, compose_creative_prompt

CONTRACT_VERSION = "2.0.0"
JS_WHITESPACE = "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
ENHANCEMENT_PROMPT = "Improve the visual clarity of this image: reduce compression artifacts and noise, recover natural fine detail, and keep edges clean without halos. Preserve the original composition, identity, text, colors, lighting and objects. Do not add or remove elements or change the artistic style."
CHARACTER_SHEETS = [
    {
        "id": "key-visual",
        "labelKey": "csheetKeyVisual",
        "hintKey": "csheetKeyVisualHint",
        "shots": [
            {
                "aspectRatio": "2:3",
                "promptTemplate": "Full-body character key visual of {character}. Style: {style}. Standing in a relaxed confident pose, front view, full figure from head to toe, detailed rendering, clean plain studio background, soft even lighting, high detail.",
            }
        ],
    },
    {
        "id": "turnaround",
        "labelKey": "csheetTurnaround",
        "hintKey": "csheetTurnaroundHint",
        "shots": [
            {
                "aspectRatio": "16:9",
                "promptTemplate": "Character turnaround model sheet of {character}. Style: {style}. The SAME character shown in four orthographic views arranged left to right: front view, left side profile, right side profile, and back view. Consistent proportions, costume and colors across all four views, neutral A-pose, flat even lighting, plain light grey background, professional character design reference sheet.",
            }
        ],
    },
    {
        "id": "head-closeups",
        "labelKey": "csheetHeadCloseups",
        "hintKey": "csheetHeadCloseupsHint",
        "shots": [
            {
                "aspectRatio": "16:9",
                "promptTemplate": "Character head study of {character}. Style: {style}. The same head shown from three angles side by side: front, side profile, and three-quarter view. Consistent facial features and hairstyle, neutral expression, clean plain background, character design reference.",
            }
        ],
    },
    {
        "id": "expressions",
        "labelKey": "csheetExpressions",
        "hintKey": "csheetExpressionsHint",
        "shots": [
            {
                "aspectRatio": "4:3",
                "promptTemplate": "Expression sheet of {character}. Style: {style}. A neat grid of the same character's face showing distinct emotions: neutral, happy, angry, sad, surprised, and smirking. Consistent character design and features across every panel, clean plain background, model sheet.",
            }
        ],
    },
    {
        "id": "poses",
        "labelKey": "csheetPoses",
        "hintKey": "csheetPosesHint",
        "shots": [
            {
                "aspectRatio": "16:9",
                "promptTemplate": "Character pose sheet of {character}. Style: {style}. The same character in several dynamic full-body action poses, anatomically correct, feet grounded, consistent proportions, costume and colors, plain background, character design reference.",
            }
        ],
    },
    {
        "id": "costume",
        "labelKey": "csheetCostume",
        "hintKey": "csheetCostumeHint",
        "shots": [
            {
                "aspectRatio": "4:3",
                "promptTemplate": "Costume and accessory breakdown sheet of {character}. Style: {style}. A central full-body view with separate close-up callouts of clothing details, accessories and props arranged around it, each clearly separated, consistent design, clean background, character reference sheet.",
            }
        ],
    },
    {
        "id": "color-material",
        "labelKey": "csheetColorMaterial",
        "hintKey": "csheetColorMaterialHint",
        "shots": [
            {
                "aspectRatio": "4:3",
                "promptTemplate": "Color and material board for {character}. Style: {style}. A palette of color swatch chips next to material texture close-ups (fabric, metal, skin, hair) beside a small character thumbnail for reference, clean organized layout, design board.",
            }
        ],
    },
    {
        "id": "proportions",
        "labelKey": "csheetProportions",
        "hintKey": "csheetProportionsHint",
        "shots": [
            {
                "aspectRatio": "16:9",
                "promptTemplate": "Character proportion sheet of {character}. Style: {style}. The same full-body character aligned to a heads-tall measurement grid with horizontal guide lines marking head units, front view, neutral pose, plain background, character design reference.",
            }
        ],
    },
    {
        "id": "seedance-pack",
        "labelKey": "csheetSeedancePack",
        "hintKey": "csheetSeedancePackHint",
        "shots": [
            {
                "aspectRatio": "2:3",
                "promptTemplate": "Clean reference photo of {character}. Style: {style}. Front view, full body, neutral standing pose, plain seamless background, even lighting, sharp focus, consistent character.",
            },
            {
                "aspectRatio": "2:3",
                "promptTemplate": "Clean reference photo of the SAME character {character}. Style: {style}. Three-quarter view, full body, neutral standing pose, plain seamless background, even lighting, consistent with the front-view reference.",
            },
            {
                "aspectRatio": "2:3",
                "promptTemplate": "Clean reference photo of the SAME character {character}. Style: {style}. Side profile view, full body, neutral standing pose, plain seamless background, even lighting, consistent with the front-view reference.",
            },
        ],
    },
]
MAX_TILES = 144
MAX_CHARACTER_SHOTS = 32
RATIOS = ("1:1", "2:3", "3:2", "4:3", "3:4", "16:9", "9:16", "21:9", "9:21")
GPT_RATIOS = ("1:1", "3:2", "2:3", "16:9", "9:16", "4:3", "3:4", "5:4", "4:5", "21:9")
GEMINI_RATIOS = (
    "1:1",
    "16:9",
    "9:16",
    "4:3",
    "3:4",
    "2:3",
    "3:2",
    "4:5",
    "5:4",
    "21:9",
)
GROK_RATIOS = ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3")
AROUSAL = {
    -2: "deeply calm, still expression",
    -1: "relaxed, composed expression",
    1: "alert, animated expression",
    2: "intense, high-energy expression, wide eyes",
}
AFFINITY = {
    -2: "cold distant gaze, detached expression",
    -1: "reserved, aloof expression, averted gaze",
    1: "gentle smile, soft eyes",
    2: "warm beaming smile, smiling eyes, open and approachable",
}
QUADRANTS = {
    (1, 1): {2: "cheerful", 3: "joyful, excited", 4: "elated, beaming smile"},
    (1, -1): {
        2: "annoyed, raised eyebrow",
        3: "angry, furrowed brow",
        4: "furious, scowl, furrowed brow, clenched teeth",
    },
    (-1, -1): {
        2: "bored, indifferent",
        3: "gloomy, faint frown",
        4: "melancholic, downturned mouth, drooping eyelids",
    },
    (-1, 1): {
        2: "content",
        3: "serene expression, at ease",
        4: "peaceful, serene expression",
    },
}


def _text(value: Any, field: str, limit: int = 20000) -> str:
    if (
        type(value) is not str
        or len(value.encode("utf-16-le", errors="surrogatepass")) // 2 > limit
    ):
        raise ValueError(f"{field}: expected a bounded string.")
    return value


def _integer(value: Any, field: str, low: int, high: int) -> int:
    if (
        type(value) not in (int, float)
        or not low <= value <= high
        or not math.isfinite(value)
        or int(value) != value
    ):
        raise ValueError(f"{field}: expected an integer from {low} to {high}.")
    return int(value)


def _flag(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field}: expected a boolean.")
    return value


def validate_emotion(setting: Any) -> dict:
    if type(setting) is not dict or set(setting) - {
        "enabled",
        "arousal",
        "affinity",
        "targetLabel",
    }:
        raise ValueError("emotion: unknown or invalid setting.")
    if "enabled" in setting:
        _flag(setting["enabled"], "emotion.enabled")
    for axis in ("arousal", "affinity"):
        _integer(setting.get(axis, 0), f"emotion.{axis}", -2, 2)
    _text(setting.get("targetLabel", ""), "emotion.targetLabel", 1000)
    return setting


def build_emotion_prompt(setting: dict) -> str:
    setting = validate_emotion(setting)
    if setting.get("enabled") is False:
        return ""
    a, f = setting.get("arousal", 0), setting.get("affinity", 0)
    if not (a or f):
        return ""
    anchor = (
        QUADRANTS[(1 if a > 0 else -1, 1 if f > 0 else -1)][abs(a) + abs(f)]
        if a and f
        else ""
    )
    phrases = dict.fromkeys(
        phrase
        for source in [anchor, AROUSAL.get(a, ""), AFFINITY.get(f, "")]
        if source
        for phrase in source.split(", ")
    )
    fragment = ", ".join(phrases)
    target = setting.get("targetLabel", "").strip(JS_WHITESPACE)
    return f"{target} with {fragment}" if target else fragment


def compose_creative_prompt_v2(payload: Any) -> dict:
    if type(payload) is not dict or set(payload) - {
        "contract_version",
        "prompt",
        "mode",
        "tools",
    }:
        raise ValueError("payload: invalid V2 fields.")
    if payload.get("contract_version", CONTRACT_VERSION) != CONTRACT_VERSION:
        raise ValueError("contract_version: expected 2.0.0.")
    tools = payload.get("tools", {})
    if type(tools) is not dict or set(tools) - {
        "angle",
        "lighting",
        "emotion",
        "camera",
    }:
        raise ValueError("tools: unknown or invalid fields.")
    emotion = build_emotion_prompt(tools.get("emotion", {}))
    legacy = compose_creative_prompt(
        {k: v for k, v in payload.items() if k not in {"tools", "contract_version"}}
        | {"tools": {k: v for k, v in tools.items() if k != "emotion"}}
    )
    if not emotion:
        return {"contract_version": CONTRACT_VERSION, **legacy}
    mode = payload.get("mode", "generate")
    section = {
        "tool": "emotion",
        "label": "Expression",
        "text": f"Change the subject's expression: {emotion}."
        if mode == "edit"
        else f"Expression: {emotion}",
    }
    sections = list(legacy["sections"])
    index = next(
        (i for i, s in enumerate(sections) if s["tool"] == "camera"), len(sections)
    )
    sections.insert(index, section)
    lines = [s["text"] for s in sections] + ([EDIT_GUARD] if mode == "edit" else [])
    base = payload["prompt"]
    final = (base + "\n\n" if base else "") + "\n".join(lines)
    _text(final, "final_prompt")
    return {
        "contract_version": CONTRACT_VERSION,
        "final_prompt": final,
        "sections": sections,
        "applied_tools": [s["tool"] for s in sections],
        "changed": final != base,
    }


def _cuts(lines: Any, size: int, count: int, field: str) -> list[int]:
    if lines is None or lines == []:
        cuts = [i * size // count for i in range(count + 1)]
    else:
        if type(lines) is not list or len(lines) > 11:
            raise ValueError(f"{field}: expected at most 11 normalized cut positions.")
        for line in lines:
            if (
                type(line) not in (int, float)
                or not math.isfinite(line)
                or not 0 < line < 1
            ):
                raise ValueError(
                    f"{field}: each cut must be finite and strictly inside (0,1)."
                )
        cuts = [0] + sorted(math.floor(line * size + 0.5) for line in lines) + [size]
    if any(right <= left for left, right in zip(cuts, cuts[1:])):
        raise ValueError(f"{field}: duplicate, overlapping or empty pixel cuts.")
    return cuts


def grid_geometry(
    width: int,
    height: int,
    *,
    rows: int = 2,
    columns: int = 2,
    horizontal_lines=None,
    vertical_lines=None,
    max_tiles: int = MAX_TILES,
) -> list[dict]:
    width = _integer(width, "width", 1, 65536)
    height = _integer(height, "height", 1, 65536)
    rows = _integer(rows, "rows", 1, 12)
    columns = _integer(columns, "columns", 1, 12)
    budget = _integer(max_tiles, "max_tiles", 1, MAX_TILES)
    xcuts = _cuts(vertical_lines, width, columns, "vertical_lines")
    ycuts = _cuts(horizontal_lines, height, rows, "horizontal_lines")
    if (len(xcuts) - 1) * (len(ycuts) - 1) > budget:
        raise ValueError("Grid exceeds the tile budget.")
    return [
        {
            "row": row,
            "column": column,
            "x": x,
            "y": y,
            "width": xcuts[column + 1] - x,
            "height": ycuts[row + 1] - y,
        }
        for row, y in enumerate(ycuts[:-1])
        for column, x in enumerate(xcuts[:-1])
    ]


def split_image_grid(
    images,
    *,
    enabled=True,
    rows=2,
    columns=2,
    horizontal_lines=None,
    vertical_lines=None,
    max_tiles=MAX_TILES,
):
    _flag(enabled, "enabled")
    shape = getattr(images, "shape", ())
    if len(shape) != 4 or not 1 <= shape[0] <= 16 or shape[-1] not in (3, 4):
        raise ValueError("IMAGE must contain 1–16 RGB/RGBA images [B,H,W,C].")
    batch, height, width, _ = shape
    budget = _integer(max_tiles, "max_tiles", 1, MAX_TILES)
    geometry = grid_geometry(
        width,
        height,
        rows=rows if enabled else 1,
        columns=columns if enabled else 1,
        horizontal_lines=horizontal_lines if enabled else None,
        vertical_lines=vertical_lines if enabled else None,
        max_tiles=budget,
    )
    if not enabled:
        return [images], {
            "enabled": False,
            "order": "input-batch",
            "width": int(width),
            "height": int(height),
            "batch_count": int(batch),
            "tiles": [{"batch_start": 0, "batch_count": int(batch), **geometry[0]}],
        }
    if batch * len(geometry) > budget:
        raise ValueError("Image batch exceeds the total tile budget.")
    pieces, tiles = [], []
    for b in range(batch):
        for tile in geometry:
            x, y, w, h = (tile[k] for k in ("x", "y", "width", "height"))
            part = images[b : b + 1, y : y + h, x : x + w, :]
            pieces.append(part.clone() if hasattr(part, "clone") else part.copy())
            tiles.append({"batch": b, **tile})
    return pieces, {
        "enabled": enabled,
        "order": "batch-row-column",
        "width": int(width),
        "height": int(height),
        "batch_count": int(batch),
        "tiles": tiles,
    }


def _ratio(width, height):
    target = width / height
    return min(
        RATIOS, key=lambda r: abs(int(r.split(":")[0]) / int(r.split(":")[1]) - target)
    )


def build_enhancement_plan(
    model: str = "gemini-3.1-flash-image", width: int = 1024, height: int = 1024
) -> dict:
    _text(model, "model", 128)
    width = _integer(width, "width", 1, 65536)
    height = _integer(height, "height", 1, 65536)
    aspect = _ratio(width, height)
    if model in {"gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst"}:
        ratio = aspect if aspect in GPT_RATIOS else "1:1"
        w, h = map(int, ratio.split(":"))
        long = math.floor((1024 * max(w, h) / min(w, h)) / 64 + 0.5) * 64
        size = f"{long}x1024" if w >= h else f"1024x{long}"
        params = {
            "moderation": "low",
            "output_format": "png",
            "quality": "auto",
            "size": size,
        }
    elif model in {
        "gemini-3.1-flash-image",
        "gemini-3.1-flash-image-preview",
        "gemini-3-pro-image",
        "gemini-3-pro-image-preview",
        "gemini-nano-banana-2.1",
    }:
        params = {
            "aspect_ratio": aspect if aspect in GEMINI_RATIOS else "1:1",
            "resolution": "1K",
        }
    elif model in {"grok-imagine-image", "grok-imagine-image-quality"}:
        params = {"aspect_ratio": aspect if aspect in GROK_RATIOS else "1:1"}
    else:
        raise ValueError(
            "No verified enhancement parameter mapping for this exact model; use Image Edit with your own parameters."
        )
    return {
        "prompt": ENHANCEMENT_PROMPT,
        "aspect": aspect,
        "parameters": params,
        "count": 1,
        "tools": {},
    }


def build_character_shots(input: dict) -> list[dict]:
    if type(input) is not dict or set(input) - {
        "character",
        "style",
        "sheetIds",
        "custom",
    }:
        raise ValueError("Character plan: unknown or invalid fields.")
    character = (
        _text(input.get("character", ""), "character", 4000).strip(JS_WHITESPACE)
        or "a character"
    )
    style = (
        _text(input.get("style", ""), "style", 2000).strip(JS_WHITESPACE)
        or "detailed, high quality"
    )
    custom = _text(input.get("custom", ""), "custom", 4000).strip(JS_WHITESPACE)
    ids = input.get("sheetIds", [])
    if type(ids) is not list or len(ids) > 32 or any(type(x) is not str for x in ids):
        raise ValueError("sheetIds: expected a bounded list of sheet identifiers.")
    catalog = {x["id"]: x for x in CHARACTER_SHEETS}
    shots = []
    for sheet_id in ids:
        for shot in catalog.get(sheet_id, {}).get("shots", []):
            shots.append(
                {
                    "tag": sheet_id,
                    # One pass only: inserted user text stays literal. This
                    # narrowly fixes the website's chained-template bug.
                    "prompt": re.sub(
                        r"\{(character|style)\}",
                        lambda match: {"character": character, "style": style}[
                            match.group(1)
                        ],
                        shot["promptTemplate"],
                    ),
                    "aspectRatio": shot["aspectRatio"],
                }
            )
    if custom:
        shots.append(
            {
                "tag": "custom",
                "prompt": f"{character}. {custom}. Style: {style}. Full body, clean plain background, consistent character, high detail.",
                "aspectRatio": "2:3",
            }
        )
    if len(shots) > MAX_CHARACTER_SHOTS:
        raise ValueError("Character plan exceeds 32 preview shots.")
    return shots


def select_character_plan(input: dict, *, enabled=False, shot_index=-1) -> dict:
    _flag(enabled, "enabled")
    index = _integer(shot_index, "shot_index", -1, MAX_CHARACTER_SHOTS - 1)
    shots = build_character_shots(input)
    if enabled and not 0 <= index < len(shots):
        raise ValueError(
            "Choose one shot explicitly; shot_index does not identify a planned shot."
        )
    selected = shots[index] if enabled and shots else None
    return {
        "enabled": enabled,
        "shots": shots,
        "selected_index": index,
        "selected_prompt": selected["prompt"] if selected else "",
        "selected_aspect": selected["aspectRatio"] if selected else "auto",
        "automatic_generation": False,
    }
