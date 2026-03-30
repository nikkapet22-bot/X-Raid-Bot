# Top Tab Shell Redesign

Date: 2026-03-30

## Summary

Replace the current left sidebar shell with a top navigation strip styled like simplified Chrome tabs. Remove the in-app sidebar brand block entirely. Move the sidebar-only `Success Rate` and `Uptime` cards into the dashboard metric row so the app uses its horizontal space more efficiently.

This is a shell/layout redesign only. It must not change bot behavior, storage, settings semantics, tray behavior, or runtime logic.

## Goals

- Remove the left sidebar completely.
- Add a top navigation strip with three tabs:
  - `Dashboard`
  - `Settings`
  - `Bot Actions`
- Style those tabs like simplified Chrome tabs:
  - content-sized
  - active tab visually attached to the page
  - inactive tabs darker and flatter
  - rounded top corners
- Remove the in-app `L8N Raid Bot` brand block from the shell.
- Move `Success Rate` and `Uptime` into the dashboard metric card area.
- Preserve all existing page content and behavior.

## Non-Goals

- No runtime or automation changes.
- No storage/config changes.
- No tray/title-bar branding changes.
- No redesign of the setup wizard in this pass.

## Shell Layout

The new shell should be:

1. native window title bar
2. top tab strip
3. current page content

The top strip replaces the sidebar entirely. There should be no leftover sidebar gutter or blank placeholder column.

## Navigation

Navigation is still page-based over the existing `QStackedWidget`, but the source of page selection changes:

- old: `SidebarNav.pageRequested`
- new: top tab strip selection

The tab strip should:

- switch the stacked widget page
- visually reflect the active page
- preserve the current page on app state refreshes

## Dashboard Changes

The dashboard keeps its existing sections:

- page title
- `Start` / `Stop`
- `System Status`
- `Profiles`
- metric cards
- `Recent Activity`
- `Last Error`

The metric row expands to six cards:

- `AVG RAID COMPLETION TIME`
- `AVG RAIDS PER HOUR`
- `Raids Completed`
- `Raids Failed`
- `Success Rate`
- `Uptime`

These two cards are removed from the old sidebar footer and become normal dashboard metric cards.

## Settings And Bot Actions

`Settings` and `Bot Actions` keep their current content. Only the shell around them changes:

- top tab strip above
- page content below
- no sidebar

## Visual Rules

- Top tabs should resemble simplified browser tabs, not pill buttons.
- The active tab should feel attached to the content surface.
- Inactive tabs should recede slightly.
- Horizontal space recovered from the removed sidebar should be given back to page content, not replaced with extra gutter.

## Testing

Add or update tests for:

- no sidebar shell widget in the main window layout
- top tabs switch the stacked pages correctly
- dashboard metric row now includes `Success Rate` and `Uptime`
- existing dashboard/settings/bot-actions pages still mount correctly
- shell change does not remove or rename the existing page content unexpectedly

## Risks

- The current code couples shell and sidebar metric labels, so moving `Success Rate` and `Uptime` requires careful relinking without changing the underlying metric calculations.
- Existing tests reference the sidebar directly and will need to be rewritten to validate the new tab shell instead.

## Acceptance Criteria

- The left sidebar is gone.
- Top tabs exist and behave as navigation.
- The app no longer shows the in-app brand block.
- `Success Rate` and `Uptime` appear as dashboard metric cards.
- All existing runtime behavior remains unchanged.
