const manifest = {
  id: "image-issue-analyzer",
  apiVersion: 1,
  version: "0.1.0",
  displayName: "Image Issue Analyzer",
  description:
    "Analyzes Markdown image embeds in issues and comments, then posts the image summary back as a text comment.",
  author: "Melchinger",
  categories: ["automation"],
  capabilities: [
    "events.subscribe",
    "issues.read",
    "issues.update",
    "issue.comments.read",
    "issue.comments.create",
    "http.outbound",
  ],
  entrypoints: {
    worker: "src/worker.js",
  },
  instanceConfigSchema: {
    type: "object",
    additionalProperties: false,
    properties: {
      analyzerBinary: {
        type: "string",
        default: "python3",
        description: "Local Python binary used to launch the analyzer script.",
      },
      analyzerUrl: {
        type: "string",
        default: "http://127.0.0.1:4015/analyze",
        description: "Legacy helper URL kept for compatibility with older installs.",
      },
      analysisTimeoutMs: {
        type: "number",
        default: 120000,
        minimum: 1000,
        description: "Timeout for one analyzer request.",
      },
      commentPrefix: {
        type: "string",
        default: "<!-- image-issue-analyzer -->",
        description: "Marker inserted into generated comments to avoid loops.",
      },
      moveBacklogToTodoAfterProcessing: {
        type: "boolean",
        default: false,
        description:
          "Moves the issue from backlog to todo after a successful analysis comment, but only when the issue is still in backlog.",
      },
    },
  },
};

export default manifest;
