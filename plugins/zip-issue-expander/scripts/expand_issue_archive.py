#!/usr/bin/env python3
"""Expand archive attachments from Paperclip issues into stable company paths."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


ARCHIVE_SUFFIXES = (
    (".tar.gz", "tar.gz"),
    (".tgz", "tar.gz"),
    (".tar.bz2", "tar.bz2"),
    (".tbz2", "tar.bz2"),
    (".tar", "tar"),
    (".zip", "zip"),
)
ARCHIVE_CONTENT_TYPES = {
    "application/zip": "zip",
    "application/x-zip-compressed": "zip",
    "application/x-tar": "tar",
    "application/gzip": "tar.gz",
    "application/x-gzip": "tar.gz",
    "application/x-bzip2": "tar.bz2",
    "application/bzip2": "tar.bz2",
}
DEFAULT_BINARY_ROOT = "/var/lib/paperclip/instances/default/data/company-binaries"
DEFAULT_STORAGE_ROOT = "/var/lib/paperclip/instances/default/data/storage"


@dataclass
class IssueRow:
    issue_id: str
    company_id: str
    identifier: str
    title: str


@dataclass
class CommentRow:
    comment_id: str
    issue_id: str
    company_id: str
    body: str


@dataclass
class AttachmentRow:
    attachment_id: str
    asset_id: str
    issue_id: str
    issue_comment_id: str | None
    company_id: str
    provider: str
    object_key: str
    content_type: str
    original_filename: str
    created_at: str
    issue_identifier: str
    issue_title: str


class ArchiveError(Exception):
    pass


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
        else:
            config_path = "/var/lib/paperclip/instances/default/config.json"

    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            config = json.load(fh)
    except Exception as exc:
        raise SystemExit(f"Failed to read database URL from {config_path}: {exc}") from exc

    url = config.get("database", {}).get("connectionString") if isinstance(config, dict) else None
    if isinstance(url, str) and url.strip():
        return url.strip()
    raise SystemExit("DATABASE_URL is required")


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def psql_json(sql: str):
    proc = subprocess.run(
        ["psql", get_database_url(), "-At", "-c", sql],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or "psql query failed")
    raw = (proc.stdout or "").strip()
    if not raw:
        raise SystemExit("No row returned")
    return json.loads(raw)


def db_query_issue_by_id(issue_id: str) -> IssueRow:
    payload = psql_json(
        f"""
        select json_build_object(
            'issue_id', id,
            'company_id', company_id,
            'identifier', identifier,
            'title', title
        )::text
        from public.issues
        where id = {sql_quote(issue_id)}
        limit 1;
        """
    )
    return IssueRow(
        issue_id=str(payload["issue_id"]),
        company_id=str(payload["company_id"]),
        identifier=str(payload["identifier"]),
        title=str(payload["title"]),
    )


def db_query_comment(comment_id: str) -> CommentRow:
    payload = psql_json(
        f"""
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
    )
    return CommentRow(
        comment_id=str(payload["comment_id"]),
        issue_id=str(payload["issue_id"]),
        company_id=str(payload["company_id"]),
        body=str(payload.get("body") or ""),
    )


def _attachment_from_payload(payload: dict[str, object]) -> AttachmentRow:
    return AttachmentRow(
        attachment_id=str(payload["attachment_id"]),
        asset_id=str(payload["asset_id"]),
        issue_id=str(payload["issue_id"]),
        issue_comment_id=str(payload["issue_comment_id"]) if payload.get("issue_comment_id") else None,
        company_id=str(payload["company_id"]),
        provider=str(payload["provider"]),
        object_key=str(payload["object_key"]),
        content_type=str(payload.get("content_type") or ""),
        original_filename=str(payload.get("original_filename") or ""),
        created_at=str(payload.get("created_at") or ""),
        issue_identifier=str(payload.get("issue_identifier") or ""),
        issue_title=str(payload.get("issue_title") or ""),
    )


def db_query_attachment(attachment_id: str) -> AttachmentRow:
    payload = psql_json(
        f"""
        select json_build_object(
            'attachment_id', ia.id,
            'asset_id', ia.asset_id,
            'issue_id', ia.issue_id,
            'issue_comment_id', ia.issue_comment_id,
            'company_id', ia.company_id,
            'provider', a.provider,
            'object_key', a.object_key,
            'content_type', coalesce(a.content_type, ''),
            'original_filename', coalesce(a.original_filename, ''),
            'created_at', ia.created_at,
            'issue_identifier', i.identifier,
            'issue_title', i.title
        )::text
        from public.issue_attachments ia
        join public.assets a on a.id = ia.asset_id
        join public.issues i on i.id = ia.issue_id
        where ia.id = {sql_quote(attachment_id)}
        limit 1;
        """
    )
    return _attachment_from_payload(payload)


