const manifest = {
  id: "zip-issue-expander",
  apiVersion: 1,
  version: "0.1.0",
  displayName: "Archive Issue Expander",
  description:
    "Expands archive attachments into company-scoped binary directories and comments stable local file paths back onto issues.",
  author: "Melchinger",
  categories: ["automation"],
  capabilities: [
    "events.subscribe",
    "issues.read",
    "issues.update",
    "issue.comments.read",
    "issue.comments.create",
    "plugin.state.read",
    "plugin.state.write",
  ],
  entrypoints: {
    worker: "src/worker.js",
  },
  instanceConfigSchema: {
    type: "object",
    additionalProperties: false,
    properties: {
      helperBinary: {
        type: "string",
        default: "python3",
        description: "Local Python binary used to launch the archive helper script.",
      },
      extractionTimeoutMs: {
        type: "number",
        default: 120000,
        minimum: 1000,
        description: "Timeout for one archive expansion request.",
      },
      commentPrefix: {
        type: "string",
        default: "<!-- zip-issue-expander -->",
        description: "Marker inserted into generated comments to avoid loops.",
      },
      binaryRoot: {
        type: "string",
        default: "/var/lib/paperclip/instances/default/data/company-binaries",
        description: "Root directory where extracted archives are persisted per company.",
      },
      maxArchiveEntries: {
        type: "number",
        default: 500,
        minimum: 1,
        description: "Maximum extracted file entries per archive.",
      },
      maxTotalBytes: {
        type: "number",
        default: 209715200,
        minimum: 1024,
        description: "Maximum total uncompressed bytes per archive.",
      },
      maxListedFiles: {
        type: "number",
        default: 40,
        minimum: 1,
        description: "Maximum number of file paths written back into the issue comment.",
      },
      moveBacklogToTodoAfterProcessing: {
        type: "boolean",
        default: false,
        description:
          "Moves the issue from backlog to todo after a successful archive expansion comment, but only when the issue is still in backlog.",
      },
    },
  },
};

export default manifest;
