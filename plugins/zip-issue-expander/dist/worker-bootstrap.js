import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { definePlugin, runWorker } from "@paperclipai/plugin-sdk";

const DEFAULT_COMMENT_PREFIX = "<!-- zip-issue-expander -->";
const COMMENT_TITLE_OK = "Archiv entpackt";
const COMMENT_TITLE_ERROR = "Archiv konnte nicht entpackt werden";
const STATE_NAMESPACE = "archive-expander";
const execFileAsync = promisify(execFile);
const HELPER_SCRIPT_PATH = fileURLToPath(new URL("../scripts/expand_issue_archive.py", import.meta.url));

function readString(value, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function readNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function isPluginComment(body, prefix) {
  return typeof body === "string" && body.includes(prefix);
}

function quotePath(path) {
  return `\`${String(path).replaceAll("`", "\\`")}\``;
}

function buildCommentBody(result, prefix) {
  const lines = [
    prefix,
    "",
    `**${result.ok ? COMMENT_TITLE_OK : COMMENT_TITLE_ERROR}**`,
  ];

  if (result.issueIdentifier || result.issueTitle) {
    lines.push(
      [
        "- Ticket:",
        result.issueIdentifier ? ` ${result.issueIdentifier}` : "",
        result.issueTitle ? ` ${result.issueTitle}` : "",
      ].join("")
    );
  }

  if (result.sourceKind) {
    lines.push(`- Quelle: ${result.sourceKind}${result.sourceId ? ` (${result.sourceId})` : ""}`);
  }

  if (result.originalFilename) {
    lines.push(`- Archiv: ${quotePath(result.originalFilename)}`);
  }

  if (result.archiveKind) {
    lines.push(`- Typ: ${quotePath(result.archiveKind)}`);
  }

  if (!result.ok) {
    if (result.error) {
      lines.push(`- Fehler: ${String(result.error).trim()}`);
    }
    return lines.join("\n").trim();
  }

  if (result.extractRoot) {
    lines.push(`- Ablage: ${quotePath(result.extractRoot)}`);
  }

  if (result.manifestPath) {
    lines.push(`- Manifest: ${quotePath(result.manifestPath)}`);
  }

  lines.push(`- Dateien: ${result.fileCount ?? 0}`);
  lines.push(`- Gesamtgroesse entpackt: ${result.totalBytes ?? 0} Bytes`);
  lines.push(`- Status: ${result.reused ? "bereits vorhanden, wiederverwendet" : "neu entpackt"}`);

  const listedFiles = Array.isArray(result.listedFiles) ? result.listedFiles : [];
  if (listedFiles.length > 0) {
    lines.push("");
    lines.push("Direkte Dateipfade:");
    for (const filePath of listedFiles) {
      lines.push(`- ${quotePath(filePath)}`);
    }
  }

  const remaining = Number(result.remainingFileCount ?? 0);
  if (remaining > 0) {
    lines.push(`- ... plus ${remaining} weitere Dateien unter ${quotePath(result.extractRoot)}`);
  }

  return lines.join("\n").trim();
}

async function invokeHelper(config, request) {
  const helperBinary = readString(config.helperBinary, "python3");
  const timeoutMs = readNumber(config.extractionTimeoutMs, 120000);
  const args = [
    HELPER_SCRIPT_PATH,
    "--binary-root",
    readString(config.binaryRoot, "/var/lib/paperclip/instances/default/data/company-binaries"),
    "--max-entries",
    String(readNumber(config.maxArchiveEntries, 500)),
    "--max-total-bytes",
    String(readNumber(config.maxTotalBytes, 209715200)),
    "--max-listed-files",
    String(readNumber(config.maxListedFiles, 40)),
  ];

  if (request.issueId) {
    args.push("--issue-id", request.issueId);
  }
  if (request.commentId) {
    args.push("--comment-id", request.commentId);
  }
  if (request.attachmentId) {
    args.push("--attachment-id", request.attachmentId);
  }

  const { stdout } = await execFileAsync(helperBinary, args, {
    cwd: fileURLToPath(new URL("..", import.meta.url)),
    env: process.env,
    timeout: timeoutMs,
    maxBuffer: 10 * 1024 * 1024,
  });

  const raw = String(stdout || "").trim();
  if (!raw) {
    throw new Error("Archive helper did not return any output");
  }

  try {
    return JSON.parse(raw);
  } catch {
    throw new Error("Archive helper did not return valid JSON");
  }
}

async function maybeMoveIssueToTodo(ctx, issueId, companyId, config) {
  if (!config?.moveBacklogToTodoAfterProcessing || !issueId || !companyId) {
    return;
  }

  try {
    const issue = await ctx.issues.get(issueId, companyId);
    if (!issue || issue.status !== "backlog") {
      return;
    }

    await ctx.issues.update(issueId, { status: "todo" }, companyId);
  } catch (error) {
    ctx.logger.warn("Could not move expanded issue from backlog to todo", {
      issueId,
      companyId,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

function extractEventRefs(event) {
  const payload = event && typeof event.payload === "object" && event.payload !== null ? event.payload : {};
  const entityType = readString(event.entityType);
  const entityId = readString(event.entityId);
  const issueId = readString(payload.issueId, entityType === "issue" ? entityId : "");
  const commentId = readString(payload.commentId, entityType === "issue_comment" ? entityId : "");
  const attachmentId = readString(payload.attachmentId, entityType === "attachment" ? entityId : "");
  return { issueId, commentId, attachmentId };
}

async function maybeExpandEvent(ctx, event, sourceKind) {
  const { issueId, commentId, attachmentId } = extractEventRefs(event);
  if (!issueId && !commentId && !attachmentId) {
    ctx.logger.debug("Skipping archive event without usable refs", {
      eventType: event.eventType,
      eventId: event.eventId,
      entityType: readString(event.entityType),
      entityId: readString(event.entityId),
    });
    return;
  }

  const config = await ctx.config.get();
  const commentPrefix = readString(config.commentPrefix, DEFAULT_COMMENT_PREFIX);

  if (sourceKind === "comment" && issueId && commentId) {
    try {
      const comments = await ctx.issues.listComments(issueId, event.companyId);
      const current = comments.find((comment) => comment.id === commentId);
      if (current && isPluginComment(current.body, commentPrefix)) {
        return;
      }
    } catch (error) {
      ctx.logger.warn("Could not inspect source comment before archive expansion", {
        issueId,
        commentId,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  let payload;
  try {
    payload = await invokeHelper(config, { issueId, commentId, attachmentId });
  } catch (error) {
    ctx.logger.warn("Archive helper failed", {
      issueId,
      commentId,
      attachmentId,
      error: error instanceof Error ? error.message : String(error),
    });
    return;
  }

  const results = Array.isArray(payload?.results) ? payload.results : [];
  if (results.length === 0) {
    ctx.logger.debug("Archive helper found no matching archive attachments", {
      issueId,
      commentId,
      attachmentId,
      eventType: event.eventType,
    });
  }
  let movedIssueId = "";
  for (const result of results) {
    const issueRef = readString(result.issueId, issueId);
    const attachmentRef = readString(result.attachmentId);
    if (!issueRef || !attachmentRef) {
      continue;
    }

    const stateKey = {
      scopeKind: "issue",
      scopeId: issueRef,
      namespace: STATE_NAMESPACE,
      stateKey: `attachment:${attachmentRef}`,
    };
    const existing = await ctx.state.get(stateKey);
    if (existing) {
      continue;
    }

    const body = buildCommentBody(result, commentPrefix);
    if (!body) {
      continue;
    }

    const comment = await ctx.issues.createComment(issueRef, body, event.companyId);
    ctx.logger.info("Archive expansion comment created", {
      issueId: issueRef,
      attachmentId: attachmentRef,
      commentId: comment.id,
      reused: Boolean(result.reused),
      ok: Boolean(result.ok),
    });
    await ctx.state.set(stateKey, {
      processedAt: new Date().toISOString(),
      commentId: comment.id,
      ok: Boolean(result.ok),
      manifestPath: readString(result.manifestPath),
      extractRoot: readString(result.extractRoot),
      originalFilename: readString(result.originalFilename),
    });

    if (!movedIssueId) {
      await maybeMoveIssueToTodo(ctx, issueRef, event.companyId, config);
      movedIssueId = issueRef;
    }
  }
}

const plugin = definePlugin({
  async setup(ctx) {
    ctx.logger.info("Archive Issue Expander starting", {
      pluginId: ctx.manifest.id,
    });

    ctx.events.on("issue.created", async (event) => {
      await maybeExpandEvent(ctx, event, "issue");
    });

    ctx.events.on("issue.updated", async (event) => {
      await maybeExpandEvent(ctx, event, "issue");
    });

    ctx.events.on("issue.comment.created", async (event) => {
      await maybeExpandEvent(ctx, event, "comment");
    });
  },

  async onHealth() {
    return {
      status: "ok",
      message: "Listening for issue create/update and comment events to expand archive attachments and comment extracted local file paths.",
    };
  },

  async onValidateConfig(config) {
    const helperBinary = readString(config.helperBinary, "python3");
    if (!helperBinary) {
      return { ok: false, errors: ["helperBinary is required"] };
    }

    const timeoutMs = readNumber(config.extractionTimeoutMs, 120000);
    if (!Number.isFinite(timeoutMs) || timeoutMs < 1000) {
      return { ok: false, errors: ["extractionTimeoutMs must be a number >= 1000"] };
    }

    const maxEntries = readNumber(config.maxArchiveEntries, 500);
    if (!Number.isFinite(maxEntries) || maxEntries < 1) {
      return { ok: false, errors: ["maxArchiveEntries must be a number >= 1"] };
    }

    const maxTotalBytes = readNumber(config.maxTotalBytes, 209715200);
    if (!Number.isFinite(maxTotalBytes) || maxTotalBytes < 1024) {
      return { ok: false, errors: ["maxTotalBytes must be a number >= 1024"] };
    }

    const maxListedFiles = readNumber(config.maxListedFiles, 40);
    if (!Number.isFinite(maxListedFiles) || maxListedFiles < 1) {
      return { ok: false, errors: ["maxListedFiles must be a number >= 1"] };
    }

    return { ok: true };
  },
});

export default plugin;
runWorker(plugin, import.meta.url);
