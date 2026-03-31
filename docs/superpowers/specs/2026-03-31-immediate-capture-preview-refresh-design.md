# Immediate Capture Preview Refresh Design

## Goal

Make capture previews update immediately after the user captures a new image, even when the file path stays the same, and expose slot 1's finish-image preview directly on the slot 1 card.

## Current Problem

Bot Actions captures reuse stable filenames such as `slot_1_r.png` and `page_ready.png`. The UI currently reloads previews through Qt pixmap loading by file path. In practice, Qt reuses the cached pixmap for the same path, so overwriting the capture file does not reliably refresh the preview immediately.

This affects:

- slot capture previews
- page-ready preview
- slot 1 finish-image preview indirectly, because it is only visible in the presets dialog and not mirrored on the slot 1 card

## Decision

Fix the problem at the preview-loading layer instead of changing file naming.

- Keep stable capture filenames
- Stop relying on path-based pixmap caching for preview refresh
- Load preview images fresh from disk every time the preview is updated
- Apply the same fix to all capture surfaces
- Add a second preview tile on the slot 1 card for `finish_template_path`

## Scope

In scope:

- immediate preview refresh for:
  - page-ready captures
  - slot 1/2/3/4 captures
  - slot 1 finish-image captures
- slot 1 card UI updated to show both:
  - main capture preview
  - finish-image preview
- focused tests proving overwrite-on-same-path refresh works

Out of scope:

- changing capture file names
- adding timestamps or versioned filenames
- changing capture storage locations
- changing automation runtime behavior

## UI Shape

Slot 1 gets two previews in the existing preview area:

- the normal slot capture preview
- a finish-image preview beside it

If the finish image is missing, the second preview shows a neutral empty state such as `No finish image`.

Other cards keep their existing single-preview layout.

## Implementation Notes

- Update `raidbot/desktop/bot_actions/page.py` so preview rendering loads the latest image bytes from disk instead of using the cached `QPixmap(path)` path directly
- Keep the existing `MainWindow` capture handlers and config sync flow
- Extend slot 1 preview rendering to read `finish_template_path` and update that second preview tile during normal config sync

The root cause is a rendering/cache issue, so the fix should stay in the preview layer rather than adding new storage or controller complexity.

## Testing

Add focused coverage for:

- overwriting a slot capture at the same path refreshes the visible preview immediately
- overwriting the page-ready capture at the same path refreshes immediately
- capturing slot 1 finish image updates the slot 1 card preview immediately
- slot 1 finish preview shows a neutral empty state when no finish image exists
