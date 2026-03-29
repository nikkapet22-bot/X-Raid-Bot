# 2026-03-30 UI IDEAS Hybrid Redesign Design

## Summary

Adopt the visual direction from `UI_IDEAS` across the live desktop app without changing the working bot behavior. This is a shell-and-page redesign, not a runtime rewrite.

The redesign should make the app feel like one coherent control console:

- left sidebar navigation instead of the current tab-heavy feel
- stronger card-based dashboard
- cleaner Settings layout
- cleaner Bot Actions layout
- improved Slot 1 Presets dialog
- unified theme, spacing, borders, and status styling

All existing working desktop bot features remain functionally intact.

## Goals

- Bring the live app visually in line with the `UI_IDEAS` direction.
- Keep the current Telegram, multi-profile, and bot-action behavior unchanged.
- Preserve the current Bot Actions feature set while making the UI feel simpler and more intentional.
- Keep the redesign testable through the existing desktop test suite plus focused UI structure checks.

## Non-Goals

- Do not redesign the setup wizard in this pass.
- Do not change Telegram/session/runtime semantics.
- Do not add new bot features beyond what the redesign needs to expose current functionality cleanly.
- Do not remove current working controls unless they are already obsolete in the live app.

## Chosen Approach

Use a direct hybrid port:

- treat `UI_IDEAS` as the visual target
- merge that direction into the live UI files
- preserve all current controller wiring, signals, config meaning, and runtime behavior

This is preferred over a theme-only pass because the value in `UI_IDEAS` is not just colors. It changes the app shell, dashboard framing, profile presentation, and Bot Actions composition.

## Redesign Scope

### In Scope

- `raidbot/desktop/theme.py`
- `raidbot/desktop/main_window.py`
- `raidbot/desktop/settings_page.py`
- `raidbot/desktop/bot_actions/page.py`
- `raidbot/desktop/bot_actions/presets_dialog.py`

### Out of Scope

- setup wizard redesign
- runtime/model refactors unrelated to UI integration
- changes to automation semantics, slot behavior, or profile execution logic

## Layout Target

### App Shell

The live app should move to a sidebar-based shell:

- fixed left sidebar
- app identity block
- nav buttons for `Dashboard`, `Settings`, and `Bot Actions`
- main stacked content area on the right

The shell should visually match the `UI_IDEAS` control-console direction:

- dark navy palette
- stronger contrast between sidebar, page background, and cards
- rounded surfaces
- cleaner status accents

### Dashboard

The dashboard should become a card-first operational view:

- top status strip for bot/session state
- metrics rendered as cards
- profile health cards made prominent
- recent activity presented as a styled feed

The current operational information stays, but it should be grouped more clearly and feel less like raw forms.

### Settings

Settings should keep the same meaning and signals, but move to a cleaner section-card presentation:

- session card
- Telegram/API card
- routing card
- clearer raid-profile management row and list

### Bot Actions

Bot Actions should keep all current features while adopting the `UI_IDEAS` layout:

- shared `Page Ready` block
- four slot tiles in a grid
- clearer timing section
- clearer status section
- card/tile treatment for slots

### Slot 1 Presets Dialog

The dialog should use the `UI_IDEAS` split layout:

- preset list on the left
- editor on the right
- cleaner text/image/finish controls
- same persisted behavior as today

## Integration Rules

The redesign must preserve:

- current controller signal wiring
- current config/storage meaning
- current profile health and restart behavior
- current page-ready capture support
- current slot testing support
- current slot 1 presets behavior
- current timing controls that already exist in the live app

The redesign may change:

- widget hierarchy
- page framing
- card composition
- labels and helper copy
- styling, spacing, borders, and color treatment

The redesign must not silently revert newer features already on local `main`.

## File Strategy

### `theme.py`

Port the `UI_IDEAS` palette and structural styling:

- sidebar styling
- card styling
- profile red/green state styling
- nav button active/hover styling
- typography scale for titles, metrics, and labels

Keep any live selectors that are still needed by the current app.

### `main_window.py`

Port the shell and dashboard composition while preserving:

- tray wiring
- controller signal hookups
- page sync/update logic
- current state rendering behavior

### `settings_page.py`

Re-skin and restructure around section cards, but keep:

- existing apply signal
- existing raid-profile add/remove/reorder signals
- existing sender entry behavior

### `bot_actions/page.py`

Adopt the card/tile layout and stronger status framing while keeping:

- page-ready capture
- slot capture
- slot test
- slot presets
- enable toggles
- settle delay control

### `presets_dialog.py`

Adopt the split editor layout while keeping:

- add/remove/save
- optional preset image
- shared finish image capture
- current persisted slot-1 preset structure

## Validation

Validation should happen in three layers:

### UI Structure

- sidebar renders and page switching works
- dashboard still renders profile cards
- settings still expose session, Telegram, and routing surfaces
- Bot Actions still exposes page-ready and slot controls

### Interaction

- settings still emit the same apply/profile signals
- Bot Actions still emit capture/test/presets/timing signals
- presets dialog still returns updated slot data correctly

### Regression

- run the full desktop test suite after the redesign merge

## Success Criteria

- the live desktop app visually matches the `UI_IDEAS` direction
- current bot behavior remains unchanged
- the app feels more coherent and less overbuilt
- profile health and bot state remain immediately understandable
- no existing working desktop feature disappears during the redesign
