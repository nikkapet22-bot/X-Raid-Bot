# Slot 1 Explorer-Style Image Paste Design

## Summary

Change slot-1 preset image insertion so it mimics copying an image file from Windows Explorer and pasting it with `Ctrl+V`.

This is a slot-1-only change. Text paste behavior stays unchanged. The current bitmap-based image paste path remains available for any future use, but slot 1 should stop using it.

## Goals

- Make slot-1 preset image paste behave more like the user's manual `Ctrl+C` from Explorer and `Ctrl+V` into the target field.
- Reduce or eliminate the crop dialog that appears with the current bitmap clipboard payload.
- Keep the change narrow to slot-1 preset images.

## Non-Goals

- Do not redesign all image paste behavior in the app.
- Do not switch slot 1 to a UI-driven file upload flow.
- Do not change text paste behavior.

## Current Problem

The current bot image paste path loads the file, converts it to a bitmap clipboard format (`CF_DIB`), and sends `Ctrl+V`.

That is not the same as copying an image file from Windows Explorer. Sites can treat those two clipboard payloads differently. In the current behavior, slot-1 preset image paste opens a crop dialog, while the user's manual Explorer copy/paste does not.

## Desired Behavior

For slot-1 preset images only:

1. Put the image file reference on the Windows clipboard in the same style as Explorer copy.
2. Send `Ctrl+V`.

This should more closely match:

1. selecting an image file in Explorer
2. pressing `Ctrl+C`
3. focusing the target field
4. pressing `Ctrl+V`

## Architecture

Keep both clipboard image strategies in the input layer:

- existing bitmap clipboard image paste
- new file-reference clipboard image paste

Slot 1 runtime should explicitly use the new file-reference path for preset images.

This avoids changing behavior elsewhere and keeps the slot-1 intent obvious.

## Implementation Shape

### Input Layer

Add a dedicated method such as:

- `paste_image_file(image_path: Path)`

This should place the file reference on the Windows clipboard instead of raw bitmap image data, then issue `Ctrl+V`.

The current bitmap path should stay available as-is.

### Slot 1 Runtime

In the slot-1 preset step:

- keep `paste_text(...)`
- replace the current preset image insertion call with `paste_image_file(...)`

### Platform Scope

This behavior is Windows-specific and should be implemented only in the Windows clipboard backend.

## Testing

Add regression coverage for:

- input-layer file-reference clipboard paste path
- slot-1 runner using the file-reference paste method for preset images
- existing bitmap paste tests remain valid for the old method

## Risks

- Explorer copy behavior can involve multiple clipboard formats. A minimal file-reference-only implementation may still differ slightly from Explorer in some apps.
- If the target site depends on more than a file reference payload, a later refinement may be needed.

## Success Criteria

- Slot 1 preset image insertion no longer uses the bitmap clipboard path.
- Slot 1 continues to paste text first, then image.
- Manual behavior and bot behavior become closer enough that the extra crop dialog is avoided or materially reduced.
