"""ComfyUI V1 nodes: explicit paid submissions and independently resumable reads."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import uuid
from pathlib import Path

from .client import (
    MAX_IMAGE_BYTES,
    ApixlyClient,
    ApixlyError,
    checked_parameters,
    public_receipt,
    safe_media_url,
)
from .creative_nodes import (
    ApixlyPromptCamera,
    ApixlyPromptCompose,
    ApixlyPromptLighting,
    ApixlyPromptViewpoint,
)
from .journal import SubmissionJournal


def parse_parameters(text):
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        raise ValueError("Parameters must be a valid JSON object.") from None
    return checked_parameters(value)


def parse_reference_urls(value):
    if not value:
        return []
    if not isinstance(value, str):
        raise ValueError("Reference image URLs must be HTTPS text or a JSON array.")
    try:
        urls = (
            json.loads(value) if value.lstrip().startswith("[") else value.splitlines()
        )
        if not isinstance(urls, list) or not 1 <= len(urls) <= 16:
            raise ValueError("Provide 1–16 public HTTPS reference image URLs.")
        if any(not isinstance(url, str) or not url.strip() for url in urls):
            raise ValueError("Every reference must be a nonempty public HTTPS URL.")
        return [safe_media_url(url.strip()) for url in urls]
    except (ValueError, TypeError, ApixlyError):
        raise ValueError(
            "References require public HTTPS image URLs. Connect Image: Result result_urls_json to reference_image_urls; local data URLs are not accepted here."
        ) from None


def encode_images(images):
    if images is None:
        return []
    import numpy as np
    from PIL import Image

    array = images.detach().cpu().numpy()
    if (
        len(array.shape) != 4
        or array.shape[-1] not in {3, 4}
        or not 1 <= array.shape[0] <= 16
    ):
        raise ValueError(
            "Reference IMAGE must be a batch of 1–16 RGB/RGBA images [B,H,W,C]."
        )
    result = []
    for image in array:
        buffer = io.BytesIO()
        Image.fromarray(np.clip(image * 255.0, 0, 255).astype(np.uint8)).save(
            buffer, format="PNG"
        )
        result.append(buffer.getvalue())
    return result


def encode_mask(mask, width, height):
    import numpy as np
    from PIL import Image

    array = mask.detach().cpu().numpy()
    if len(array.shape) == 3 and array.shape[0] == 1:
        array = array[0]
    if array.shape != (height, width):
        raise ValueError(
            "Mask must be one image with the exact reference width and height."
        )
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    pixels[:, :, 3] = np.clip((1.0 - array) * 255.0, 0, 255).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    return buffer.getvalue()


def decode_images(values):
    import numpy as np
    import torch
    from PIL import Image, ImageOps

    tensors = []
    for value in values:
        try:
            with Image.open(io.BytesIO(value)) as image:
                if image.width * image.height > 64_000_000:
                    raise ValueError("Generated image exceeds 64 megapixels.")
                image = ImageOps.exif_transpose(image).convert("RGB")
                tensors.append(
                    torch.from_numpy(
                        np.array(image).astype(np.float32) / 255.0
                    ).unsqueeze(0)
                )
        except (OSError, ValueError):
            raise ApixlyError(
                "Result could not be decoded as an image; resume the existing task ID."
            ) from None
    # Comfy IMAGE batches require matching dimensions. Never silently resize.
    if len({tuple(t.shape) for t in tensors}) != 1:
        raise ApixlyError(
            "Image results have different dimensions. Request n=1 or retrieve each result separately; no images were resized."
        )
    return torch.cat(tensors, dim=0)


def _state_path():
    if os.environ.get("APIXLY_STATE_DIR"):
        return Path(os.environ["APIXLY_STATE_DIR"]) / "submissions.sqlite3"
    import folder_paths

    return Path(folder_paths.get_user_directory()) / "apixly" / "submissions.sqlite3"


def _fingerprint(api, kind, model, prompt, params, nonce, images=(), mask=None):
    if not isinstance(nonce, int) or nonce < 0:
        raise ValueError("request_nonce must be a nonnegative integer.")
    digest = hashlib.sha256()
    digest.update(hashlib.sha256(api._api_key.encode()).digest())
    digest.update(
        json.dumps(
            [kind, model, prompt, params, nonce], sort_keys=True, allow_nan=False
        ).encode()
    )
    for value in images:
        digest.update(hashlib.sha256(value).digest())
    if mask:
        digest.update(hashlib.sha256(mask).digest())
    return digest.hexdigest()


def _submit_inputs(default_model="grok-imagine-image"):
    return {
        "model": (
            "STRING",
            {
                "default": default_model,
                "tooltip": "Exact model ID. The suggested model passed a bounded live smoke test; other models require qualification.",
            },
        ),
        "prompt": ("STRING", {"multiline": True, "default": ""}),
        "parameters_json": (
            "STRING",
            {
                "multiline": True,
                "default": "{}",
                "tooltip": "Advanced model-specific JSON. Core fields and credentials cannot be overridden.",
            },
        ),
        "request_nonce": (
            "INT",
            {
                "default": 0,
                "min": 0,
                "max": 9007199254740991,
                "control_after_generate": True,
                "tooltip": "A new nonce creates a new paid action. Keep this nonce to recover a previous submission.",
            },
        ),
    }


def _progress():
    try:
        from comfy.model_management import throw_exception_if_processing_interrupted
        from comfy.utils import ProgressBar
    except ImportError:
        return None
    progress = ProgressBar(100)

    def report(job):
        throw_exception_if_processing_interrupted()
        value = job.get(
            "progress", 100 if job.get("status") in {"succeeded", "completed"} else 0
        )
        progress.update_absolute(max(0, min(100, int(value))), 100)

    return report


def _ui_result(values, job, kind, preview=None):
    detail = {
        "task_id": job.get("id", ""),
        "status": job.get("status", "unknown"),
        "kind": kind,
        "url": job.get("url", ""),
    }
    if not detail["url"] and job.get("data"):
        detail["url"] = job["data"][0].get("url", "")
    ui = {
        "text": [f"{kind.title()} task {detail['task_id']}: {detail['status']}"],
        "apixly": [detail],
    }
    if preview:
        ui.update(preview)
        detail["saved"] = preview["images"][0]
    return {"ui": ui, "result": values}


def _image_previews(tensors, identifier):
    import folder_paths
    import numpy as np
    from PIL import Image

    directory = Path(folder_paths.get_temp_directory()) / "apixly"
    directory.mkdir(parents=True, exist_ok=True)
    previews = []
    for index, tensor in enumerate(tensors):
        filename = f"image-{identifier}-{uuid.uuid4().hex[:8]}-{index}.png"
        Image.fromarray(
            np.clip(tensor.cpu().numpy() * 255, 0, 255).astype(np.uint8)
        ).save(directory / filename)
        previews.append({"filename": filename, "subfolder": "apixly", "type": "temp"})
    return {"images": previews}


class ApixlyImageSubmit:
    ALLOW_REFERENCES = False
    CATEGORY = "Apixly/Media"
    FUNCTION = "submit"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("task_id", "submission_json")
    DESCRIPTION = "Submit one paid text-to-image job. Use Apixly Image: Edit for references. Credentials come only from the server environment."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": _submit_inputs()}

    def submit(
        self,
        model,
        prompt,
        parameters_json,
        request_nonce,
        reference_images=None,
        mask=None,
    ):
        if mask is not None:
            raise ValueError(
                "Masked editing is not available in this version. Use reference-image editing instead."
            )
        if reference_images is not None and not self.ALLOW_REFERENCES:
            raise ValueError(
                "Use Apixly Image: Edit for reference images; this node only generates images from text."
            )
        if self.ALLOW_REFERENCES and reference_images is None:
            raise ValueError(
                "Apixly Image: Edit requires at least one reference image."
            )
        parameters = parse_parameters(parameters_json)
        api = ApixlyClient.from_environment()
        images = encode_images(reference_images)
        mask_bytes = None
        fingerprint = _fingerprint(
            api, "image", model, prompt, parameters, request_nonce, images, mask_bytes
        )
        job = SubmissionJournal(_state_path()).submit_once(
            fingerprint,
            lambda: api.submit_image(
                model, prompt, parameters, images=images, mask=mask_bytes
            ),
        )
        return _ui_result((job["id"], json.dumps(job)), job, "image")


class ApixlyImageEdit(ApixlyImageSubmit):
    ALLOW_REFERENCES = True
    DESCRIPTION = "Edit required reference images with an exact model. Gemini 3.1 Flash Image passed the initial reference-preservation smoke test."

    @classmethod
    def INPUT_TYPES(cls):
        required = _submit_inputs("gemini-3.1-flash-image")
        required["reference_images"] = ("IMAGE",)
        return {"required": required}


class ApixlyImageResult:
    CATEGORY = "Apixly/Media"
    FUNCTION = "result"
    OUTPUT_NODE = True
    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("images", "result_urls_json", "receipt_json")
    DESCRIPTION = "Wait for and download an existing image job. This node never submits generation."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {"default": ""}),
                "timeout_seconds": ("INT", {"default": 600, "min": 1, "max": 3600}),
                "poll_interval": ("FLOAT", {"default": 3.0, "min": 0.5, "max": 60.0}),
            }
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")  # Refresh status/expiring media when explicitly queued.

    def result(self, task_id, timeout_seconds=600, poll_interval=3.0):
        api = ApixlyClient.from_environment()
        job = api.wait_job(
            "image",
            task_id,
            timeout_seconds=timeout_seconds,
            poll_interval=poll_interval,
            on_progress=_progress(),
        )
        values = api.image_bytes(job)
        urls = [item.get("url", "") for item in job.get("data", [])]
        images = decode_images(values)
        return _ui_result(
            (images, json.dumps(urls), json.dumps(public_receipt(job))),
            job,
            "image",
            _image_previews(images, task_id),
        )


class ApixlyVideoSubmit:
    CATEGORY = "Apixly/Media"
    FUNCTION = "submit"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("task_id", "submission_json")
    DESCRIPTION = "Submit one paid video job via /v1/videos. Supply model-specific flat parameters as JSON."

    @classmethod
    def INPUT_TYPES(cls):
        inputs = _submit_inputs("grok-imagine-video")
        inputs["seconds"] = (
            "INT",
            {
                "default": 3,
                "min": 1,
                "max": 30,
                "tooltip": "Output seconds. Verify the exact model's supported range; no duration is changed silently.",
            },
        )
        inputs["resolution"] = (
            ["720p", "480p", "1080p", "768p", "1440p", "4k", "model_default"],
            {"default": "720p"},
        )
        inputs["aspect_ratio"] = (
            ["16:9", "9:16", "1:1", "21:9", "3:4", "4:3", "adaptive", "model_default"],
            {"default": "16:9"},
        )
        return {
            "required": inputs,
            "optional": {
                "reference_images": ("IMAGE",),
                "reference_image_urls": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "Public HTTPS image URLs, as a JSON array or one per line. Connect Image: Result result_urls_json. Grok image-to-video requires URLs rather than local IMAGE data.",
                    },
                ),
            },
        }

    def submit(
        self,
        model,
        prompt,
        parameters_json,
        request_nonce,
        reference_images=None,
        seconds=None,
        resolution=None,
        aspect_ratio=None,
        reference_image_urls="",
    ):
        urls = parse_reference_urls(reference_image_urls)
        if reference_images is not None and urls:
            raise ValueError(
                "Choose one reference source: local IMAGE or reference_image_urls, not both."
            )
        if reference_images is not None and model == "grok-imagine-video-1.5-preview":
            raise ValueError(
                "grok-imagine-video-1.5-preview requires public HTTPS references. Connect Image: Result result_urls_json to reference_image_urls; no upload or generation was submitted."
            )
        parameters = parse_parameters(parameters_json)
        if model == "grok-imagine-video-1.5-preview" and (
            urls or reference_images is not None
        ):
            geometry_fields = {
                "resolution",
                "aspect_ratio",
                "size",
                "ratio",
                "width",
                "height",
            }
            if (
                resolution not in {None, "model_default"}
                or aspect_ratio not in {None, "model_default"}
                or geometry_fields.intersection(parameters)
            ):
                raise ValueError(
                    "Explicit geometry is not qualified for this reference-video route. Set resolution and aspect_ratio to model_default and remove geometry fields from advanced JSON. Source framing is used; actual dimensions are reported by the result."
                )
        for name, value in {
            "seconds": seconds,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
        }.items():
            if name in {"resolution", "aspect_ratio"} and value == "model_default":
                if name in parameters:
                    raise ValueError(
                        f"{name}=model_default conflicts with the explicit value in advanced JSON."
                    )
                continue
            if value is not None:
                if name in parameters and parameters[name] != value:
                    raise ValueError(
                        f"{name} conflicts with advanced parameters. Choose one consistent value before submitting."
                    )
                parameters[name] = value
        api = ApixlyClient.from_environment()
        images = encode_images(reference_images)
        if images or urls:
            capabilities = api._json("GET", "/video/config")
            for capability in capabilities.get("data", []):
                if not isinstance(capability, dict) or capability.get("model") != model:
                    continue
                modes = capability.get("modes", [])
                if modes and not {"image2video", "frames2video"}.intersection(modes):
                    raise ValueError(
                        f"{model} currently supports text2video only. Keep your references and explicitly select an image2video model such as grok-imagine-video-1.5-preview; no model was changed and no generation was submitted."
                    )
                break
        references = [
            "data:image/png;base64," + base64.b64encode(image).decode("ascii")
            for image in images
        ]
        reference_fingerprints = list(images)
        if urls:
            from PIL import Image

            for url in urls:
                try:
                    media = api._media(url, max_bytes=MAX_IMAGE_BYTES)
                    with Image.open(io.BytesIO(media.body)) as image:
                        if image.width * image.height > 64_000_000:
                            raise ValueError("Reference exceeds the pixel limit.")
                        image.verify()
                    reference_fingerprints.append(hashlib.sha256(media.body).digest())
                except (ApixlyError, OSError, ValueError):
                    raise ValueError(
                        "Reference URL could not be read as an image. Refresh the source URL and retry; no generation was submitted. Existing task IDs can still be recovered with Video: Result."
                    ) from None
            references = urls
        fingerprint = _fingerprint(
            api,
            "video",
            model,
            prompt,
            parameters,
            request_nonce,
            reference_fingerprints,
        )
        job = SubmissionJournal(_state_path()).submit_once(
            fingerprint,
            lambda: api.submit_video(model, prompt, parameters, images=references),
        )
        return _ui_result((job["id"], json.dumps(job)), job, "video")


class ApixlyTaskStatus:
    CATEGORY = "Apixly/Media"
    FUNCTION = "status"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("status", "result_url", "receipt_json")
    DESCRIPTION = "Query an existing task once. This node never submits generation."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "kind": (["image", "video"],),
                "task_id": ("STRING", {"default": ""}),
            }
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def status(self, kind, task_id):
        job = ApixlyClient.from_environment().get_job(kind, task_id)
        image_url = (job.get("data") or [{}])[0].get("url", "")
        return _ui_result(
            (
                str(job.get("status", "unknown")),
                job.get("url", image_url),
                json.dumps(public_receipt(job)),
            ),
            job,
            kind,
        )


class ApixlyVideoResult:
    CATEGORY = "Apixly/Media"
    FUNCTION = "result"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("video_path", "result_url", "receipt_json")
    DESCRIPTION = "Wait for an existing video task and optionally download its terminal video. Never submits generation."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {"default": ""}),
                "timeout_seconds": ("INT", {"default": 900, "min": 1, "max": 3600}),
                "poll_interval": ("FLOAT", {"default": 3.0, "min": 0.5, "max": 60.0}),
                "download_video": ("BOOLEAN", {"default": True}),
            }
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def result(
        self, task_id, timeout_seconds=900, poll_interval=3.0, download_video=True
    ):
        api = ApixlyClient.from_environment()
        job = api.wait_job(
            "video",
            task_id,
            timeout_seconds=timeout_seconds,
            poll_interval=poll_interval,
            on_progress=_progress(),
        )
        video_path = ""
        preview = None
        if download_video:
            import folder_paths

            destination = (
                Path(folder_paths.get_output_directory())
                / "apixly"
                / f"video-{task_id}-{uuid.uuid4().hex[:8]}.mp4"
            )
            video_path = str(api.download_video(job, destination))
            preview = {
                "images": [
                    {
                        "filename": Path(video_path).name,
                        "subfolder": "apixly",
                        "type": "output",
                    }
                ],
                "animated": [True],
            }
        return _ui_result(
            (video_path, job.get("url", ""), json.dumps(public_receipt(job))),
            job,
            "video",
            preview,
        )


NODE_CLASS_MAPPINGS = {
    cls.__name__: cls
    for cls in (
        ApixlyImageSubmit,
        ApixlyImageEdit,
        ApixlyImageResult,
        ApixlyVideoSubmit,
        ApixlyTaskStatus,
        ApixlyVideoResult,
        ApixlyPromptViewpoint,
        ApixlyPromptLighting,
        ApixlyPromptCamera,
        ApixlyPromptCompose,
    )
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "ApixlyImageSubmit": "Apixly Image: Submit",
    "ApixlyImageEdit": "Apixly Image: Edit",
    "ApixlyImageResult": "Apixly Image: Result",
    "ApixlyVideoSubmit": "Apixly Video: Submit",
    "ApixlyTaskStatus": "Apixly Task: Status",
    "ApixlyVideoResult": "Apixly Video: Result",
    "ApixlyPromptViewpoint": "Apixly Prompt: Viewpoint",
    "ApixlyPromptLighting": "Apixly Prompt: Lighting",
    "ApixlyPromptCamera": "Apixly Prompt: Camera & Lens",
    "ApixlyPromptCompose": "Apixly Prompt: Compose",
}
