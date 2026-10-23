"""Free native utilities; explicitly selected single prompts, never inference."""

import json

from .free_tools_v2 import (
    build_emotion_prompt,
    build_enhancement_plan,
    compose_creative_prompt_v2,
    select_character_plan,
    split_image_grid,
)


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _parse(value, label):
    if not isinstance(value, str) or len(value) > 20000:
        raise ValueError(f"{label}: expected bounded JSON text.")
    try:
        return json.loads(
            value,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("Non-finite JSON is invalid.")
            ),
        )
    except (ValueError, TypeError):
        raise ValueError(f"{label}: invalid JSON.") from None


class ApixlyPromptEmotion:
    CATEGORY = "Apixly/Prompt"
    FUNCTION = "build"
    OUTPUT_NODE = True
    RETURN_TYPES = ("APIXLY_EMOTION_V2", "STRING")
    RETURN_NAMES = ("emotion", "instruction")
    DESCRIPTION = "Free expression guidance from the original Studixly 5×5 grid. No generation or guaranteed facial geometry."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "enabled": ("BOOLEAN", {"default": False}),
                "arousal": ("INT", {"default": 0, "min": -2, "max": 2, "step": 1}),
                "affinity": ("INT", {"default": 0, "min": -2, "max": 2, "step": 1}),
                "target_label": ("STRING", {"default": ""}),
            }
        }

    def build(self, enabled=False, arousal=0, affinity=0, target_label=""):
        setting = {
            "enabled": enabled,
            "arousal": arousal,
            "affinity": affinity,
            "targetLabel": target_label,
        }
        fragment = build_emotion_prompt(setting)
        return {
            "ui": {
                "text": [fragment],
                "apixly_free_v2": [
                    {"kind": "emotion", "settings": setting, "prompt": fragment}
                ],
            },
            "result": (setting, fragment),
        }


class ApixlyPromptComposeV2:
    CATEGORY = "Apixly/Prompt"
    FUNCTION = "compose"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("final_prompt", "controls_json")
    DESCRIPTION = "Free V2 composition: viewpoint, lighting, expression, lens. Old V1 nodes and workflows remain unchanged."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "mode": (["generate", "edit"],),
            },
            "optional": {
                "angle": ("APIXLY_ANGLE",),
                "lighting": ("APIXLY_LIGHTING",),
                "emotion": ("APIXLY_EMOTION_V2",),
                "camera": ("APIXLY_CAMERA",),
            },
        }

    def compose(
        self,
        prompt,
        mode="generate",
        angle=None,
        lighting=None,
        emotion=None,
        camera=None,
    ):
        tools = {
            k: v
            for k, v in {
                "angle": angle,
                "lighting": lighting,
                "emotion": emotion,
                "camera": camera,
            }.items()
            if v is not None
        }
        payload = {
            "contract_version": "2.0.0",
            "prompt": prompt,
            "mode": mode,
            "tools": tools,
        }
        result = compose_creative_prompt_v2(payload)
        return {
            "ui": {
                "text": [result["final_prompt"]],
                "apixly_free_v2": [{"kind": "compose", **result}],
            },
            "result": (result["final_prompt"], _json(payload)),
        }


class ApixlyImageGridSplit:
    CATEGORY = "Apixly/Image Tools"
    FUNCTION = "split"
    OUTPUT_NODE = True
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("tiles", "coordinates_json")
    OUTPUT_IS_LIST = (True, False)
    DESCRIPTION = "Free lossless grid slicing. Tiles are separate images, not a resized batch. Downstream nodes execute once per tile; connect Preview/Save, not a paid generation node, unless you intend multiple requests."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "enabled": ("BOOLEAN", {"default": False}),
                "rows": ("INT", {"default": 2, "min": 1, "max": 12}),
                "columns": ("INT", {"default": 2, "min": 1, "max": 12}),
                "horizontal_lines_json": ("STRING", {"default": "[]"}),
                "vertical_lines_json": ("STRING", {"default": "[]"}),
            }
        }

    def split(
        self,
        image,
        enabled=False,
        rows=2,
        columns=2,
        horizontal_lines_json="[]",
        vertical_lines_json="[]",
    ):
        pieces, metadata = split_image_grid(
            image,
            enabled=enabled,
            rows=rows,
            columns=columns,
            horizontal_lines=_parse(horizontal_lines_json, "horizontal lines"),
            vertical_lines=_parse(vertical_lines_json, "vertical lines"),
        )
        return {
            "ui": {
                "text": [_json(metadata)],
                "apixly_free_v2": [{"kind": "grid", **metadata}],
            },
            "result": (pieces, _json(metadata)),
        }


