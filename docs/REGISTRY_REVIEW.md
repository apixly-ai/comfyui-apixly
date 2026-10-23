# Registry review notes

The official Registry readback on October 23, 2026 marks both 0.1.2 and 0.1.3
`NodeVersionStatusFlagged`. Each report contains four `info` findings: two
environment-access matches and a local SQLite connection matched by both the
database and network rules. Publication and download availability do not
establish Registry approval. These historical reports do not establish that the
newer 0.2 account functionality has passed scanning or review.

The current report is available from the [official version API](https://api.comfy.org/nodes/comfyui-apixly/versions?include_status_reason=true).

| Reported 0.1.x location | Intended behavior | Data boundary |
| --- | --- | --- |
| `ApixlyClient.from_environment` in `apixly_media/client.py` | Read the server owner's `APIXLY_API_KEY` when a media node executes. | The key authenticates requests to the fixed `https://apixly.ai/v1` origin. It is absent from graph widgets, outputs and the journal. API calls do not follow redirects. |
| `_state_path` in `apixly_media/nodes.py` | Read an optional `APIXLY_STATE_DIR` override for the submission journal. | This reads configuration; it does not modify environment variables. Without an override, state belongs to ComfyUI's user directory. |
| `SubmissionJournal._connect` in `apixly_media/journal.py` | Open the local SQLite file used to prevent duplicate paid submissions. | This is a local file connection. The same line matched the scanner's database and network rules. The journal stores digests, task IDs, statuses and timestamps. |

The journal commits a claim before submission and preserves uncertain outcomes
so that rerunning a workflow does not blindly create another paid request. It
does not contain original prompts, keys, source media or reference URLs. Removing
this mechanism would remove that protection.

## Account mode in 0.2

Account connection uses the fixed `https://apixly.ai/api/integrations` service for
device authorization, connection metadata, owned-Key selection and revocation.
Account-mode media and catalog requests use its `/v1` relay. The normal website
handles login and approval; the plugin receives a scoped connection token,
not a website password, login JWT, refresh token or underlying API Key. Account
and API requests do not follow authenticated redirects. Signed media downloads
have their separate, credential-free boundary described in [PRIVACY.md](../PRIVACY.md).

`apixly_media/account.py` deliberately reads/writes a private connection file.
On POSIX its directory is `0700` and file `0600`, outside browser-readable
ComfyUI userdata. It contains the scoped token, account/selected-Key metadata and
pending device proofs. It is not an encrypted vault: code running as the same OS
user can read it. `APIXLY_CONNECTION_DIR` and the platform data-directory setting
select its location; these environment reads remain visible in the source.
Disconnect calls the service to revoke that connection before clearing its local
binding. A failed revoke is reported rather than presented as successful removal.
Owners can also revoke lost connections from [website settings](https://apixly.ai/integrations).
Revocation does not delete the underlying API Key or unrelated connections.

Manual `APIXLY_API_KEY` mode remains optional and server-owned. Mode switching is
explicit; an unavailable account or selected Key does not silently fall back to
that environment key. Both credential modes apply to the server operator, not
separate identities inferred from Comfy browser client IDs. The browser receives
metadata and a panel CSRF nonce, never the private token or device proof.
`server.py` exposes the local account controls with origin/CSRF checks;
`catalog_service.py` performs bounded catalog reads with a ten-minute,
identity-scoped cache. These are ordinary disclosed network and storage calls;
catalog browsing and Key selection do not perform inference.

## Offline controls

The free Creative Controls nodes compose prompts offline. They do not instantiate
the API client, read credentials, create journal entries or submit media tasks.
Their browser previews and server execution use the same versioned composition
contract, with all control groups disabled by default.

The source retains ordinary, readable environment and SQLite calls. These notes
explain their purpose; they do not assert that an automated finding has been
cleared. See [PRIVACY.md](../PRIVACY.md) for network, local-storage and shared-server
behavior. Questions can be directed to `support@apixly.ai`.
