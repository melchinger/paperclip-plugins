# Zip Issue Expander

Paperclip plugin for archive-backed issues and comments.

What it does:

- listens to `issue.created`, `issue.updated`, and `issue.comment.created`
- detects archive attachments such as `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`
- expands them into a stable company-scoped binary path
- writes a comment back onto the issue with the local extraction root and direct file paths
- stores a `manifest.json` beside the extracted files for later cleanup
- can optionally move an issue from `backlog` to `todo` after a successful expansion comment

Why `issue.updated`:

- the current Paperclip plugin event model does not expose dedicated attachment events to plugins
- archive detection therefore runs idempotently on issue create/update and on comment creation

## Extraction layout

Archives are expanded under:

```text
/var/lib/paperclip/instances/default/data/company-binaries/<companyId>/zip-expander/<issueIdentifier>/<attachmentId>/
```

Each expansion directory contains:

- `manifest.json`
- `files/` with the extracted archive tree

## Instance config

Current config keys from `src/manifest.js`:

- `helperBinary`
  default: `python3`
- `extractionTimeoutMs`
  default: `120000`
- `commentPrefix`
  default: `<!-- zip-issue-expander -->`
- `binaryRoot`
  default: `/var/lib/paperclip/instances/default/data/company-binaries`
- `maxArchiveEntries`
  default: `500`
- `maxTotalBytes`
  default: `209715200`
- `maxListedFiles`
  default: `40`
- `moveBacklogToTodoAfterProcessing`
  default: `false`
  if enabled, the plugin sets an issue from `backlog` to `todo` after it posted a successful expansion comment

## Safety rules

- rejects unsafe member paths such as `../...` and absolute paths
- rejects symlinks and unsupported special files
- enforces max file count and max total uncompressed bytes
- keeps one stable directory per attachment so later cleanup can remove old company data deterministically

## Build and check

```bash
npm run build
npm run check
```

## Manual dry-run

Expand one attachment directly:

```bash
python3 scripts/expand_issue_archive.py --attachment-id <attachment-uuid>
```

Expand all supported root-level issue attachments:

```bash
python3 scripts/expand_issue_archive.py --issue-id <issue-uuid>
```

## Troubleshooting

- archive upload happened, but no comment appeared:
  the plugin now reacts on `issue.updated`; touch the issue once more if an older upload predated the fix
- attachment is ignored:
  only supported archive suffixes / content types are processed
- no status move happened:
  `moveBacklogToTodoAfterProcessing` defaults to `false`
- extraction failed:
  inspect the issue comment body and `journalctl -u paperclip -n 100 --no-pager`
