"""Free native ComfyUI prompt controls. No client, credentials or task journal."""

import json

from .creative_compiler import compose_creative_prompt

ANGLE_PRESETS = [
    "custom",
    "fisheye",
    "dutch",
    "front_high",
    "front_low",
    "aerial_top_down",
    "back",
]
SHOTS = ["none", "extreme_long", "long", "medium", "medium_close_up", "close_up"]
LIGHT_PRESETS = [
    "none",
    "overexposedFilm",
    "blueBacklight",
    "rembrandt",
    "cyberpunk",
    "psychedelicSunset",
    "mysteriousDark",
    "goldenHour",
    "nolanGray",
]
BODIES = [
    "none",
    "arri-alexa-35",
    "sony-venice",
    "red-v-raptor",
    "panavision-dxl2",
    "imax-film",
    "leica-m11",
]
LENSES = [
    "none",
    "cooke-anamorphic-sf",
    "panavision-c-series",
    "zeiss-master-prime",
    "canon-k35",
    "helios-44-2",
    "lensbaby",
]
APERTURES = ["none", "f/1.4", "f/1.8", "f/2.8", "f/4", "f/5.6", "f/8", "f/11", "f/16"]


def _flag(value, path):
    if not isinstance(value, bool):
        raise ValueError(f"{path}: expected a boolean.")
    return value


def _unspecified(value):
    return "" if value == "none" else value


def _control_result(kind, settings):
    result = compose_creative_prompt({"prompt": "", "tools": {kind: settings}})
    fragment = result["final_prompt"]
    return {
        "ui": {"text": [fragment], "apixly_prompt": [result]},
        "result": (settings, fragment),
    }


class ApixlyPromptViewpoint:
    CATEGORY = "Apixly/Prompt"
    FUNCTION = "build"
    OUTPUT_NODE = True
    RETURN_TYPES = ("APIXLY_ANGLE", "STRING")
    RETURN_NAMES = ("angle", "instruction")
    DESCRIPTION = "Free prompt guidance, not a precise 3D camera API. No generation."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "enabled": ("BOOLEAN", {"default": False}),
                "preset": (ANGLE_PRESETS,),
                "yaw": (
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": 0,
                        "max": 360,
                        "step": 1.0,
                        "tooltip": "Azimuth: 0 front, 90 right, 180 back, 270 left.",
                    },
                ),
                "pitch": (
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": -90,
                        "max": 90,
                        "step": 1.0,
                        "tooltip": "Positive elevation is above the subject.",
                    },
                ),
                "shot": (SHOTS,),
            }
        }

    def build(self, enabled=False, preset="custom", yaw=0, pitch=0, shot="none"):
        return _control_result(
            "angle",
            {
                "enabled": enabled,
                "preset": preset,
                "yaw": yaw,
                "pitch": pitch,
                "shot": shot,
            },
        )


class ApixlyPromptLighting:
    CATEGORY = "Apixly/Prompt"
    FUNCTION = "build"
    OUTPUT_NODE = True
    RETURN_TYPES = ("APIXLY_LIGHTING", "STRING")
    RETURN_NAMES = ("lighting", "instruction")
    DESCRIPTION = (
        "Free lighting instructions. The diagram is not a physical light simulation."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "enabled": ("BOOLEAN", {"default": False}),
                "preset": (LIGHT_PRESETS,),
                "brightness": (
                    "FLOAT",
                    {"default": 50.0, "min": 0, "max": 100, "step": 1.0},
                ),
                "use_color": ("BOOLEAN", {"default": False}),
                "color": (
                    "STRING",
                    {
                        "default": "#2e8fff",
                        "tooltip": "Optional #RGB/#RRGGBB. Black is not an active light color; lower brightness instead.",
                    },
                ),
                "view": (["perspective", "front"],),
                "direction": (["unspecified", "legacy", "orbit"],),
                "key_light": (
                    ["none", "left", "top", "right", "front", "bottom", "back"],
                ),
                "light_yaw": (
                    "FLOAT",
                    {"default": 0.0, "min": 0, "max": 360, "step": 1.0},
                ),
                "light_pitch": (
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": -90,
                        "max": 90,
                        "step": 1.0,
                        "tooltip": "Positive elevation puts the light above the subject.",
                    },
                ),
                "rim_light": ("BOOLEAN", {"default": False}),
                "smart_text": ("STRING", {"default": "", "multiline": True}),
            }
        }

    def build(
        self,
        enabled=False,
        preset="none",
        brightness=50,
        use_color=False,
        color="#2e8fff",
        view="perspective",
        direction="unspecified",
        key_light="none",
        light_yaw=0,
        light_pitch=0,
        rim_light=False,
        smart_text="",
    ):
        if direction not in {"unspecified", "legacy", "orbit"}:
            raise ValueError("lighting.direction: choose unspecified, legacy or orbit.")
        settings = {
            "enabled": enabled,
            "preset": _unspecified(preset),
            "brightness": brightness,
            "color": color if _flag(use_color, "lighting.use_color") else "",
            "view": view,
            "rimLight": rim_light,
            "smartText": smart_text,
        }
        if direction == "legacy":
            settings["keyLight"] = _unspecified(key_light)
        elif direction == "orbit":
            settings.update(lightYaw=light_yaw, lightPitch=light_pitch)
        return _control_result("lighting", settings)


class ApixlyPromptCamera:
    CATEGORY = "Apixly/Prompt"
    FUNCTION = "build"
    OUTPUT_NODE = True
    RETURN_TYPES = ("APIXLY_CAMERA", "STRING")
    RETURN_NAMES = ("camera", "instruction")
    DESCRIPTION = "Free camera/lens style guidance, not real camera metadata or optics."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "enabled": ("BOOLEAN", {"default": False}),
                "body": (BODIES,),
                "lens": (LENSES,),
                "use_focal": ("BOOLEAN", {"default": False}),
                "focal": ("INT", {"default": 50, "min": 8, "max": 800, "step": 1}),
                "aperture": (APERTURES,),
            }
        }

    def build(
        self,
        enabled=False,
        body="none",
        lens="none",
        use_focal=False,
        focal=50,
        aperture="none",
    ):
        return _control_result(
            "camera",
            {
                "enabled": enabled,
                "body": _unspecified(body),
                "lens": _unspecified(lens),
                "focal": focal if _flag(use_focal, "camera.use_focal") else None,
                "aperture": _unspecified(aperture),
            },
        )


class ApixlyPromptCompose:
    CATEGORY = "Apixly/Prompt"
    FUNCTION = "compose"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("final_prompt", "controls_json")
    DESCRIPTION = "Free composition. Recomputes the prompt from typed controls. Connect final_prompt explicitly to a generation node."

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
                "camera": ("APIXLY_CAMERA",),
            },
        }

    def compose(self, prompt, mode="generate", angle=None, lighting=None, camera=None):
        tools = {
            key: value
            for key, value in {
                "angle": angle,
                "lighting": lighting,
                "camera": camera,
            }.items()
            if value is not None
        }
        payload = {"prompt": prompt, "mode": mode, "tools": tools}
        result = compose_creative_prompt(payload)
        return {
            "ui": {"text": [result["final_prompt"]], "apixly_prompt": [result]},
            "result": (result["final_prompt"], json.dumps(payload, ensure_ascii=False)),
        }
