var manifest = {
  id: "melchinger.paperclip-issue-archiver",
  apiVersion: 1,
  version: "0.1.0",
  displayName: "Paperclip Issue Archiver",
  description: "Archive old Paperclip issues by status and cutoff date.",
  author: "Melchinger",
  categories: ["automation", "ui"],
  capabilities: ["ui.action.register"],
  entrypoints: {
    worker: "./dist/worker-bootstrap.js",
    ui: "./dist/ui"
  },
  ui: {
    launchers: [
      {
        id: "paperclip-issue-archiver-launcher",
        displayName: "Archive Issues",
        description: "Open a compact drawer to preview and archive old issues.",
        placementZone: "globalToolbarButton",
        action: {
          type: "openDrawer",
          target: "PaperclipIssueArchiverDrawer"
        },
        render: {
          environment: "hostOverlay",
          bounds: "wide"
        }
      }
    ]
  }
};
var manifest_default = manifest;
export {
  manifest as manifest,
  manifest_default as default
};
