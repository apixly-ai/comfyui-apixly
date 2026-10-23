# Registry review notes

The Registry accepted the 0.1.2 archive and subsequently marked it
`NodeVersionStatusFlagged`. Its public scan report contains four informational
findings. Version 0.1.3 is pending at the time of this note. Publication and
download availability do not establish Registry approval.

The current report is available from the [official version API](https://api.comfy.org/nodes/comfyui-apixly/versions?include_status_reason=true).

| Reported location | Intended behavior | Data boundary |
| --- | --- | --- |
| `ApixlyClient.from_environment` in `apixly_media/client.py` | Read the server owner's `APIXLY_API_KEY` when a media node executes. | The key authenticates requests to the fixed `https://apixly.ai/v1` origin. It is absent from graph widgets, outputs and the journal. API calls do not follow redirects. |
| `_state_path` in `apixly_media/nodes.py` | Read an optional `APIXLY_STATE_DIR` override for the submission journal. | This reads configuration; it does not modify environment variables. Without an override, state belongs to ComfyUI's user directory. |
| `SubmissionJournal._connect` in `apixly_media/journal.py` | Open the local SQLite file used to prevent duplicate paid submissions. | This is a local file connection. The same line matched the scanner's database and network rules. The journal stores digests, task IDs, statuses and timestamps. |

The journal commits a claim before submission and preserves uncertain outcomes
so that rerunning a workflow does not blindly create another paid request. It
does not contain original prompts, keys, source media or reference URLs. Removing
this mechanism would remove that protection.

The free Creative Controls nodes compose prompts offline. They do not instantiate
the API client, read credentials, create journal entries or submit media tasks.
Their browser previews and server execution use the same versioned composition
contract, with all control groups disabled by default.

The source retains ordinary, readable environment and SQLite calls. These notes
explain their purpose; they do not assert that an automated finding has been
cleared. See [PRIVACY.md](../PRIVACY.md) for network, local-storage and shared-server
behavior. Questions can be directed to `support@apixly.ai`.
