# Paperclip Issue Archiver

Paperclip plugin for bulk-archiving old issues by status and cutoff date.

## Contents

- `.codex-plugin/plugin.json` for the plugin manifest
- `dist/` for the runtime bundle consumed by Paperclip
- `assets/` for the iconography
- `skills/` for the usage and workflow prompt

## Behavior

- Opens a compact drawer from the global toolbar
- Lets the user choose an issue status and cutoff date
- Supports preview-only runs via `dryRun`
- Calls `POST /session-api/v1/issues/archive` from the browser UI to archive matching issues

## Dependency

This plugin depends on the separate `paperclip-session-api` service being
reachable behind the host under `/session-api`.

Repository:

- <https://github.com/melchinger/paperclip-session-api>
