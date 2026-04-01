# Profile Action Overrides Design

## Goal

Let each raid profile choose which of the four global bot actions it will run:

- Reply
- Like
- Repost
- Bookmark

This must be configured from the dashboard profile cards through a cog button. The action choices should reuse the existing global slot templates and only decide whether a given profile participates in each action.

## User Experience

### Profile Card

Each profile card gets a cog button on the top-right.

When the user clicks the cog:

- open a small dialog for that specific profile
- show four checkboxes:
  - `Reply []`
  - `Like []`
  - `Repost []`
  - `Bookmark []`

These map directly to the current global slots:

- slot 1 -> Reply
- slot 2 -> Like
- slot 3 -> Repost
- slot 4 -> Bookmark

### Defaults

For existing and new profiles:

- all four profile action toggles default to enabled

The dialog should start from the current stored per-profile values.

### Paused State

If a profile has all four actions unchecked:

- that profile becomes `Paused`
- its card shows `Paused` instead of `Healthy`
- its color changes to orange

This is a configuration state, not a runtime error.

If the user re-enables at least one action:

- the profile leaves `Paused`
- it returns to normal green/red status behavior

## Runtime Behavior

The app keeps one global Bot Actions template set.

Per-profile action settings only mask those global slots:

- a slot runs for a profile only if:
  - the global slot is enabled
  - and that profile has the corresponding action enabled

Profiles with all four actions disabled:

- do not run raids
- are skipped by the worker as paused profiles

No per-profile template captures or per-profile slot definitions are introduced.

## Data Model

Extend `RaidProfileConfig` with four booleans:

- `reply_enabled`
- `like_enabled`
- `repost_enabled`
- `bookmark_enabled`

Defaults:

- all `True`

Storage must remain backward compatible:

- older configs load with all four booleans set to `True`

## Implementation Shape

### `raidbot/desktop/models.py`

- extend `RaidProfileConfig` with the four action booleans
- default each one to `True`

### `raidbot/desktop/storage.py`

- persist the four booleans
- load missing values from older configs as `True`

### `raidbot/desktop/main_window.py`

- add cog button to `RaidProfileCard`
- add a small dialog for per-profile action checkboxes
- render orange `Paused` styling when all four are off

### `raidbot/desktop/controller.py`

- add an update path for per-profile action booleans
- persist the changed profile config

### `raidbot/desktop/worker.py`

- filter the global action sequence for each profile using that profile’s action mask
- skip all-off profiles as paused

## Non-Goals

- no per-profile captured templates
- no changes to the global Bot Actions page layout or captures
- no new global action system
- no slot remapping beyond the existing 1->Reply, 2->Like, 3->Repost, 4->Bookmark mapping

## Testing

Add focused coverage for:

- storage backward compatibility for old configs
- cog dialog updating a profile’s action mask
- profile card showing `Paused` and orange when all four are off
- worker filtering global slots per profile
- worker skipping all-off profiles
