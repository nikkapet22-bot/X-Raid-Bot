# 2026-03-29 Multi-Profile Raid Execution Design

## Summary

Extend the desktop bot so each incoming raid link can be executed across multiple Chrome profiles in a fixed user-managed order.

The user will choose detected Chrome profiles in the app, order them, and the bot will run the same existing bot-action flow for each eligible profile:

1. open raid link in a fresh dedicated Chrome window for that profile
2. run the shared `[R][L][R][B]` bot actions
3. close the window on success
4. leave the window open on failure
5. continue to the next healthy profile

Each configured profile gets a health state shown on the dashboard:

- green: healthy and eligible
- red: failed and blocked

Red profiles are skipped on future raids until the user presses `Restart`.

## Goals

- Let one raid link execute automatically across multiple Chrome profiles.
- Keep one shared bot-action configuration for all profiles.
- Continue raiding with remaining healthy profiles even when one profile fails.
- Surface profile health clearly on the dashboard.
- Allow the user to recover failed profiles without restarting the whole bot.

## Non-Goals

- Do not create per-profile bot-action captures or per-profile presets.
- Do not replay old failed raids when a profile is restarted.
- Do not build a separate advanced profile-management product.
- Do not reintroduce the old generic automation UI.

## Runtime Flow

For each incoming Telegram raid link:

1. bot detects the raid link
2. bot loads the ordered configured raid-profile list
3. bot filters that list to profiles that are enabled and currently healthy
4. for each eligible profile in order:
   - open the link in a fresh dedicated Chrome window for that profile
   - run the existing shared bot-action flow
   - on success:
     - close that profile’s raid window
     - mark the profile green for the latest raid
   - on failure:
     - leave the window open
     - mark the profile red with the failure reason
     - block that profile from future raids
     - continue to the next healthy profile
5. raid processing completes after the last eligible profile finishes

## Profile Configuration Model

Add a persisted ordered list of configured raid profiles.

Each profile entry stores:

- Chrome profile directory or identifier
- display label
- execution order
- enabled flag
- health state
- last failure reason

The existing single “raid browser profile” concept becomes obsolete for raid execution.

## Profile Management UI

The app should detect available Chrome profiles on the machine and let the user build the raid-profile list from detected profiles.

User actions:

- add detected profile
- remove profile
- reorder profile list

All configured profiles use the same Bot Actions setup already defined in the app.

## Dashboard UI

Add a `Profiles` area to the dashboard with one rectangle per configured raid profile.

Each rectangle shows:

- profile name
- green glow when healthy
- red glow when failed/blocked

Interactions:

- clicking a red profile shows the failure reason
- red profiles show a `Restart` button

The card state reflects the most recent raid attempt for that profile, but red cards remain blocked for future raids until restarted.

## Failure Handling

If a profile fails during a raid:

- that profile’s Chrome window stays open
- its card becomes red
- the failure reason is persisted and shown in the dashboard
- the bot continues raiding with the remaining healthy profiles
- future raids skip that failed profile automatically

Examples of reasons:

- not logged into X
- target window not found
- image match not found
- runtime error

## Restart Behavior

`Restart` is a profile-health reset, not a backlog replay.

When the user presses `Restart` on a red profile:

- clear the blocked state for that profile
- perform the normal eligibility path for future raids
- if the profile is usable again, turn it green
- if the profile is still broken, keep it red and update the reason

Restart does not rerun an old failed raid immediately.

## Data Flow Changes

- desktop config persists ordered raid-profile list
- worker/autorun processes one raid across multiple profiles
- per-profile outcomes update dashboard state and storage
- dashboard emits restart requests back into controller/worker

## Testing

Add tests for:

- config/storage round-trip for raid-profile list and health state
- ordered multi-profile raid execution
- continuing after one profile fails
- skipping red profiles on later raids
- restart clearing a red profile back to eligible state
- dashboard profile-card state and failure-reason interaction

## Risks

- Multiple profile windows will increase run time per raid; this is expected because the bot now raids sequentially across profiles.
- Profile detection must stay tied to real Chrome profiles on the machine; stale or deleted profiles should fail cleanly.
- Leaving failed windows open is useful for debugging but can accumulate windows if several profiles fail; dashboard visibility and restart behavior mitigate this.
