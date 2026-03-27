# Raid Bot Premium Dark UI Design

## Goal

Redesign the existing PySide6 desktop app so it looks like a premium dark Windows application instead of a mostly unstyled Qt prototype. The redesign should fix the visual mismatch visible in `Screenshot_5572.png`, give the app a coherent branded identity, and keep all existing bot behavior intact.

## Problem Summary

The current desktop UI works functionally, but the visual layer is underdesigned:

- the wizard mixes a dark native frame with a bright default-white content area
- the welcome page is too sparse and looks unfinished
- buttons, fields, tabs, and lists still look like mostly default Qt widgets
- spacing and hierarchy are weak, especially in setup
- the dashboard and settings pages are practical but not visually cohesive

This makes the app feel broken or incomplete even when the underlying runtime is working correctly.

## Scope

### In scope

- Global desktop theme for the app
- Premium dark visual system
- Electric-blue accent color system
- Wizard layout and content redesign
- Dashboard layout redesign
- Settings page visual redesign
- Shared reusable card/section styling
- Better hierarchy for status, activity, and error surfaces
- Focused UI tests for theme and structural behavior

### Out of scope

- Changing bot runtime behavior
- Replacing the native Windows title bar
- Adding new bot features
- Pixel-perfect screenshot snapshot testing
- Installer or packaging work

## Recommended Approach

Apply a coherent app-wide dark theme and strengthen page composition without changing the native Windows window frame.

This is the best fit because:

- it fixes the actual issue shown in the screenshot: no coherent visual system
- it delivers a premium look without fragile custom window-chrome work
- it preserves tray, minimize, and close behavior
- it keeps the change mostly in the presentation layer

## Visual Direction

The app should feel like a premium desktop operations tool:

- dark charcoal base instead of pure black
- layered surface cards for content grouping
- restrained electric-blue accent for primary actions and active states
- high-contrast off-white primary text
- muted gray-blue secondary text
- subtle borders and depth cues instead of loud effects

The target mood is polished and intentional, not gaming-themed and not generic enterprise gray.

## Theme System

Create one shared theme module for the desktop UI. It should define reusable tokens for:

- window background
- surface and elevated surface colors
- border color
- primary text and muted text
- electric-blue accent and hover/pressed variants
- success, warning, and error accent colors
- corner radius
- content spacing
- control heights

The theme should be applied globally from the desktop app entrypoint so the wizard, main window, settings page, lists, tabs, and buttons all inherit the same visual language.

## Wizard Redesign

The setup wizard should feel like premium onboarding software rather than a plain form stack.

### Structure

- keep the existing multi-step flow
- wrap each page in a stronger content composition
- add a slim branded header region inside the wizard body
- create clearer titles, descriptions, and helper text per page
- keep the bottom navigation, but style it intentionally

### Welcome page

The current welcome page should be replaced with a structured intro that includes:

- a strong headline
- short setup description
- a concise list of what the wizard will configure
- a brief note that Chrome should already be logged into X

This step should immediately communicate that the app is working and guide the user into setup.

### Form pages

Telegram authorization, chat discovery, Raidar selection, Chrome profile selection, and review should all use:

- section labels
- helper text under important fields
- clearer loading, empty, and error states
- more deliberate vertical spacing

### Navigation controls

The wizard buttons should visually communicate role:

- primary `Next` and `Finish`
- secondary `Back`
- quiet `Cancel`

Disabled buttons should remain legible and intentional instead of looking washed out or broken.

## Main Window Redesign

The main app shell should feel like a control panel with clear structure.

### Dashboard

The dashboard should be reorganized into:

- a top status section for bot state and Telegram connection state
- metric cards for raids opened, duplicates, non-matching skips, and open failures
- a dedicated recent activity panel
- a dedicated last-error panel

The content should read as a premium monitoring surface rather than a stack of plain labels and one generic list.

### Settings

The settings page should keep the current capabilities but present them in grouped sections:

- Telegram/session
- whitelist and Raidar configuration
- Chrome profile selection
- apply and reauthorize actions

The layout should feel like account/system configuration, not a raw dev form.

## Shared Presentation Patterns

Use a few consistent patterns across the app:

- card containers for grouped information
- stronger section headings with muted supporting text
- consistent input, button, tab, and list styling
- clear empty-state and error-state surfaces
- consistent spacing between controls and sections

These patterns should be reusable so future desktop features inherit the same design language.

## Runtime And Behavior Boundaries

This redesign should not change the app's runtime model:

- the bot still runs behind the existing desktop controller/worker structure
- tray, minimize, and close behavior remain functionally the same
- Telegram authorization, chat discovery, Raidar selection, and Chrome detection logic stay in their current service/controller boundaries

This is a visual and composition pass, not a behavior rewrite.

## Testing Strategy

Keep existing functional coverage and add focused UI structure checks:

- theme is applied from desktop startup
- wizard welcome page renders the new structured intro content
- dashboard contains distinct status, metric, activity, and error sections
- settings page still emits apply and reauthorize signals after the layout refactor

Testing should validate structural behavior and integration boundaries, not pixel-perfect rendering.

## Implementation Constraints

- preserve the native Windows title bar
- prefer a shared theme module over one-off inline styles
- keep presentation logic separate from runtime and controller code
- avoid large UI rewrites that would destabilize working bot behavior

## Expected Outcome

After the redesign:

- the screenshot issue should be resolved
- first-run setup should look intentional and trustworthy
- the app should feel visually coherent from wizard through daily use
- the desktop client should read as a premium dark app with a clear electric-blue brand accent
