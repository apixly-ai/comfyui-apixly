# Privacy and credentials

This free plugin sends prompts, supplied reference images, reference
video/audio URLs, generation parameters, and an Apixly API key to
`https://apixly.ai/v1`. Apixly forwards generation inputs to the provider needed
to fulfill the selected model. Generation requires the external Apixly service
and paid API balance. Review Apixly's current service terms and privacy policy
before sending confidential, personal, or third-party content; only provide
material you are permitted to process.

The key is read from the **ComfyUI server's** `APIXLY_API_KEY` environment variable
when a node runs. It is never offered as a node widget or output and is not stored
in the submission journal. The plugin has no analytics, advertising, telemetry,
remote executable-code loading, or background generation. Standard HTTP requests
include a plugin/version User-Agent. Importing the plugin makes no network call.

The plugin authenticates only against the fixed Apixly API origin. API calls do
not follow redirects. Signed public result URLs are fetched without an
Authorization header. The optional authenticated video-content fallback sends
the key only to `https://apixly.ai/v1/videos/{numeric_task_id}/content`; any redirect
from that path is followed without credentials. Media requests allow HTTPS only,
at most five redirects, and bounded response sizes. Literal local/private media
addresses are blocked; this is not a complete DNS-rebinding defense. Run ComfyUI
in an appropriately isolated environment when processing untrusted workflows.

Local state consists of a SQLite submission guard and downloaded output videos.
The guard stores request/account digests, task IDs/statuses, timestamps, and
accepted/unknown/rejected submission states. It does not store original prompts,
keys, images, masks, or reference URLs. ComfyUI itself may save workflows, prompts,
API receipts, signed media URLs, and image metadata according to its own settings.
Generated images use the usual ComfyUI IMAGE output; preview copies are written
to ComfyUI's temporary directory. Additional permanent image files are saved by
the downstream nodes you choose. Video downloads are saved under the configured
ComfyUI output directory when `download_video` is enabled. No cancellation or
remote deletion is performed by this package.

Signed result URLs are temporary bearer links: anyone holding one may be able to
read its media until expiry. Avoid sharing private workflow/receipt metadata.
Apixly/provider retention and media availability are separate from the local
plugin. This document does not claim zero service retention or that outputs are
permanent. Deleting the local journal does not delete remote tasks and removes
local duplicate-submission protection. Revoking your API key is managed in your
Apixly account.

Server access is the trust boundary. All users who can run custom nodes in a
shared ComfyUI process can potentially spend the server's environment key. Use
separate isolated instances and limited keys for separate users/accounts.
Contact: support@apixly.ai.
