"""Canonical offline compiler for Apixly Creative Controls contract 1.0.0.

This standalone standard-library module is shared byte-for-byte with ComfyUI.
It performs no network, file, credential or generation operations.
Vocabulary comes from the pinned contract, not a model-generated rewrite.
"""

from __future__ import annotations

import math
import re
from typing import Any

CONTRACT_VERSION = "1.0.0"
CATALOG = {
    "angle": {
        "directionalPresets": {
            "front_high": "front view, high-angle shot, looking down at the subject",
            "front_low": "front view, low-angle shot, looking up from below",
            "aerial_top_down": "aerial view, bird's-eye view, top-down shot",
            "back": "back view, seen from behind",
        },
        "lensPresets": {
            "fisheye": "fisheye lens, distorted spherical wide-angle perspective",
            "dutch": "Dutch angle, tilted canted camera",
        },
        "yawSectors": [
            "",
            "three-quarter front view, from the right",
            "right side profile view",
            "three-quarter back view, from the right",
            "back view, seen from behind",
            "three-quarter back view, from the left",
            "left side profile view",
            "three-quarter front view, from the left",
        ],
        "shots": {
            "none": "",
            "extreme_long": "extreme long shot",
            "long": "long shot, full body in frame",
            "medium": "medium shot, from the waist up",
            "medium_close_up": "medium close-up",
            "close_up": "close-up shot",
        },
    },
    "lighting": {
        "presets": {
            "overexposedFilm": "overexposed film look, blown-out highlights, dreamy soft glow",
            "blueBacklight": "blue backlighting, cool blue rim light, glowing silhouette edges",
            "rembrandt": "Rembrandt lighting, key light at 45 degrees, triangle "
            "of light on the shadow-side cheek, chiaroscuro",
            "cyberpunk": "cyberpunk lighting, neon pink and cyan light sources, "
            "high-contrast neon rim lighting",
            "psychedelicSunset": "psychedelic sunset lighting, saturated magenta "
            "and orange glow, low sun backlight",
            "mysteriousDark": "low-key lighting, deep dramatic shadows, "
            "mysterious moody atmosphere",
            "goldenHour": "golden hour lighting, warm soft low-angle sunlight, long shadows",
            "nolanGray": "cool desaturated color grade, muted teal and slate "
            "gray tones, soft overcast cinematic light",
        },
        "keyLights": {
            "left": "key light from camera left, dramatic side lighting",
            "right": "key light from camera right, dramatic side lighting",
            "top": "overhead top lighting",
            "front": "frontal lighting, evenly lit",
            "bottom": "underlighting, lit from below",
            "back": "backlighting, subject lit from behind",
        },
        "lightAzNames": [
            "front",
            "front-right",
            "camera right",
            "back-right",
            "behind",
            "back-left",
            "camera left",
            "front-left",
        ],
        "hueSectors": [
            [15, "red"],
            [40, "orange"],
            [52, "amber"],
            [70, "yellow"],
            [150, "green"],
            [175, "teal"],
            [200, "cyan"],
            [260, "blue"],
            [300, "purple"],
            [330, "magenta"],
            [345, "pink"],
            [360, "red"],
        ],
    },
    "camera": {
        "bodies": {
            "arri-alexa-35": "ARRI Alexa 35",
            "sony-venice": "Sony Venice",
            "red-v-raptor": "RED V-Raptor",
            "panavision-dxl2": "Panavision Millennium DXL2",
            "imax-film": "IMAX 70mm film camera",
            "leica-m11": "Leica M11",
        },
        "lenses": {
            "cooke-anamorphic-sf": "Cooke Anamorphic/i SF 1.8x lens",
            "panavision-c-series": "Panavision C-Series anamorphic lens",
            "zeiss-master-prime": "Zeiss Master Prime lens",
            "canon-k35": "vintage Canon K-35 lens",
            "helios-44-2": "vintage Helios 44-2 lens",
            "lensbaby": "Lensbaby lens",
        },
        "apertures": ["", "f/1.4", "f/1.8", "f/2.8", "f/4", "f/5.6", "f/8", "f/11", "f/16"],
    },
}
EDIT_GUARD = "Preserve all subject and scene details that are not explicitly requested to change."


