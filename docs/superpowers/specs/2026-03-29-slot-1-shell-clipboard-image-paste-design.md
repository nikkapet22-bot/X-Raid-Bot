# Slot 1 Shell Clipboard Image Paste Design

## Summary

Refine slot-1 preset image paste again so it mimics Explorer copy/paste more closely than the current `CF_HDROP`-only implementation.

The current slot-1 image path already switched away from bitmap clipboard data, but the payload is still too thin. Manual Explorer copy produces a richer shell/OLE clipboard payload, and that appears to be the behavior the target UI accepts without opening the crop flow.

## Goals

- Make slot-1 preset image paste behave more like a real Explorer file copy.
- Keep the change limited to slot-1 preset image insertion.
- Avoid falling back to the old bitmap path that triggers the crop flow.

## Non-Goals

- Do not redesign image handling across the whole app.
- Do not change slot-1 text paste.
- Do not implement a site-specific upload-button flow.

## Current Problem

The current bot now pastes slot-1 preset images via a file-reference clipboard path, but inspection showed:

- manual Explorer copy exposes a rich shell/OLE clipboard object with formats such as `DataObject`, `Shell IDList Array`, `Preferred DropEffect`, `CF_HDROP`, `FileNameW`, `FileContents`, and `FileGroupDescriptorW`
- the bot currently exposes only `CF_HDROP`

So the bot still does not match the working manual copy path closely enough.

## Desired Behavior

For slot-1 preset images only:

1. Build a richer Windows shell clipboard payload that more closely matches Explorer file copy behavior.
2. Send `Ctrl+V`.

Text paste remains unchanged and still happens first.

## Architecture

Keep the current public slot-1 runtime shape:

- `paste_text(...)`
- `paste_image_file(...)`

But change the implementation of `paste_image_file(...)` on Windows:

- replace the current `CF_HDROP`-only payload
- use Windows shell/COM support to place a richer file-copy clipboard object on the clipboard

This keeps the runner code stable while swapping only the low-level clipboard behavior.

## Implementation Shape

### Input Layer

In the Windows clipboard backend:

- keep `set_image(...)` for the old bitmap path
- replace or extend `set_file_image(...)` so it uses Windows shell/COM APIs to emulate Explorer file copy more closely than raw `CF_HDROP`

The code should use the Windows modules already available in this repo environment:

- `pythoncom`
- `win32com.shell`
- `win32clipboard`

### Runtime Scope

No change to slot-1 runner ordering:

1. click slot-1 main image
2. paste text
3. paste preset image via `paste_image_file(...)`
4. continue finish-image chain

## Failure Behavior

- If the shell clipboard setup fails, surface a clear error in the slot-1 path
- Do not silently fall back to bitmap clipboard paste

That keeps failures visible instead of reintroducing the known bad behavior.

## Testing

Add regression coverage for:

- input-layer shell clipboard path being used by `paste_image_file(...)`
- slot-1 runner still using `paste_image_file(...)`
- existing bitmap path remaining untouched

Manual smoke check is required after implementation:

1. configure slot-1 preset image
2. run slot-1 test
3. compare behavior against manual Explorer copy/paste
4. verify whether the crop dialog is gone

## Risks

- Explorer copy behavior is implemented through Windows shell/OLE internals, so this is more platform-specific than the previous clipboard change.
- Matching Explorer perfectly may still require iteration if the target UI is sensitive to additional clipboard formats.

## Success Criteria

- Slot-1 preset image paste uses the richer shell clipboard path, not bitmap paste and not bare `CF_HDROP` only.
- Slot 1 continues to paste text first, then image.
- The target UI behaves closer to the user's manual Explorer copy/paste path.
