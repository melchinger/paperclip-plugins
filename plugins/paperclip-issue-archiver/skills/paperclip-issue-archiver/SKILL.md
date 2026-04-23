---
name: paperclip-issue-archiver
description: Archive Paperclip issues older than a selected cutoff date and matching a status filter.
---

# Paperclip Issue Archiver

Use this plugin when the user wants to archive a batch of old Paperclip issues.

## UI flow

1. Open the archive panel.
2. Choose a status.
3. Pick a cutoff date.
4. Optionally preview the affected issues first.
5. Confirm the archive action.

## Backend contract

The plugin should call:

`POST /v1/issues/archive`

Request body:

```json
{
  "companyId": "uuid",
  "status": "done",
  "before": "2026-04-01",
  "dryRun": true
}
```

Notes:

- `before` may be a date or an ISO datetime.
- `dryRun: true` should only return the matching issues.
- The real archive action should set `hiddenAt` on every matching issue.

## Recommended behavior

- Show the preview count before confirming.
- Keep the UI compact: one dropdown, one date field, one preview button, one archive button.
- Use the backend response to report exactly how many issues were archived.
