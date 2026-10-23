# Visual assets

The Apixly icon is the existing official brand mark. The native SVG covers and
workflow diagrams use the official electric-blue, near-black and cyan/blue/indigo
palette. Diagrams are explanatory illustrations, not screenshots of plugin UI.
The compact SVG variants are selected on narrow screens by the README picture tags.

The refreshed cover labels describe fifteen nodes and twelve templates. Nine
creative/image utilities are free; paid Creative → media and enhancement branches
start muted in their respective starters.
The cover diagrams are illustrations, not an account/sidebar UI capture.

The screenshots are unmodified captures from the official ComfyUI host used for
live acceptance on October 23, 2026. Account screenshots show the earlier plugin Settings link
area; they do not depict the new account connection sidebar. the video canvas shows an actual completed result. The reference-to-video
canvas capture shows the configured workflow, rather than a fabricated completion
state. Private keys, signed result URLs and supplier information are not shown.

The example media are unretouched saved API results:

- `reference-vase.png`: the source reference image.
- `edited-vase.png`: the real `gemini-3.1-flash-image` edit of that reference.
- `video-frame.png`: the first decoded frame from the saved reference video.
- `reference-video.mp4`: the actual `grok-imagine-video-1.5-preview` output,
  3.041667 seconds, 960 × 960. The request used source framing, with no explicit
  resolution or aspect ratio. This is a bounded example, not a promise of model
  quality or universal model support.

No new media generation was performed for the earlier repository presentation update.

`social-preview.png` is a 1440 × 720 raster export of `social-preview.svg`, ready
for a repository social preview. It is illustrated artwork, not a screenshot.


## Version 0.3.0 additions

The four new screenshot PNGs are unmodified captures from the official ComfyUI
host with frontend 1.57.1. They show only offline Apixly tools and stock previews,
with the account sidebar hidden and no task IDs, keys, authorization links or
private paths. Stock preview node sizes were adjusted for presentation at 1:1
canvas scale. Grid Split outputs four separate tiles; PreviewImage displays them
as a continuous mosaic. The character planner is shown beside a separately loaded
saved result, without a paid node in the screenshot.

- `screenshots/expression-compose-v2.png`: expression grid and V2 prompt composition.
- `screenshots/image-grid-split.png`: offline 2×2 tile splitting and preview.
- `screenshots/enhancement-prompt.png`: exact model/parameter outputs from the helper.
- `screenshots/character-sheet-plan.png`: one explicitly selected character plan.

Three live actions were authorized individually for 0.3.0 media acceptance:

- `examples/character-neutral.jpg`: original Grok result, 768×1152.
- `examples/character-smile.png`: original Gemini reference edit, 848×1264.
- `examples/character-enhanced.jpg`: original Gemini redraw enhancement, 843×1264.

These three files retain the original API bytes and provider metadata, including
XMP/IPTC where supplied. They are not Comfy SavePNG exports. No retouching or
metadata stripping was applied. Both edits used the neutral image as reference.
The full-body instruction did not include the feet in the output. The examples
show bounded model behavior, not guaranteed framing, identity preservation or
pixel-preserving super-resolution. Their source SHA-256 values were checked
before copying to this directory.