def db_query_archive_attachments_for_issue(issue_id: str, *, comment_id: str | None = None) -> list[AttachmentRow]:
    comment_filter = (
        "ia.issue_comment_id = " + sql_quote(comment_id)
        if comment_id
        else "ia.issue_comment_id is null"
    )
    rows = psql_json(
        f"""
        select coalesce(json_agg(row_to_json(t) order by t.created_at desc), '[]')::text
        from (
            select ia.id as attachment_id,
                   ia.asset_id as asset_id,
                   ia.issue_id as issue_id,
                   ia.issue_comment_id as issue_comment_id,
                   ia.company_id as company_id,
                   a.provider as provider,
                   a.object_key as object_key,
                   coalesce(a.content_type, '') as content_type,
                   coalesce(a.original_filename, '') as original_filename,
                   ia.created_at as created_at,
                   i.identifier as issue_identifier,
                   i.title as issue_title
              from public.issue_attachments ia
              join public.assets a on a.id = ia.asset_id
              join public.issues i on i.id = ia.issue_id
             where ia.issue_id = {sql_quote(issue_id)}
               and {comment_filter}
        ) t;
        """
    )
    return [_attachment_from_payload(row) for row in rows]


def resolve_local_storage_dir() -> Path:
    override = os.environ.get("PAPERCLIP_STORAGE_LOCAL_DIR", "").strip()
    if override:
        return Path(override)

    paperclip_home = os.environ.get("PAPERCLIP_HOME", "").strip()
    instance_id = os.environ.get("PAPERCLIP_INSTANCE_ID", "default").strip() or "default"
    if paperclip_home:
        return Path(paperclip_home) / "instances" / instance_id / "data" / "storage"
    return Path(DEFAULT_STORAGE_ROOT)


def local_path_for_attachment(attachment: AttachmentRow) -> Path:
    if attachment.provider != "local_disk":
        raise ArchiveError(f"Unsupported asset provider: {attachment.provider}")
    path = resolve_local_storage_dir() / attachment.object_key
    if not path.exists():
        raise ArchiveError(f"Local asset file not found: {path}")
    return path


def detect_archive_kind(filename: str, content_type: str) -> str | None:
    lower_name = filename.lower()
    for suffix, kind in ARCHIVE_SUFFIXES:
        if lower_name.endswith(suffix):
            return kind
    return ARCHIVE_CONTENT_TYPES.get(content_type.lower())


def sanitize_path_component(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value.strip())
    safe = safe.strip(".-")
    return safe or "item"