class ApixlyEnhancementPrompt:
    CATEGORY = "Apixly/Prompt"
    FUNCTION = "build"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompt", "parameters_json", "aspect_ratio", "model")
    DESCRIPTION = "Free AI redraw-enhancement instruction. Connect prompt/parameters and your source image explicitly to Image: Edit. Editing is paid and may alter details; this is not pixel-preserving super-resolution."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "enabled": ("BOOLEAN", {"default": False}),
                "model": ("STRING", {"default": "gemini-3.1-flash-image"}),
                "width": ("INT", {"default": 1024, "min": 1, "max": 65536}),
                "height": ("INT", {"default": 1024, "min": 1, "max": 65536}),
            },
            "optional": {"reference_image": ("IMAGE",)},
        }

    def build(
        self,
        enabled=False,
        model="gemini-3.1-flash-image",
        width=1024,
        height=1024,
        reference_image=None,
    ):
        if type(enabled) is not bool:
            raise ValueError("enabled: expected a boolean.")
        if reference_image is not None:
            shape = getattr(reference_image, "shape", ())
            if len(shape) != 4 or shape[0] != 1 or shape[-1] not in (3, 4):
                raise ValueError(
                    "Enhancement preview requires one RGB/RGBA reference image."
                )
            height, width = int(shape[1]), int(shape[2])
        plan = build_enhancement_plan(model, width, height)
        result = (
            (plan["prompt"], _json(plan["parameters"]), plan["aspect"], model)
            if enabled
            else ("", "{}", "auto", model)
        )
        return {
            "ui": {
                "text": [result[0]],
                "apixly_free_v2": [
                    {
                        "kind": "enhancement",
                        "enabled": enabled,
                        "model": model,
                        "preview": plan,
                        "automatic_generation": False,
                    }
                ],
            },
            "result": result,
        }


class ApixlyCharacterSheetPlan:
    CATEGORY = "Apixly/Prompt"
    FUNCTION = "build"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("plan_json", "selected_prompt", "selected_aspect")
    DESCRIPTION = "Free original Studixly character-sheet planner. Select one shot explicitly; JSON previews all shots but never triggers batch generation. Seedance reference pack is three separate images. No guarantee of generated identity consistency."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "enabled": ("BOOLEAN", {"default": False}),
                "character": ("STRING", {"default": "", "multiline": True}),
                "style": ("STRING", {"default": ""}),
                "sheet_ids_json": ("STRING", {"default": '["key-visual"]'}),
                "custom": ("STRING", {"default": "", "multiline": True}),
                "shot_index": ("INT", {"default": -1, "min": -1, "max": 31}),
            }
        }

    def build(
        self,
        enabled=False,
        character="",
        style="",
        sheet_ids_json='["key-visual"]',
        custom="",
        shot_index=-1,
    ):
        plan = select_character_plan(
            {
                "character": character,
                "style": style,
                "sheetIds": _parse(sheet_ids_json, "sheet IDs"),
                "custom": custom,
            },
            enabled=enabled,
            shot_index=shot_index,
        )
        return {
            "ui": {
                "text": [plan["selected_prompt"]],
                "apixly_free_v2": [{"kind": "character", **plan}],
            },
            "result": (_json(plan), plan["selected_prompt"], plan["selected_aspect"]),
        }


FREE_V2_NODE_CLASS_MAPPINGS = {
    "ApixlyPromptEmotion": ApixlyPromptEmotion,
    "ApixlyPromptComposeV2": ApixlyPromptComposeV2,
    "ApixlyImageGridSplit": ApixlyImageGridSplit,
    "ApixlyEnhancementPrompt": ApixlyEnhancementPrompt,
    "ApixlyCharacterSheetPlan": ApixlyCharacterSheetPlan,
}
FREE_V2_NODE_DISPLAY_NAME_MAPPINGS = {
    "ApixlyPromptEmotion": "Apixly Prompt: Expression",
    "ApixlyPromptComposeV2": "Apixly Prompt: Compose V2",
    "ApixlyImageGridSplit": "Apixly Image: Grid Split",
    "ApixlyEnhancementPrompt": "Apixly Prompt: AI Enhancement",
    "ApixlyCharacterSheetPlan": "Apixly Prompt: Character Sheets",
}
