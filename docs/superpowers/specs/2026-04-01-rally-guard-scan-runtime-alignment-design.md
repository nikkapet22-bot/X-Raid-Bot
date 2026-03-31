# Rally Guard Scan And Runtime Alignment Design

## Goal

Make Rally Guard raid posts open reliably by fixing two app-side mismatches:

- scanned sender candidates must save the same numeric sender ID that runtime will later compare against
- raid parsing must accept X/Twitter status links even when the post omits the `http://` or `https://` scheme

The user-facing experience stays simple:

- user scans and picks a raid bot
- UI shows a readable label like `@RallyGuard_Raid_Bot`
- runtime matches the correct numeric sender ID in the background

## Confirmed Root Causes

### Sender Identity Mismatch

The app currently uses two different Telegram identities for the same sender:

- runtime listener uses `event.sender_id`
- settings scan currently derives candidates from the resolved sender entity returned by `message.get_sender()`

These are not guaranteed to be the same for channel-style posts. That can cause scan to save one ID while runtime later receives another.

### Scheme-Less Link Rejection

The raid parser currently only accepts status URLs that explicitly include `http://` or `https://`.

Valid raid posts such as:

- `x.com/i/status/...`
- `twitter.com/.../status/...`

are rejected as `missing_status_url` even though they are semantically valid.

## Design

### Sender Scan

When inferring recent sender candidates from Telegram chats:

- use `message.sender_id` as the canonical runtime-matching sender ID
- still resolve the sender entity for display purposes
- save:
  - numeric runtime sender ID in `allowed_sender_ids`
  - readable label such as `@username` in `allowed_sender_entries`

If multiple messages from the same runtime sender ID are seen:

- dedupe by runtime sender ID
- keep the best readable label found for display

This hides Telegram identity differences from the user while keeping runtime matching correct.

### Parser

Accept X/Twitter status links with or without scheme:

- `https://x.com/.../status/...`
- `http://x.com/.../status/...`
- `x.com/.../status/...`
- same for `twitter.com`

Normalize all accepted matches to the canonical stored URL:

- `https://x.com/<path>/status/<id>`

All existing raid marker requirements remain unchanged:

- action markers still required
- video still required
- dedupe still uses normalized URL

## Implementation Shape

### `raidbot/parser.py`

- relax the URL regex so the scheme is optional
- keep canonical normalization to `https://x.com/...`

### `raidbot/desktop/telegram_setup.py`

- update `infer_recent_sender_candidates(...)`
- use `message.sender_id` as the candidate `entity_id`
- use the resolved sender entity only for label construction

### Tests

Add or update focused coverage for:

- scheme-less `x.com/...` links
- scheme-less `twitter.com/...` links
- scan returning runtime sender ID plus readable label when runtime sender ID differs from resolved sender entity ID

## Non-Goals

- no change to the main raid execution flow
- no new settings
- no UI redesign
- no loosening of video or action-marker requirements