class CreativePromptError(ValueError):
    """Invalid input; messages identify fields without echoing their values."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.field_path = path
        super().__init__(f"{path}: {reason}.")


def _fail(path: str, reason: str) -> None:
    raise CreativePromptError(path, reason)


def _object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(path, "must be an object")
    return value


def _known_fields(value: dict, allowed: set[str], path: str = "") -> None:
    for key in value:
        if key not in allowed:
            field = (
                str(key)
                if isinstance(key, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)
                else "unknown_field"
            )
            _fail(f"{path}.{field}" if path else field, "unknown field")


def _units(value: str) -> int:
    return len(value.encode("utf-16-le", errors="surrogatepass")) // 2


def _string(value: Any, path: str, limit: int | None = None) -> str:
    if type(value) is not str:
        _fail(path, "must be a string")
    if limit is not None and _units(value) > limit:
        _fail(path, "exceeds the allowed UTF-16 length")
    return value


def _enum(value: Any, allowed: set[str], path: str) -> None:
    if type(value) is not str or value not in allowed:
        _fail(path, "must be a supported option")


def _boolean(value: Any, path: str) -> None:
    if type(value) is not bool:
        _fail(path, "must be a boolean")


def _number(value: Any, low: float, high: float, path: str, integer: bool = False) -> None:
    if type(value) not in (int, float):
        _fail(path, "must be a finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value < low or value > high:
        _fail(path, "must be a finite number within the allowed range")
    if integer and int(value) != value:
        _fail(path, "must be an integer")


def _validate_group(name: str, value: Any) -> dict[str, Any]:
    group = _object(value, "tools." + name)
    allowed = {
        "angle": {"enabled", "preset", "yaw", "pitch", "shot", "showPrompt"},
        "lighting": {
            "enabled",
            "preset",
            "view",
            "brightness",
            "color",
            "keyLight",
            "lightYaw",
            "lightPitch",
            "rimLight",
            "smartText",
        },
        "camera": {"enabled", "body", "lens", "focal", "aperture"},
    }[name]
    _known_fields(group, allowed, "tools." + name)
    for field, value in group.items():
        path = f"tools.{name}.{field}"
        if field in {"enabled", "showPrompt", "rimLight"}:
            _boolean(value, path)
        elif field in {"yaw", "lightYaw"}:
            _number(value, -360000, 360000, path)
        elif field in {"pitch", "lightPitch"}:
            _number(value, -90, 90, path)
        elif field == "brightness":
            _number(value, 0, 100, path)
        elif field == "focal":
            if value is not None:
                _number(value, 8, 800, path, integer=True)
        elif field == "smartText":
            _string(value, path, 1000)
        elif field == "color":
            _string(value, path)
            if value and not re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", value):
                _fail(path, "must be empty or a hexadecimal RGB color")
            if group.get("enabled") is True and value.lower() in {"#000", "#000000"}:
                _fail(path, "black is not a light color; reduce brightness instead")
        elif field == "preset":
            options = (
                {
                    "custom",
                    *CATALOG["angle"]["directionalPresets"],
                    *CATALOG["angle"]["lensPresets"],
                }
                if name == "angle"
                else {"", *CATALOG["lighting"]["presets"]}
            )
            _enum(value, options, path)
        elif field == "shot":
            _enum(value, set(CATALOG["angle"]["shots"]), path)
        elif field == "keyLight":
            _enum(value, {"", *CATALOG["lighting"]["keyLights"]}, path)
        elif field == "view":
            _enum(value, {"perspective", "front"}, path)
        elif field == "body":
            _enum(value, {"", *CATALOG["camera"]["bodies"]}, path)
        elif field == "lens":
            _enum(value, {"", *CATALOG["camera"]["lenses"]}, path)
        elif field == "aperture":
            _enum(value, set(CATALOG["camera"]["apertures"]), path)
    return group


def _round(value: float) -> int:
    floor = math.floor(value)
    return floor + 1 if value - floor >= 0.5 else floor


def _wrap_yaw(value: float) -> float:
    return math.fmod(math.fmod(value, 360) + 360, 360)


_JS_TRIM_WHITESPACE = "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"


def _angle(group: dict[str, Any]) -> str:
    if group.get("enabled") is not True:
        return ""
    preset = group.get("preset", "custom")
    yaw = group.get("yaw", 0)
    pitch = group.get("pitch", 0)
    pieces = []
    directional = CATALOG["angle"]["directionalPresets"].get(preset)
    if directional:
        pieces.append(directional)
    else:
        pieces.append(CATALOG["angle"]["lensPresets"].get(preset, ""))
        sector = math.floor(((_wrap_yaw(yaw) + 22.5) % 360) / 45) % 8
        pieces.append(CATALOG["angle"]["yawSectors"][sector])
        if pitch >= 60:
            pieces.append("bird's-eye view, top-down shot, directly overhead")
        elif pitch > 15:
            pieces.append("high-angle shot, looking down at the subject")
        elif pitch < -15:
            pieces.append(
                "low-angle shot, looking up from below"
                if pitch > -60
                else "worm's-eye view, extreme low angle"
            )
        orientation = []
        azimuth = _round(yaw) % 360
        elevation = _round(pitch)
        if azimuth:
            orientation.append(f"{azimuth}° azimuth")
        if elevation:
            orientation.append(f"{elevation}° elevation")
        if orientation:
            pieces.append("(" + ", ".join(orientation) + ")")
    pieces.append(CATALOG["angle"]["shots"][group.get("shot", "none")])
    return ", ".join(x for x in pieces if x)


def _color(hex_value: str) -> str:
    if not hex_value:
        return ""
    raw = hex_value[1:]
    if len(raw) == 3:
        raw = "".join(x * 2 for x in raw)
    red, green, blue = [int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    highest, lowest = max(red, green, blue), min(red, green, blue)
    delta = highest - lowest
    lightness = (highest + lowest) / 2
    saturation = 0 if delta == 0 else delta / (1 - abs(2 * lightness - 1))
    if saturation < 0.15:
        return "white"
    if highest == red:
        hue = 60 * (((green - blue) / delta) % 6)
    elif highest == green:
        hue = 60 * ((blue - red) / delta + 2)
    else:
        hue = 60 * ((red - green) / delta + 4)
    if hue < 0:
        hue += 360
    for upper, name in CATALOG["lighting"]["hueSectors"]:
        if hue < upper:
            return name
    return "red"


def _lighting(group: dict[str, Any]) -> str:
    if group.get("enabled") is not True:
        return ""
    pieces = [CATALOG["lighting"]["presets"].get(group.get("preset", ""), "")]
    color = _color(group.get("color", ""))
    direction = ""
    if "lightYaw" in group or "lightPitch" in group:
        azimuth = _round(group.get("lightYaw", 0)) % 360
        elevation = _round(group.get("lightPitch", 0))
        if azimuth or elevation:
            sector = math.floor(((azimuth + 22.5) % 360) / 45) % 8
            position = []
            if sector:
                position.append(CATALOG["lighting"]["lightAzNames"][sector])
            if elevation >= 45:
                position.append("high above")
            elif elevation >= 15:
                position.append("above")
            elif elevation <= -45:
                position.append("far below")
            elif elevation <= -15:
                position.append("below")
            where = " ".join(position) or "front"
            direction = f"key light from the {where} ({azimuth}° azimuth, {elevation}° elevation)"
    else:
        direction = CATALOG["lighting"]["keyLights"].get(group.get("keyLight", ""), "")
    if direction:
        pieces.append((color + " " if color else "") + direction)
    brightness = group.get("brightness", 50)
    if brightness <= 14:
        pieces.append("very dim lighting, deep shadows")
    elif brightness <= 39:
        pieces.append("dim, subdued lighting")
    elif brightness <= 60:
        pass
    elif brightness <= 85:
        pieces.append("bright, well-lit")
    else:
        pieces.append("very bright, high-key lighting")
    if color and not direction:
        pieces.append(color + " light")
    if group.get("rimLight", False):
        pieces.append("rim lighting outlining the subject's edges")
    smart = group.get("smartText", "").strip(_JS_TRIM_WHITESPACE)
    if smart:
        pieces.append("lighting style: " + smart)
    return ", ".join(x for x in pieces if x)


def _camera(group: dict[str, Any]) -> str:
    if group.get("enabled") is not True:
        return ""
    pieces = []
    body = CATALOG["camera"]["bodies"].get(group.get("body", ""))
    lens = CATALOG["camera"]["lenses"].get(group.get("lens", ""))
    if body and lens:
        pieces.append(f"shot on {body} with {lens}")
    elif body:
        pieces.append("shot on " + body)
    elif lens:
        pieces.append("shot with " + lens)
    focal = group.get("focal")
    if focal is not None:
        focal = int(focal)
        if focal <= 20:
            pieces.append(f"ultra wide-angle {focal}mm")
        elif focal <= 32:
            pieces.append(f"wide-angle {focal}mm")
        elif focal >= 85:
            pieces.append(f"{focal}mm telephoto")
        else:
            pieces.append(f"{focal}mm")
    aperture = group.get("aperture", "")
    if aperture:
        pieces.append(aperture)
        if aperture in {"f/1.4", "f/1.8"}:
            pieces.append("shallow depth of field")
        elif aperture in {"f/8", "f/11", "f/16"}:
            pieces.append("deep focus")
    return ", ".join(pieces)


def compose_creative_prompt(payload: Any) -> dict[str, Any]:
    """Compile validated AI art direction without changing inactive prompts."""
    payload = _object(payload, "payload")
    _known_fields(payload, {"prompt", "mode", "tools"})
    prompt = _string(payload.get("prompt"), "prompt", 20000)
    mode = payload.get("mode", "generate")
    _enum(mode, {"generate", "edit"}, "mode")
    tools = _object(payload.get("tools", {}), "tools")
    _known_fields(tools, {"angle", "lighting", "camera"}, "tools")
    groups = {name: _validate_group(name, value) for name, value in tools.items()}
    sections = []
    for name, label, builder in [
        ("angle", "Camera", _angle),
        ("lighting", "Lighting", _lighting),
        ("camera", "Lens", _camera),
    ]:
        fragment = builder(groups.get(name, {}))
        if not fragment:
            continue
        if mode == "generate":
            text = f"{label}: {fragment}"
        elif name == "angle":
            text = f"Change the camera angle: re-photograph the exact same subject from {fragment}."
        elif name == "lighting":
            text = f"Change the lighting: relight the same scene with {fragment}."
        else:
            text = f"Change the camera and lens style: make it look {fragment}."
        sections.append({"tool": name, "label": label, "text": text})
    final = prompt
    if sections:
        lines = [x["text"] for x in sections]
        if mode == "edit":
            lines.append(EDIT_GUARD)
        final = (prompt + "\n\n" if prompt else "") + "\n".join(lines)
    if _units(final) > 20000:
        _fail("final_prompt", "exceeds the allowed UTF-16 length")
    return {
        "final_prompt": final,
        "sections": sections,
        "applied_tools": [x["tool"] for x in sections],
        "changed": final != prompt,
    }
