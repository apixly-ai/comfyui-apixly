# Privacy and credentials

This plugin has two explicit credential modes. **Account mode** uses normal
browser approval at `https://apixly.ai`, then stores a revocable scoped connection
token on the ComfyUI server. Your website password, login JWT, refresh token and
underlying Apixly API Key are never sent to the plugin. The website resolves the
owned Key selected by that connection. **Manual mode** reads `APIXLY_API_KEY` from
the ComfyUI server's environment. Switching modes is explicit; an unavailable
account/Key does not silently fall back to the environment key.

Generation sends prompts, supplied references, parameters and the appropriate
credential to the fixed Apixly service: `/v1` in manual mode or
`/api/integrations/v1` in account mode. Apixly forwards generation inputs to the
provider needed for the exact selected model. Review the service's current terms
and privacy policy before sending confidential, personal or third-party material.
Paid generation requires access to that model and sufficient API balance.

The nine free utilities—Viewpoint, Lighting, Camera & Lens, Compose, Expression,
Compose V2, Grid Split, AI Enhancement Prompt and Character Sheet Plan—run locally.
They do not read account credentials, create a media client or submission journal,
send network/model requests, or queue generation. Their inputs and previews may
be saved in your ComfyUI workflow. Character selection identity is saved in its
node properties; it contains the sheet/shot identity, index and sheet selection,
not account data. Character plans output a single explicitly selected prompt,
never a prompt list that automatically starts a paid batch. Grid Split intentionally
outputs an IMAGE list when enabled; downstream nodes execute per item, so connecting
a paid node can cause multiple billed requests. Off passes the original IMAGE
batch as one output item. The enhancement utility only produces instructions
and parameters; connecting and explicitly running Image Edit is a separate paid
action that may redraw details. Opening a model
picker makes bounded catalog/account metadata reads; its options use a ten-minute
identity-scoped cache with stale refresh and a manual Refresh action. Catalog,
Key selection and connection approval do not generate media.

Account state is separate from ComfyUI's browser-readable userdata and submission
journal. It contains the scoped connection token, selected-Key/account metadata
and pending short-lived device proof in a private JSON file, normally
`~/.local/share/apixly/comfyui/connection.json` on macOS/Linux or under
`LOCALAPPDATA` on Windows. `APIXLY_CONNECTION_DIR` can choose its server-owned
directory. On POSIX, the directory is `0700` and file `0600`; the file is not an
encrypted credential vault. Other code running as that OS user can read it.
Pending proofs expire on the service after ten minutes and may remain locally
until the flow is completed, cancelled or replaced. The browser receives only
public connection metadata and an approval URL/short user code, never the private
device proof or token. Native controls use same-origin checks and a process-local
CSRF nonce, rather than trusting Comfy browser client IDs as account identities.
Connect prepares a blank tab in its click gesture, removes its opener, then
navigates to the validated public approval URL. Manual Open and Copy actions use
that same URL. No device proof is copied, placed in a workflow or sent to a new
browser tab.

No credential is a node widget or output. The plugin has no analytics, telemetry,
remote executable-code loading or background generation. Standard HTTP requests
include a plugin/version User-Agent. Importing the package makes no network call.
Public reference images are fetched without credentials for content validation
and duplicate-submission hashing; their original URLs are then passed to Apixly.
The plugin does not silently host local video-reference images on another service.

The plugin authenticates only against the fixed Apixly API origin. API and account
requests do not follow authenticated redirects. Signed public result URLs are
fetched without an Authorization header. The optional authenticated video-content fallback sends
the selected credential only to its same-origin numeric video content path
(`/v1/videos/{id}/content` or `/api/integrations/v1/videos/{id}/content`); any redirect
from that path is followed without credentials. Media requests allow HTTPS only,
at most five redirects, and bounded response sizes. Literal local/private media
addresses are blocked; this is not a complete DNS-rebinding defense. Run ComfyUI
in an appropriately isolated environment when processing untrusted workflows.

In addition to the private connection file, local state includes a SQLite
submission guard and downloaded output videos.
The guard stores request/account digests, task IDs/statuses, timestamps, and
accepted/unknown/rejected submission states. It does not store original prompts,
keys, images, masks, or reference URLs. ComfyUI itself may save workflows, prompts,
API receipts, signed media URLs, and image metadata according to its own settings.
Generated images use the usual ComfyUI IMAGE output; preview copies are written
to ComfyUI's temporary directory. Additional permanent image files are saved by
the downstream nodes you choose. Video downloads are saved under the configured
ComfyUI output directory when `download_video` is enabled. No media-task cancellation or remote media
deletion is performed by this package.
Disconnecting an account revokes only its scoped connection; it leaves the
underlying Key and other connections unchanged. Lost connections can also be
revoked from [website connection settings](https://apixly.ai/integrations).

Signed result URLs are temporary bearer links: anyone holding one may be able to
read its media until expiry. Avoid sharing private workflow/receipt metadata.
Apixly/provider retention and media availability are separate from the local
plugin. This document does not claim zero service retention or that outputs are
permanent. Deleting the local journal does not delete remote tasks and removes
local duplicate-submission protection. Revoking your API key is managed in your
Apixly account.

Server access is the trust boundary. All users who can run custom nodes in a
shared ComfyUI process can potentially spend its selected account Key or
environment key. This is one server-operator binding, not separate login sessions
for each browser user. Use separate isolated instances and limited keys for separate users/accounts.
Website: [apixly.ai](https://apixly.ai). Account/Keys: [platform.apixly.ai](https://platform.apixly.ai).
Contact: [support@apixly.ai](mailto:support@apixly.ai).
