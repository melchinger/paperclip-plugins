# Image Issue Analyzer

Paperclip plugin for image-backed issues and comments.

What it does:

- listens to `issue.created`, `issue.comment.created`, and `issue.comment_added`
- looks for Markdown image embeds like `![](/api/assets/<id>/content)`
- resolves the asset to the local storage path
- copies the image into a temporary working file
- runs Kimi against the local image file
- posts the analysis back as a normal text comment
- can optionally move an issue from `backlog` to `todo` after a successful analysis comment

## Layout

- `src/manifest.js` - Paperclip plugin manifest
- `src/worker.js` - event handler and comment writer
- `scripts/analyze_issue_image.py` - local analyzer CLI and HTTP helper
- `.codex-plugin/plugin.json` - Codex plugin metadata scaffold

## Runtime

The plugin worker invokes the local analyzer script directly as `paperclip`
user-facing process context. The script resolves the Paperclip database and
storage paths from the standard instance config at
`/var/lib/paperclip/instances/default/config.json` when environment variables
are not present.

## Instance config

Current config keys from `src/manifest.js`:

- `analyzerBinary`
  default: `python3`
- `analyzerUrl`
  default: `http://127.0.0.1:4015/analyze`
  kept only for compatibility with older installs
- `analysisTimeoutMs`
  default: `120000`
- `commentPrefix`
  default: `<!-- image-issue-analyzer -->`
- `moveBacklogToTodoAfterProcessing`
  default: `false`
  if enabled, the plugin sets an issue from `backlog` to `todo` after it posted a successful analysis comment

## Manual dry-run

Analyze a single issue directly:

```bash
sudo -u paperclip env \
  HOME=/var/lib/paperclip \
  PAPERCLIP_HOME=/var/lib/paperclip \
  PAPERCLIP_INSTANCE_ID=default \
  DATABASE_URL='postgres://paperclip_app:<redacted>@127.0.0.1:5432/paperclip' \
  python3 scripts/analyze_issue_image.py --issue MEL-286
```

If `DATABASE_URL` is omitted, the helper falls back to the standard Paperclip
instance config and resolves the database connection from there.

If you want the plugin to skip a comment loop, keep the marker comment prefix
enabled. The worker uses:

```text
<!-- image-issue-analyzer -->
```

## Temp file flow

The helper does not analyze the storage file in place. It copies the asset into
a temporary directory, passes that staged file to Kimi, and removes the temp
file immediately after the analysis finishes.

## Troubleshooting

- no comment appears:
  check that the issue or comment actually contains a Markdown image embed, not only a plain attachment
- the issue status does not move:
  `moveBacklogToTodoAfterProcessing` defaults to `false`
- helper errors:
  run the manual dry-run and inspect `journalctl -u paperclip -n 100 --no-pager`
