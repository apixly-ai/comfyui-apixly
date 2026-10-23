"""Explicit, paid live node smoke test. Supply a limited key fixture and output path.

This invokes the shipped node methods with actual tensors/HTTP. It does not claim
to exercise ComfyUI's canvas or graph executor. Run only with spending approval.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apixly_media.client import ApixlyClient, HTTPXTransport
from apixly_media.nodes import (
    ApixlyImageResult,
    ApixlyImageSubmit,
    ApixlyVideoResult,
    ApixlyVideoSubmit,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-fixture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--image-model", required=True)
    parser.add_argument("--edit-model", required=True)
    parser.add_argument("--video-model", required=True)
    parser.add_argument("--video-seconds", type=int, default=3)
    parser.add_argument(
        "--skip-video",
        action="store_true",
        help="Recover image tasks only; reserve the planned video submit for host verification.",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(args.output, 0o700)
    fixture = json.loads(args.key_fixture.read_text())
    os.environ["APIXLY_API_KEY"] = fixture["key"]
    os.environ["APIXLY_STATE_DIR"] = str(args.output / "state")
    report_path = args.output / "report.json"
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "verification_scope": "Actual shipped node methods, live public REST, real tensor conversion, downloaded terminal files; ComfyUI canvas/executor not exercised",
        "steps": [],
    }

    def save_report():
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        os.chmod(report_path, 0o600)

    class TraceTransport(HTTPXTransport):
        def request(self, method, url, **kwargs):
            from urllib.parse import urlsplit

            result = super().request(method, url, **kwargs)
            parsed = urlsplit(url)
            entry = {
                "at": datetime.now(timezone.utc).isoformat(),
                "method": method,
                "host": parsed.hostname,
                "path": parsed.path,
                "status": result.status,
                "request_id": result.headers.get("x-request-id"),
                "response_bytes": len(result.body),
            }
            with (args.output / "http-events.jsonl").open("a") as stream:
                stream.write(json.dumps(entry) + "\n")
            return result

    api = ApixlyClient(fixture["key"], transport=TraceTransport())
    ApixlyClient.from_environment = classmethod(lambda cls: api)
    sys.modules["folder_paths"] = types.SimpleNamespace(
        get_output_directory=lambda: str(args.output),
        get_user_directory=lambda: str(args.output / "user"),
        get_temp_directory=lambda: str(args.output / "temp"),
    )

    def artifact(path):
        data = path.read_bytes()
        return {
            "path": str(path),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    def save_image(tensor, filename):
        import numpy as np
        from PIL import Image

        path = args.output / filename
        Image.fromarray(
            np.clip(tensor[0].cpu().numpy() * 255, 0, 255).astype(np.uint8)
        ).save(path)
        with Image.open(path) as image:
            image.verify()
        return {**artifact(path), "tensor_shape": list(tensor.shape)}

    def safe_receipt(text):
        value = json.loads(text)
        return {
            key: val
            for key, val in value.items()
            if key not in {"url", "data", "last_frame_url", "effective_parameters"}
        }

    try:
        capabilities = api._json("GET", "/video/config")
        selected = next(
            (
                item
                for item in capabilities.get("data", [])
                if item.get("model") == args.video_model
            ),
            None,
        )
        if not selected or "text2video" not in selected.get("modes", []):
            raise RuntimeError(
                "Selected exact video model does not expose text2video capability."
            )
        seconds = selected.get("seconds", {})
        if not seconds.get("min", 1) <= args.video_seconds <= seconds.get("max", 0):
            raise RuntimeError(
                "Requested duration is outside the model's current capability range."
            )
        if "720p" not in selected.get("resolutions", []) or "16:9" not in selected.get(
            "aspect_ratios", ["16:9"]
        ):
            raise RuntimeError(
                "Selected video model does not expose the requested resolution/aspect ratio."
            )
        report["video_capabilities"] = selected
        save_report()

        prompt = "A single blue glass vase centered on a pale blue studio background, soft lighting, no text or logos."
        image_id, _ = ApixlyImageSubmit().submit(
            args.image_model, prompt, '{"n":1}', 1
        )["result"]
        step = {
            "operation": "image_generation",
            "model": args.image_model,
            "parameters": {"n": 1},
            "task_id": image_id,
        }
        report["steps"].append(step)
        save_report()
        print(
            json.dumps({"submitted": "image_generation", "task_id": image_id}),
            flush=True,
        )
        tensor, _, receipt = ApixlyImageResult().result(image_id, 600, 2.0)["result"]
        step.update(
            {
                "receipt": safe_receipt(receipt),
                "artifact": save_image(tensor, "generated.png"),
            }
        )
        save_report()
        print(
            json.dumps({"completed": "image_generation", "task_id": image_id}),
            flush=True,
        )

        edit_prompt = "Change only the pale blue background to warm beige; keep the same single blue glass vase and its shape. No text or logos."
        edit_id, _ = ApixlyImageSubmit().submit(
            args.edit_model, edit_prompt, '{"n":1}', 1, reference_images=tensor
        )["result"]
        step = {
            "operation": "reference_image_edit",
            "model": args.edit_model,
            "parameters": {"n": 1},
            "reference_image_count": 1,
            "task_id": edit_id,
        }
        report["steps"].append(step)
        save_report()
        print(
            json.dumps({"submitted": "reference_image_edit", "task_id": edit_id}),
            flush=True,
        )
        edited, _, receipt = ApixlyImageResult().result(edit_id, 600, 2.0)["result"]
        step.update(
            {
                "receipt": safe_receipt(receipt),
                "artifact": save_image(edited, "edited.png"),
            }
        )
        save_report()
        print(
            json.dumps({"completed": "reference_image_edit", "task_id": edit_id}),
            flush=True,
        )

        if args.skip_video:
            report["outcome"] = "images_completed_video_not_submitted"
            save_report()
            return

        params = {
            "seconds": args.video_seconds,
            "resolution": "720p",
            "aspect_ratio": "16:9",
        }
        video_id, _ = ApixlyVideoSubmit().submit(
            args.video_model,
            "A locked-off three-second studio shot of a single blue glass vase on a table, gentle moving reflections, no text or logos.",
            json.dumps(params),
            1,
        )["result"]
        step = {
            "operation": "video_generation",
            "model": args.video_model,
            "parameters": params,
            "task_id": video_id,
        }
        report["steps"].append(step)
        save_report()
        print(
            json.dumps({"submitted": "video_generation", "task_id": video_id}),
            flush=True,
        )
        video_path, _, receipt = ApixlyVideoResult().result(video_id, 900, 3.0, True)[
            "result"
        ]
        step.update(
            {"receipt": safe_receipt(receipt), "artifact": artifact(Path(video_path))}
        )
        ffprobe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,size:stream=codec_name,width,height",
                "-of",
                "json",
                video_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        step["ffprobe"] = json.loads(ffprobe.stdout)
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        report["outcome"] = "completed"
        save_report()
        print(
            json.dumps(
                {
                    "completed": "video_generation",
                    "task_id": video_id,
                    "report": str(report_path),
                }
            ),
            flush=True,
        )
    except BaseException as error:
        report["outcome"] = "failed_or_blocked"
        report["error"] = str(error).replace(fixture["key"], "[redacted]")
        save_report()
        print(
            json.dumps(
                {
                    "outcome": report["outcome"],
                    "error": report["error"],
                    "report": str(report_path),
                }
            ),
            flush=True,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
