# Apixly Media for ComfyUI

Generate images, edit reference images, and create videos through the
[Apixly](https://apixly.ai/) media API. Submit once, keep the task ID, and retrieve
results in a separate node. Use API images in local ComfyUI workflows and pass
video result URLs or downloaded files to later steps.

The plugin is free and MIT licensed. **Generation requires an Apixly account,
an API key with access to the chosen model, and sufficient API balance.** Apixly
API charges are separate from Comfy credits and any Comfy subscription. This
custom-node package is maintained by Apixly and is not a Comfy Partner Node.

Create a limited key in the [API key console](https://platform.apixly.ai/keys),
check [model availability and prices](https://platform.apixly.ai/models), and
review actual charges in [usage details](https://platform.apixly.ai/usage/logs).
The [website](https://apixly.ai), [console](https://platform.apixly.ai), and
[API documentation](https://apixly.ai/docs) are also available from ComfyUI
Settings → Apixly → Media. Account and service links stay in that settings area.

## Install

1. Clone this repository into `ComfyUI/custom_nodes/comfyui-apixly`.
2. In ComfyUI's Python environment, run `python -m pip install -r custom_nodes/comfyui-apixly/requirements.txt`.
3. Set `APIXLY_API_KEY` in the environment used to launch the **ComfyUI server**.
   Use a separate key with a small spending limit for this plugin.
4. Restart ComfyUI, then search for **Apixly** in Add Node.

```sh
git clone https://github.com/apixly-ai/comfyui-apixly.git ComfyUI/custom_nodes/comfyui-apixly
```

For example, with your existing ComfyUI environment activated on macOS/Linux:

```sh
read -s APIXLY_API_KEY
export APIXLY_API_KEY
python main.py
```

Windows PowerShell can read the value without placing it in command history:

```powershell
$secret = Read-Host "Apixly API key" -AsSecureString
$env:APIXLY_API_KEY = [System.Net.NetworkCredential]::new("", $secret).Password
python main.py
```

Set the variable in the actual desktop/service launcher when using ComfyUI
Desktop or a managed server. A variable set only in another terminal will not
reach an already-running server. Never paste the key into a prompt, node
parameter, workflow JSON, screenshot, or public issue.

No runtime package installation is performed. The HTTP client uses the small
`httpx` dependency. Image nodes use ComfyUI's existing PyTorch, NumPy, and Pillow.
Python 3.10 or later is required. No local GPU is required for API generation.

## Nodes

| Node | Behavior | Outputs |
| --- | --- | --- |
| Apixly Image: Submit | Starts one asynchronous text-to-image job | `task_id`, `submission_json` |
| Apixly Image: Edit | Requires reference images and explicitly suggests the qualified Gemini editing model | `task_id`, `submission_json` |
| Apixly Image: Result | Waits for an existing image task and decodes every result | `IMAGE`, result URL JSON, receipt JSON |
| Apixly Video: Submit | Starts a video task, with public reference URLs when the model supports them | `task_id`, `submission_json` |
| Apixly Task: Status | Performs one status GET for an existing task | status, result URL, receipt JSON |
| Apixly Video: Result | Waits for an existing video task and optionally downloads it | local video path, result URL, receipt JSON |

Drag a JSON file from [`example_workflows/`](example_workflows/) onto the canvas.
Set an exact model ID that your Apixly API key can use. Image generation suggests
`grok-imagine-image`; reference editing explicitly suggests
`gemini-3.1-flash-image`. The latter preserved the source vase and changed the
background in the initial live smoke test; this is a bounded sample, not a quality
guarantee. Grok reference editing is not qualified by that result. Video suggests
`grok-imagine-video`. Available models and permissions depend on your API key group.
Check your Apixly model catalog; `GET https://apixly.ai/v1/models` lists model IDs
and `GET https://apixly.ai/v1/video/config` exposes current video capabilities.
The plugin does not rename a model, select a fallback, or change requested fields.

### Image generation and editing

Connect Image Submit → Image Result → Preview Image or Save Image. Typical
`parameters_json` for a model supporting these options is:

```json
{"size":"1024x1024","quality":"high","n":1}
```

Use **Apixly Image: Edit** and connect Load Image to `reference_images` to edit an existing image. An IMAGE batch
is sent as separate PNG reference files. The selected model must support the
operation and fields. References are never silently discarded or duplicated.
Mixed-size result batches are reported instead of being resized without permission.

**Masked inpainting is unavailable in this release.** The public nodes do not
expose a MASK input and reject explicit masks before a paid request. Low-level
REST transport tests remain for future qualification. Ordinary reference-image
editing and multiple references are separate, supported workflows.

### Video generation

Connect Video Submit → Video Result. Model-specific options are flat JSON, for
example, only when the selected model supports them:

```json
{"seconds":5,"resolution":"720p","aspect_ratio":"16:9"}
```

Use `reference_image_urls` for public HTTPS reference images. It accepts Image:
Result's `result_urls_json` output, a JSON array of URLs, or one URL per line.
The `reference-image-to-video` template visibly connects Load Image → Gemini Edit
→ Image Result URLs → Grok image-to-video → Video Result. It contains two paid
actions, and does not silently upload a local file to a third-party host.

A free live
capability check rejects references for known text-only models before submission.
Choose an explicit image-to-video model, such as `grok-imagine-video-1.5-preview`,
for references; the plugin never drops references or switches models. Unknown
models remain subject to the gateway's validation. That Grok route currently
requires public URLs: local IMAGE/data-URL input is rejected before submission
with instructions for the visible image-result URL workflow. Other routes may
support local IMAGE tensors as inline PNGs, but this release does not claim
compatibility with every route. Choose one reference source, not both.

For `grok-imagine-video-1.5-preview` reference video, choose **model_default** for
both resolution and aspect ratio. This explicitly omits those API fields and
uses source framing. Explicit geometry for that route is not qualified and is
rejected before a paid request, including geometry in advanced JSON. Inspect
the decoded result for its actual dimensions; a square source can produce a
square video. The qualified text-video preset remains 3 seconds, 720p, 16:9.

Reference URLs are read once through bounded HTTPS GETs without an API key to
verify the image and hash its content. The original URLs are sent unchanged to
Apixly. Refreshing a signed URL for the same bytes therefore reuses the same
nonce/action; a source-download failure never starts a paid video. Do not put
private account credentials in these URLs. Reference limits, task modes, output
duration, resolution, and billing are model dependent; inspect current video
capabilities before choosing them. This initial version supports `/v1/videos`
generation, not the separate `/v1/videos/edits` video-edit endpoint.

Duration, resolution, and aspect ratio have dedicated video controls; conflicting
values in advanced JSON are rejected before submission. The default is a 3-second
720p, 16:9 generation. Verify prices before running it.

The result node downloads a recognizable MP4/MOV/WebM body into
`ComfyUI/output/apixly/` by default. Its `video_path` is a file path string, **not**
a ComfyUI `VIDEO` object; use a video-loader node that accepts a path if a later
workflow requires a native video object. The returned `result_url` is suitable
for URL-based workflow steps and is temporary. Save completed media promptly.
The current client download limit is 256 MiB per video and 32 MiB per image.

Results show native image/video previews. The node's result panel can copy the
task ID or temporary result URL and download a saved file. Image previews use
ComfyUI's temporary directory. Video progress uses the server-reported percentage
when available; a running image task does not invent a completion estimate.

## Paid actions, new runs, and recovery

`request_nonce` identifies an explicit generation action. **A new nonce allows a
new paid job even with the same model and prompt.** ComfyUI's after-generation
control can increment or randomize it for a new queue run. Select `fixed` while
diagnosing a submission. Changing the request contents also starts a new action.

A private local SQLite journal binds a key/account digest, request digest, and
nonce to the accepted task ID. Re-executing the same action returns that ID.
Public reference-image identity uses its content hash rather than the temporary
URL signature, so URL refreshes do not create another paid generation.
Only digests, task IDs/statuses, timestamps, and submission states are stored;
keys, prompts, reference bytes, and raw API responses are not stored there.
Its default location is `ComfyUI/user/apixly/submissions.sqlite3` (the actual
ComfyUI user-directory setting is respected). `APIXLY_STATE_DIR` may select a
different server-owned directory. It must be writable by the ComfyUI user.

The client never automatically retries a paid POST. If a submission times out,
loses its response, or receives an ambiguous server error, the nonce is guarded
as **unknown**. Check your existing Apixly tasks/account activity before selecting
a new nonce. A journal is a local recovery guard, not a gateway idempotency key:
deleting it, moving machines, changing the key, or selecting another nonce does
not cancel an accepted task and can create another charge.

For normal waiting, recover by copying the known task ID into **Image Result**,
**Video Result**, or **Task Status**. These nodes only make reads. Temporary
status errors are retried within the configured deadline. Waiting timeout,
failed download, or expired URL never triggers a new generation. Refresh an
existing task to obtain a fresh signed URL while its media remains available.
If the media itself has expired, report that state instead of generating again.
An image Result node can fail after Submit succeeded: **do not increment the
submit nonce just to retry downloading**.
Interrupted media downloads get at most three safe GET attempts; partial bodies
are discarded and are never delivered as completed files.

Use trusted workflows and protect access to the ComfyUI server. Environment
credentials apply to that server process: another person who can execute its
nodes may spend the same key's balance. The plugin has no key widget or secret
output, but prompts and returned signed result URLs can still appear in normal
ComfyUI workflow/output metadata. See [PRIVACY.md](PRIVACY.md).

## Development and release checks

```sh
python -m pytest -q
node --test tests/frontend.test.mjs
python -m compileall -q apixly_media
python -m pip wheel --no-build-isolation --no-deps . --wheel-dir /absolute/path/to/artifacts
```

Tests run offline with a fake HTTP transport, temporary journals, and real image
tensor conversion. Live model qualification and billing checks are separate and
must use a limited test key. Before publishing, verify PublisherId `apixly` is
owned by the publishing account, the public repository/icon/support URLs work,
and image generation/editing plus video terminal output have been verified
against the exact models advertised in release notes. Do not advertise untested
models or claim a completed live generation from offline tests.

Publishing follows the [Comfy Registry guide](https://docs.comfy.org/registry/publishing).
Run `comfy node publish` from the standalone release checkout using its Registry
publishing key, not an Apixly inference key. Registry packages must contain the
root `__init__.py`, `apixly_media/`, license, docs, assets, and example workflows.
The wheel is for client packaging validation; ComfyUI loads the Registry/repository
custom-node package. All versions must meet the [Registry quality and security
standards](https://docs.comfy.org/registry/standards).

Support: [support@apixly.ai](mailto:support@apixly.ai).
When reporting a problem, include plugin version, exact model, task/request ID,
status, and sanitized error text. Never send your API key or private media in a
public issue.