def sanitize_member_path(name: str) -> Path:
    normalized = name.replace("\\", "/").lstrip("/")
    pure = PurePosixPath(normalized)
    parts = [part for part in pure.parts if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise ArchiveError(f"Unsafe archive member path: {name}")
    return Path(*parts)


def path_is_within(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def extract_zip(archive_path: Path, dest_root: Path, *, max_entries: int, max_total_bytes: int) -> tuple[list[str], int]:
    listed: list[str] = []
    total_bytes = 0
    files_seen = 0
    with zipfile.ZipFile(archive_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            if info.flag_bits & 0x1:
                raise ArchiveError("Encrypted ZIP entries are not supported")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ArchiveError(f"ZIP symlink entries are not supported: {info.filename}")
            rel_path = sanitize_member_path(info.filename)
            target = (dest_root / rel_path).resolve(strict=False)
            if not path_is_within(dest_root, target):
                raise ArchiveError(f"Unsafe extraction path: {info.filename}")
            files_seen += 1
            if files_seen > max_entries:
                raise ArchiveError(f"Archive exceeds max file count of {max_entries}")
            total_bytes += int(info.file_size or 0)
            if total_bytes > max_total_bytes:
                raise ArchiveError(f"Archive exceeds max total bytes of {max_total_bytes}")
            ensure_parent(target)
            with zf.open(info, "r") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            listed.append(str(target))
    return listed, total_bytes


def extract_tar(archive_path: Path, dest_root: Path, *, mode: str, max_entries: int, max_total_bytes: int) -> tuple[list[str], int]:
    listed: list[str] = []
    total_bytes = 0
    files_seen = 0
    with tarfile.open(archive_path, mode) as tf:
        for member in tf.getmembers():
            if member.isdir():
                continue
            if member.issym() or member.islnk():
                raise ArchiveError(f"Tar symlink entries are not supported: {member.name}")
            if not member.isfile():
                raise ArchiveError(f"Unsupported tar member type: {member.name}")
            rel_path = sanitize_member_path(member.name)
            target = (dest_root / rel_path).resolve(strict=False)
            if not path_is_within(dest_root, target):
                raise ArchiveError(f"Unsafe extraction path: {member.name}")
            files_seen += 1
            if files_seen > max_entries:
                raise ArchiveError(f"Archive exceeds max file count of {max_entries}")
            total_bytes += int(member.size or 0)
            if total_bytes > max_total_bytes:
                raise ArchiveError(f"Archive exceeds max total bytes of {max_total_bytes}")
            ensure_parent(target)
            src = tf.extractfile(member)
            if src is None:
                raise ArchiveError(f"Could not read tar member: {member.name}")
            with src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            listed.append(str(target))
    return listed, total_bytes


def extract_archive(archive_path: Path, archive_kind: str, dest_root: Path, *, max_entries: int, max_total_bytes: int) -> tuple[list[str], int]:
    if archive_kind == "zip":
        return extract_zip(archive_path, dest_root, max_entries=max_entries, max_total_bytes=max_total_bytes)
    if archive_kind == "tar":
        return extract_tar(archive_path, dest_root, mode="r:", max_entries=max_entries, max_total_bytes=max_total_bytes)
    if archive_kind == "tar.gz":
        return extract_tar(archive_path, dest_root, mode="r:gz", max_entries=max_entries, max_total_bytes=max_total_bytes)
    if archive_kind == "tar.bz2":
        return extract_tar(archive_path, dest_root, mode="r:bz2", max_entries=max_entries, max_total_bytes=max_total_bytes)
    raise ArchiveError(f"Unsupported archive type: {archive_kind}")


def build_target_dir(binary_root: Path, attachment: AttachmentRow) -> Path:
    issue_component = sanitize_path_component(attachment.issue_identifier or attachment.issue_id)
    return (
        binary_root
        / sanitize_path_component(attachment.company_id)
        / "zip-expander"
        / issue_component
        / sanitize_path_component(attachment.attachment_id)
    )


def load_manifest(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def build_result_from_manifest(
    manifest: dict[str, object],
    *,
    attachment: AttachmentRow,
    source_kind: str,
    source_id: str,
    max_listed_files: int,
    reused: bool,
) -> dict[str, object]:
    files = [str(item) for item in manifest.get("files", []) if isinstance(item, str)]
    listed = files[:max_listed_files]
    return {
        "ok": True,
        "issueId": attachment.issue_id,
        "issueIdentifier": attachment.issue_identifier,
        "issueTitle": attachment.issue_title,
        "sourceKind": source_kind,
        "sourceId": source_id,
        "attachmentId": attachment.attachment_id,
        "assetId": attachment.asset_id,
        "archiveKind": manifest.get("archiveKind") or detect_archive_kind(attachment.original_filename, attachment.content_type),
        "originalFilename": attachment.original_filename,
        "extractRoot": manifest.get("extractRoot"),
        "manifestPath": manifest.get("manifestPath"),
        "fileCount": len(files),
        "totalBytes": manifest.get("totalBytes", 0),
        "listedFiles": listed,
        "remainingFileCount": max(0, len(files) - len(listed)),
        "reused": reused,
    }


def expand_attachment(
    attachment: AttachmentRow,
    *,
    source_kind: str,
    source_id: str,
    binary_root: Path,
    max_entries: int,
    max_total_bytes: int,
    max_listed_files: int,
) -> dict[str, object]:
    archive_kind = detect_archive_kind(attachment.original_filename, attachment.content_type)
    if not archive_kind:
        return {}

    target_dir = build_target_dir(binary_root, attachment)
    manifest_path = target_dir / "manifest.json"
    existing = load_manifest(manifest_path)
    if existing:
        return build_result_from_manifest(
            existing,
            attachment=attachment,
            source_kind=source_kind,
            source_id=source_id,
            max_listed_files=max_listed_files,
            reused=True,
        )

    archive_path = local_path_for_attachment(attachment)
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    temp_parent = target_dir.parent
    temp_dir_name = tempfile.mkdtemp(prefix=f".{sanitize_path_component(attachment.attachment_id)}-", dir=str(temp_parent))
    staging_dir = Path(temp_dir_name)
    files_root = staging_dir / "files"
    files_root.mkdir(parents=True, exist_ok=True)

    try:
        files, total_bytes = extract_archive(
            archive_path,
            archive_kind,
            files_root,
            max_entries=max_entries,
            max_total_bytes=max_total_bytes,
        )
        manifest = {
            "attachmentId": attachment.attachment_id,
            "assetId": attachment.asset_id,
            "issueId": attachment.issue_id,
            "issueIdentifier": attachment.issue_identifier,
            "companyId": attachment.company_id,
            "originalFilename": attachment.original_filename,
            "archiveKind": archive_kind,
            "extractRoot": str(target_dir / "files"),
            "manifestPath": str(target_dir / "manifest.json"),
            "totalBytes": total_bytes,
            "extractedAt": datetime.now(timezone.utc).isoformat(),
            "files": [str((target_dir / "files" / Path(path).relative_to(files_root)).resolve(strict=False)) for path in files],
        }
        with open(staging_dir / "manifest.json", "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)

        if target_dir.exists():
            shutil.rmtree(staging_dir)
            existing = load_manifest(manifest_path)
            if existing:
                return build_result_from_manifest(
                    existing,
                    attachment=attachment,
                    source_kind=source_kind,
                    source_id=source_id,
                    max_listed_files=max_listed_files,
                    reused=True,
                )
            raise ArchiveError(f"Target directory already exists without readable manifest: {target_dir}")

        os.replace(staging_dir, target_dir)
        final_manifest = load_manifest(target_dir / "manifest.json") or manifest
        return build_result_from_manifest(
            final_manifest,
            attachment=attachment,
            source_kind=source_kind,
            source_id=source_id,
            max_listed_files=max_listed_files,
            reused=False,
        )
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


def process_attachments(
    attachments: list[AttachmentRow],
    *,
    source_kind: str,
    source_id: str,
    binary_root: Path,
    max_entries: int,
    max_total_bytes: int,
    max_listed_files: int,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for attachment in attachments:
        archive_kind = detect_archive_kind(attachment.original_filename, attachment.content_type)
        if not archive_kind:
            continue
        try:
            result = expand_attachment(
                attachment,
                source_kind=source_kind,
                source_id=source_id,
                binary_root=binary_root,
                max_entries=max_entries,
                max_total_bytes=max_total_bytes,
                max_listed_files=max_listed_files,
            )
            if result:
                results.append(result)
        except Exception as exc:
            results.append({
                "ok": False,
                "issueId": attachment.issue_id,
                "issueIdentifier": attachment.issue_identifier,
                "issueTitle": attachment.issue_title,
                "sourceKind": source_kind,
                "sourceId": source_id,
                "attachmentId": attachment.attachment_id,
                "assetId": attachment.asset_id,
                "archiveKind": archive_kind,
                "originalFilename": attachment.original_filename,
                "error": str(exc),
            })
    return results


def analyze_request(
    *,
    issue_id: str | None,
    comment_id: str | None,
    attachment_id: str | None,
    binary_root: Path,
    max_entries: int,
    max_total_bytes: int,
    max_listed_files: int,
) -> dict[str, object]:
    if attachment_id:
        attachment = db_query_attachment(attachment_id)
        results = process_attachments(
            [attachment],
            source_kind="attachment",
            source_id=attachment.attachment_id,
            binary_root=binary_root,
            max_entries=max_entries,
            max_total_bytes=max_total_bytes,
            max_listed_files=max_listed_files,
        )
        return {"found": bool(results), "results": results}

    if comment_id:
        comment = db_query_comment(comment_id)
        attachments = db_query_archive_attachments_for_issue(comment.issue_id, comment_id=comment.comment_id)
        results = process_attachments(
            attachments,
            source_kind="comment",
            source_id=comment.comment_id,
            binary_root=binary_root,
            max_entries=max_entries,
            max_total_bytes=max_total_bytes,
            max_listed_files=max_listed_files,
        )
        return {"found": bool(results), "results": results}

    if issue_id:
        issue = db_query_issue_by_id(issue_id)
        attachments = db_query_archive_attachments_for_issue(issue.issue_id)
        results = process_attachments(
            attachments,
            source_kind="issue",
            source_id=issue.issue_id,
            binary_root=binary_root,
            max_entries=max_entries,
            max_total_bytes=max_total_bytes,
            max_listed_files=max_listed_files,
        )
        return {"found": bool(results), "results": results}

    raise SystemExit("issue_id, comment_id, or attachment_id is required")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue-id", default="")
    parser.add_argument("--comment-id", default="")
    parser.add_argument("--attachment-id", default="")
    parser.add_argument("--binary-root", default=DEFAULT_BINARY_ROOT)
    parser.add_argument("--max-entries", type=int, default=500)
    parser.add_argument("--max-total-bytes", type=int, default=200 * 1024 * 1024)
    parser.add_argument("--max-listed-files", type=int, default=40)
    args = parser.parse_args()

    result = analyze_request(
        issue_id=args.issue_id or None,
        comment_id=args.comment_id or None,
        attachment_id=args.attachment_id or None,
        binary_root=Path(args.binary_root),
        max_entries=max(1, int(args.max_entries)),
        max_total_bytes=max(1024, int(args.max_total_bytes)),
        max_listed_files=max(1, int(args.max_listed_files)),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
