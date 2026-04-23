#!/usr/bin/env python3
"""Local image analyzer for Paperclip issues and comments.

This script can be used in two ways:

1. CLI mode:
   python3 scripts/analyze_issue_image.py --issue MEL-286

2. HTTP helper mode:
   python3 scripts/analyze_issue_image.py --serve --host 127.0.0.1 --port 4015

The HTTP mode exists so a Paperclip plugin worker can call a local helper
without needing shell access inside the worker process.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\((/api/(assets|attachments)/([0-9a-fA-F-]+)/content)\)"
)
COMMENT_MARKER = "<!-- image-issue-analyzer -->"
DEFAULT_ANALYZER = "kimi"
ANALYZER_FALLBACK_DIRS = (
    str(Path.home() / ".local" / "bin"),
    "/var/lib/paperclip/.local/bin",
    "/usr/local/bin",
)


def resolve_analyzer(name: str) -> str:
    """Resolve an analyzer command to an absolute path.

    Lookup order:
      1. `IIA_ANALYZER` env var (allows pinning to an absolute path)
      2. the requested name as-is, if it's already an absolute path
      3. `shutil.which` against the current PATH
      4. ANALYZER_FALLBACK_DIRS (uv-tool installs etc. that aren't on the
         worker process PATH)
    Raises SystemExit if nothing matches.
    """
    override = os.environ.get("IIA_ANALYZER", "").strip()
    if override:
        if Path(override).is_absolute() and Path(override).exists():
            return override
        resolved = shutil.which(override)
        if resolved:
            return resolved
        raise SystemExit(f"IIA_ANALYZER set but not found: {override}")

    if Path(name).is_absolute():
        if Path(name).exists():
            return name
        raise SystemExit(f"Analyzer path does not exist: {name}")

    resolved = shutil.which(name)
    if resolved:
        return resolved

    for d in ANALYZER_FALLBACK_DIRS:
        candidate = Path(d) / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)

    raise SystemExit(
        f"Analyzer binary '{name}' not found on PATH or in fallback dirs "
        f"({', '.join(ANALYZER_FALLBACK_DIRS)}). "
        "Set IIA_ANALYZER to an absolute path."
    )


@dataclass
class IssueRow:
    issue_id: str
    company_id: str
    identifier: str
    title: str
    description: str


@dataclass
class CommentRow:
    comment_id: str
    issue_id: str
    company_id: str
    body: str


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def get_database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if value:
        return value

    config_path = os.environ.get("PAPERCLIP_CONFIG", "").strip()
    if not config_path:
        paperclip_home = os.environ.get("PAPERCLIP_HOME", "").strip()
        instance_id = os.environ.get("PAPERCLIP_INSTANCE_ID", "default").strip() or "default"
        if paperclip_home:
            config_path = str(Path(paperclip_home) / "instances" / instance_id / "config.json")
        if not config_path:
            config_path = "/var/lib/paperclip/instances/default/config.json"

    if config_path:
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                config = json.load(fh)
            url = (
                config.get("database", {}).get("connectionString")
                if isinstance(config, dict)
                else None
            )
            if isinstance(url, str) and url.strip():
                return url.strip()
        except Exception as exc:
            raise SystemExit(f"Failed to read database URL from {config_path}: {exc}") from exc

    raise SystemExit("DATABASE_URL is required")


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def psql_scalar(sql: str) -> str:
    proc = subprocess.run(
        ["psql", get_database_url(), "-At", "-c", sql],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or "psql query failed")

    line = (proc.stdout or "").strip()
    if not line:
        raise SystemExit("No row returned")
    return line


def db_query_issue_by_id(issue_id: str) -> IssueRow:
    sql = f"""
        select json_build_object(
            'issue_id', id,
            'company_id', company_id,
            'identifier', identifier,
            'title', title,
            'description', coalesce(description, '')
        )::text
        from public.issues
        where id = {sql_quote(issue_id)}
        limit 1;
    """
    payload = json.loads(psql_scalar(sql))
    return IssueRow(
        issue_id=str(payload["issue_id"]),
        company_id=str(payload["company_id"]),
        identifier=str(payload["identifier"]),
        title=str(payload["title"]),
        description=str(payload.get("description") or ""),
    )


def db_query_issue_by_identifier(identifier: str) -> IssueRow:
    sql = f"""
        select json_build_object(
            'issue_id', id,
            'company_id', company_id,
            'identifier', identifier,
            'title', title,
            'description', coalesce(description, '')
        )::text
        from public.issues
        where identifier = {sql_quote(identifier)}
        limit 1;
    """
    payload = json.loads(psql_scalar(sql))
    return IssueRow(
        issue_id=str(payload["issue_id"]),
        company_id=str(payload["company_id"]),
        identifier=str(payload["identifier"]),
        title=str(payload["title"]),
        description=str(payload.get("description") or ""),
    )


def db_query_comment(comment_id: str) -> CommentRow:
    sql = f"""
        select json_build_object(
            'comment_id', id,
            'issue_id', issue_id,
            'company_id', company_id,
            'body', coalesce(body, '')
        )::text
        from public.issue_comments
        where id = {sql_quote(comment_id)}
        limit 1;
    """
    payload = json.loads(psql_scalar(sql))
    return CommentRow(
        comment_id=str(payload["comment_id"]),
        issue_id=str(payload["issue_id"]),
        company_id=str(payload["company_id"]),
        body=str(payload.get("body") or ""),
    )


def db_query_asset(asset_id: str) -> dict[str, str]:
    sql = f"""
        select json_build_object(
            'id', id,
            'company_id', company_id,
            'provider', provider,
            'object_key', object_key,
            'content_type', coalesce(content_type, ''),
            'original_filename', coalesce(original_filename, '')
        )::text
        from public.assets
        where id = {sql_quote(asset_id)}
        limit 1;
    """
    payload = json.loads(psql_scalar(sql))
    return {
        "id": str(payload["id"]),
        "company_id": str(payload["company_id"]),
        "provider": str(payload["provider"]),
        "object_key": str(payload["object_key"]),
        "content_type": str(payload.get("content_type") or ""),
        "original_filename": str(payload.get("original_filename") or ""),
    }


def db_query_image_attachments_for_issue(
    issue_id: str, *, comment_id: str | None = None
) -> list[dict[str, str]]:
    """Return image attachments linked to an issue (or specifically a comment).

    `comment_id=None` matches issue-level attachments (`issue_comment_id IS
    NULL`). When a `comment_id` is provided, only attachments tied to that
    comment are returned. Results are sorted newest first and filtered to
    `image/*` content types.
    """
    if comment_id:
        comment_filter = "ia.issue_comment_id = " + sql_quote(comment_id)
    else:
        comment_filter = "ia.issue_comment_id is null"
    sql = f"""
        select coalesce(json_agg(row_to_json(t) order by t.created_at desc),
                        '[]')::text
        from (
            select ia.id              as attachment_id,
                   ia.asset_id        as asset_id,
                   ia.company_id      as company_id,
                   a.provider         as provider,
                   a.object_key       as object_key,
                   coalesce(a.content_type, '')      as content_type,
                   coalesce(a.original_filename, '') as original_filename,
                   ia.created_at      as created_at
              from public.issue_attachments ia
              join public.assets a on a.id = ia.asset_id
             where ia.issue_id = {sql_quote(issue_id)}
               and {comment_filter}
        ) t;
    """
    rows = json.loads(psql_scalar(sql))
    out: list[dict[str, str]] = []
    for r in rows:
        ctype = str(r.get("content_type") or "")
        if not ctype.startswith("image/"):
            continue
        out.append({
            "attachment_id": str(r["attachment_id"]),
            "asset_id": str(r["asset_id"]),
            "company_id": str(r["company_id"]),
            "provider": str(r["provider"]),
            "object_key": str(r["object_key"]),
            "content_type": ctype,
            "original_filename": str(r.get("original_filename") or ""),
        })
    return out


def db_query_attachment_asset(attachment_id: str) -> dict[str, str]:
    sql = f"""
        select json_build_object(
            'attachment_id', ia.id,
            'company_id', ia.company_id,
            'asset_id', ia.asset_id,
            'provider', a.provider,
            'object_key', a.object_key,
            'content_type', coalesce(a.content_type, ''),
            'original_filename', coalesce(a.original_filename, '')
        )::text
        from public.issue_attachments ia
        join public.assets a on a.id = ia.asset_id
        where ia.id = {sql_quote(attachment_id)}
        limit 1;
    """
    payload = json.loads(psql_scalar(sql))
    return {
        "attachment_id": str(payload["attachment_id"]),
        "company_id": str(payload["company_id"]),
        "asset_id": str(payload["asset_id"]),
        "provider": str(payload["provider"]),
        "object_key": str(payload["object_key"]),
        "content_type": str(payload.get("content_type") or ""),
        "original_filename": str(payload.get("original_filename") or ""),
    }


def resolve_local_storage_dir() -> Path:
    storage_dir = os.environ.get("PAPERCLIP_STORAGE_LOCAL_DIR", "").strip()
    if storage_dir:
        return Path(storage_dir)

    paperclip_home = os.environ.get("PAPERCLIP_HOME", "").strip()
    instance_id = os.environ.get("PAPERCLIP_INSTANCE_ID", "default").strip() or "default"
    if paperclip_home:
        return Path(paperclip_home) / "instances" / instance_id / "data" / "storage"
    return Path("/var/lib/paperclip/instances/default/data/storage")


def local_path_for_asset(asset_row: dict[str, str]) -> Path:
    if asset_row["provider"] != "local_disk":
        raise SystemExit(f"Asset storage provider is not local_disk: {asset_row['provider']}")

    path = resolve_local_storage_dir() / asset_row["object_key"]
    if not path.exists():
        raise SystemExit(f"Local asset file not found: {path}")
    return path


def stage_asset_image(image_path: Path) -> tuple[Path, tempfile.TemporaryDirectory]:
    tempdir = tempfile.TemporaryDirectory(prefix="image-issue-analyzer-")
    staged_path = Path(tempdir.name) / image_path.name
    shutil.copy2(image_path, staged_path)
    return staged_path, tempdir


def find_image_asset_id(body: str) -> str | None:
    if not body or COMMENT_MARKER in body:
        return None
    match = IMAGE_RE.search(body)
    if not match:
        return None
    return match.group(3)


def run_analyzer(image_path: Path, issue: IssueRow, analyzer_cmd: list[str]) -> str:
    if analyzer_cmd:
        analyzer_cmd = [resolve_analyzer(analyzer_cmd[0]), *analyzer_cmd[1:]]
    prompt = (
        f"Analyze the image file at this local path: {image_path}\n"
        f"Issue: {issue.identifier}\n"
        f"Issue title: {issue.title}\n"
        "Return only the final image analysis.\n"
        "Be brief, concrete, and specific.\n"
        "Describe only what is visibly in the image and what looks off.\n"
        "Do not explain your reasoning, do not mention these instructions, "
        "do not include tool logs, and do not add extra commentary.\n"
        "Use up to 20 short bullet points if that helps, otherwise 1 short paragraph.\n"
        "If nothing looks wrong, say that briefly."
    )

    proc = subprocess.run(
        [
            *analyzer_cmd,
            "--quiet",
            "--work-dir",
            str(image_path.parent),
            "--add-dir",
            str(image_path.parent),
            "-p",
            prompt,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or "Analyzer command failed")
    return (proc.stdout or "").strip()


def analyze_request(
    *,
    issue_id: str | None = None,
    issue_identifier: str | None = None,
    comment_id: str | None = None,
    analyzer: str = DEFAULT_ANALYZER,
) -> dict[str, object]:
    if not issue_id and not issue_identifier and not comment_id:
        raise SystemExit("issue_id or issue_identifier is required")

    if comment_id:
        comment = db_query_comment(comment_id)
        issue = db_query_issue_by_id(comment.issue_id)
        body = comment.body
        source_kind = "comment"
        source_id = comment.comment_id
    else:
        issue = db_query_issue_by_id(issue_id) if issue_id else db_query_issue_by_identifier(issue_identifier or "")
        body = issue.description
        source_kind = "issue"
        source_id = issue.issue_id

    asset_id = find_image_asset_id(body)
    asset_row: dict[str, str] | None = None
    asset_source = "inline"

    if asset_id:
        if body.find("/api/attachments/") >= 0:
            asset_row = db_query_attachment_asset(asset_id)
        else:
            asset_row = db_query_asset(asset_id)
    elif COMMENT_MARKER in (body or ""):
        # This is one of our own analysis comments. Never fall back to
        # attachments — that would create an analysis loop.
        return {
            "found": False,
            "reason": "Source body is an existing analysis comment",
            "issueId": issue.issue_id,
            "issueIdentifier": issue.identifier,
            "issueTitle": issue.title,
            "sourceKind": source_kind,
            "sourceId": source_id,
        }
    else:
        # Fallback: no Markdown embed, but the issue or comment may have a
        # binary image attached via public.issue_attachments (e.g. the
        # screenbug -> paperclip bridge attaches the screenshot directly
        # without writing a markdown link).
        if source_kind == "comment":
            attachments = db_query_image_attachments_for_issue(
                issue.issue_id, comment_id=source_id
            )
        else:
            attachments = db_query_image_attachments_for_issue(issue.issue_id)

        if not attachments:
            return {
                "found": False,
                "reason": (
                    "No Markdown image embed and no image attachment found "
                    "for this " + source_kind
                ),
                "issueId": issue.issue_id,
                "issueIdentifier": issue.identifier,
                "issueTitle": issue.title,
                "sourceKind": source_kind,
                "sourceId": source_id,
            }

        chosen = attachments[0]
        asset_id = chosen["asset_id"]
        asset_row = {
            "id": chosen["asset_id"],
            "company_id": chosen["company_id"],
            "provider": chosen["provider"],
            "object_key": chosen["object_key"],
            "content_type": chosen["content_type"],
            "original_filename": chosen["original_filename"],
        }
        asset_source = "attachment"
    image_path = local_path_for_asset(asset_row)
    staged_path, tempdir = stage_asset_image(image_path)
    try:
        analyzer_output = run_analyzer(staged_path, issue, [analyzer])
    finally:
        tempdir.cleanup()

    return {
        "found": True,
        "issueId": issue.issue_id,
        "issueIdentifier": issue.identifier,
        "issueTitle": issue.title,
        "sourceKind": source_kind,
        "sourceId": source_id,
        "assetId": asset_id,
        "assetSource": asset_source,
        "imagePath": str(image_path),
        "stagedImagePath": str(staged_path),
        "analysis": analyzer_output,
        "analyzerOutput": analyzer_output,
    }


class AnalyzeHandler(BaseHTTPRequestHandler):
    server_version = "ImageIssueAnalyzer/1.0"

    def _write_json(self, status: int, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/analyze":
            self._write_json(404, {"error": "Not found"})
            return

        length = int(self.headers.get("content-length") or "0")
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            self._write_json(400, {"error": "Invalid JSON"})
            return

        try:
            result = analyze_request(
                issue_id=str(payload["issueId"]) if payload.get("issueId") else None,
                issue_identifier=str(payload["issueIdentifier"]) if payload.get("issueIdentifier") else None,
                comment_id=str(payload["commentId"]) if payload.get("commentId") else None,
                analyzer=str(payload.get("analyzer") or DEFAULT_ANALYZER),
            )
        except SystemExit as exc:
            self._write_json(400, {"error": str(exc)})
            return
        except Exception as exc:  # pragma: no cover - surface runtime failures directly
            self._write_json(500, {"error": str(exc)})
            return

        self._write_json(200, result)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def print_result(result: dict[str, object]) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", help="Issue identifier such as MEL-286")
    parser.add_argument("--issue-id", help="Issue UUID")
    parser.add_argument("--comment-id", help="Issue comment UUID")
    parser.add_argument("--analyzer", default=DEFAULT_ANALYZER)
    parser.add_argument("--serve", action="store_true", help="Run an HTTP analyzer service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4015)
    args = parser.parse_args()

    if args.serve:
        server = ThreadingHTTPServer((args.host, args.port), AnalyzeHandler)
        print(f"Serving image analyzer on http://{args.host}:{args.port}/analyze", file=sys.stderr)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return 130
        return 0

    result = analyze_request(
        issue_id=args.issue_id,
        issue_identifier=args.issue,
        comment_id=args.comment_id,
        analyzer=args.analyzer,
    )
    print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
