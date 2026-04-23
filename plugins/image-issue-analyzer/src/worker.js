import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { definePlugin, runWorker } from "@paperclipai/plugin-sdk";

const DEFAULT_COMMENT_PREFIX = "<!-- image-issue-analyzer -->";
const COMMENT_TITLE = "Automatische Bildanalyse";
const execFileAsync = promisify(execFile);
const ANALYZE_SCRIPT_PATH = fileURLToPath(new URL("../scripts/analyze_issue_image.py", import.meta.url));

function readString(value, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function isAnalysisComment(body, prefix) {
  return typeof body === "string" && body.includes(prefix);
}

function buildCommentBody(result, prefix) {
  const lines = [prefix, "", `**${COMMENT_TITLE}**`];

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

  if (result.imagePath) {
    lines.push(`- Datei: \`${String(result.imagePath).replaceAll("`", "\\`")}\``);
  }

  const analysisText = String(result.analysis || result.analyzerOutput || "").trim();
  if (!analysisText) {
    return "";
  }

  lines.push("");
  lines.push(analysisText);
  return lines.join("\n").trim();
}

async function invokeAnalyzer(ctx, config, request) {
  const analyzerBinary = readString(config.analyzerBinary, "python3");
  const timeoutMs = Number(config.analysisTimeoutMs ?? 120000);
  const args = [ANALYZE_SCRIPT_PATH];
  if (request.commentId) {
    args.push("--comment-id", request.commentId);
  } else if (request.issueId) {
    args.push("--issue-id", request.issueId);
  }

  const { stdout } = await execFileAsync(analyzerBinary, args, {
    cwd: fileURLToPath(new URL("..", import.meta.url)),
    env: process.env,
    timeout: Number.isFinite(timeoutMs) ? timeoutMs : 120000,
    maxBuffer: 10 * 1024 * 1024,
  });

  const raw = String(stdout || "").trim();
  if (!raw) {
    throw new Error("Analyzer did not return any output");
  }

  try {
    return JSON.parse(raw);
  } catch {
    throw new Error("Analyzer did not return valid JSON");
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
    ctx.logger.warn("Could not move analyzed issue from backlog to todo", {
      issueId,
      companyId,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

async function maybeAnalyzeEvent(ctx, event, sourceKind) {
  const payload = event && typeof event.payload === "object" && event.payload !== null ? event.payload : {};
  const issueId = readString(payload.issueId, readString(event.entityId));
  const commentId = sourceKind === "comment" ? readString(payload.commentId, readString(event.entityId)) : "";

  if (!issueId) {
    ctx.logger.debug("Skipping image analysis event without issue id", {
      eventType: event.eventType,
      eventId: event.eventId,
    });
    return;
  }

  const config = await ctx.config.get();
  const commentPrefix = readString(config.commentPrefix, DEFAULT_COMMENT_PREFIX);

  if (sourceKind === "comment" && commentId) {
    try {
      const comments = await ctx.issues.listComments(issueId, event.companyId);
      const current = comments.find((comment) => comment.id === commentId);
      if (current && isAnalysisComment(current.body, commentPrefix)) {
        return;
      }
    } catch (error) {
      ctx.logger.warn("Could not inspect source comment before analysis", {
        issueId,
        commentId,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  const request = {
    issueId,
    companyId: event.companyId,
    commentId: commentId || undefined,
  };

  let result;
  try {
    result = await invokeAnalyzer(ctx, config, request);
  } catch (error) {
    ctx.logger.warn("Image analysis helper failed", {
      issueId,
      commentId: commentId || undefined,
      error: error instanceof Error ? error.message : String(error),
    });
    return;
  }

  if (!result || result.found === false) {
    ctx.logger.debug("No image embed found for event", {
      issueId,
      commentId: commentId || undefined,
    });
    return;
  }

  const body = buildCommentBody(result, commentPrefix);
  if (!body) {
    return;
  }

  await ctx.issues.createComment(issueId, body, event.companyId);
  await maybeMoveIssueToTodo(ctx, issueId, event.companyId, config);
}

const plugin = definePlugin({
  async setup(ctx) {
    ctx.logger.info("Image Issue Analyzer starting", {
      pluginId: ctx.manifest.id,
    });

    ctx.events.on("issue.created", async (event) => {
      await maybeAnalyzeEvent(ctx, event, "issue");
    });

    ctx.events.on("issue.comment_added", async (event) => {
      await maybeAnalyzeEvent(ctx, event, "comment");
    });

    ctx.events.on("issue.comment.created", async (event) => {
      await maybeAnalyzeEvent(ctx, event, "comment");
    });
  },

  async onHealth() {
    return {
      status: "ok",
      message: "Listening for issue and comment image embeds.",
    };
  },

  async onValidateConfig(config) {
    const analyzerBinary = readString(config.analyzerBinary, "python3");
    if (!analyzerBinary) {
      return { ok: false, errors: ["analyzerBinary is required"] };
    }

    const timeoutMs = Number(config.analysisTimeoutMs ?? 120000);
    if (!Number.isFinite(timeoutMs) || timeoutMs < 1000) {
      return { ok: false, errors: ["analysisTimeoutMs must be a number >= 1000"] };
    }

    return { ok: true };
  },
});

export default plugin;
runWorker(plugin, import.meta.url);
