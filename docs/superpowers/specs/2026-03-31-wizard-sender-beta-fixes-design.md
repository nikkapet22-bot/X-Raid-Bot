# Wizard And Sender Beta Fixes Design

## Goal

Fix the first beta tester issues around setup UX and sender handling:

1. Remove the misleading generic password wording in the wizard.
2. Add an explicit `Get Code` action before the user enters the Telegram code.
3. Keep selected sender usernames/labels visible in Settings instead of replacing them with IDs.
4. Fix the `TelegramSetupService object has no attribute 'resolve_sender_entry'` save error.

## Current Problems

### Wizard

- The Telegram access page currently shows `Code` and `Password` fields with little guidance.
- There is no explicit `Get Code` action, so users do not understand that they must first submit their Telegram details to receive a code.
- The password field is mislabeled for accounts that do not use 2FA.

### Settings / Allowed Senders

- Users choose sender labels/usernames during setup, but later see IDs in Settings.
- Saving from Settings can fail because the controller expects `TelegramSetupService.resolve_sender_entry(...)`, but the service does not implement that method.

## Decision

Keep the existing setup wizard structure, but make the Telegram access step explicit and safer:

- `API ID`, `API Hash`, `Phone`
- `Telegram Code`
- `2FA Password (optional)`
- `Get Code` button beside the code field

The user flow becomes:

1. Enter Telegram credentials and phone.
2. Press `Get Code`.
3. Receive the Telegram code in Telegram.
4. Enter the code.
5. Enter 2FA password only if needed.
6. Proceed with setup.

Keep sender entries human-readable in Settings by persisting and rendering `allowed_sender_entries` directly while still resolving them to numeric IDs for runtime filtering.

## Scope

In scope:

- Wizard Telegram access wording and flow
- Explicit `Get Code` button
- Optional 2FA guidance
- Sender label persistence/display in Settings
- Sender resolution service bug fix

Out of scope:

- Full multi-page wizard redesign
- Changing runtime sender filtering away from numeric IDs
- Reworking chat discovery or profile setup

## Implementation Notes

- Add `TelegramSetupService.resolve_sender_entry(entry: str) -> int`
- Add a service method or split flow for sending the Telegram code before final sign-in
- Wizard page should track whether `Get Code` succeeded before allowing final sign-in
- Settings should prefer `allowed_sender_entries` for display, not regenerate from IDs when entries are already available

## Testing

Add focused coverage for:

- wizard shows `Telegram Code`
- wizard shows `2FA Password (optional)` guidance
- `Get Code` sends the code request before final sign-in
- saving Settings with sender usernames resolves and persists without crashing
- Settings renders sender entries as usernames/labels instead of numeric IDs when entries exist
