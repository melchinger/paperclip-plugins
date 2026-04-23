import { jsx, jsxs, Fragment } from "react/jsx-runtime";
import { useEffect, useMemo, useState } from "react";
import { useHostContext } from "@paperclipai/plugin-sdk/ui";

var ISSUE_STATUSES = [
  "backlog",
  "todo",
  "in_progress",
  "in_review",
  "done",
  "blocked",
  "cancelled"
];
function detectDarkMode() {
  if (typeof document === "undefined") {
    return false;
  }
  var root = document.documentElement;
  if (root && root.classList.contains("dark")) {
    return true;
  }
  if (root && root.dataset && root.dataset.theme === "dark") {
    return true;
  }
  if (root && root.style && root.style.colorScheme === "dark") {
    return true;
  }
  if (typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    return true;
  }
  return false;
}
function useDarkMode() {
  var [isDark, setIsDark] = useState(function () {
    return detectDarkMode();
  });
  useEffect(function () {
    if (typeof document === "undefined") {
      return;
    }
    var root = document.documentElement;
    var update = function update() {
      setIsDark(detectDarkMode());
    };
    update();
    var observer = new MutationObserver(update);
    observer.observe(root, {
      attributes: true,
      attributeFilter: ["class", "data-theme", "style"]
    });
    var media = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
    if (media && media.addEventListener) {
      media.addEventListener("change", update);
    } else if (media && media.addListener) {
      media.addListener(update);
    }
    return function () {
      observer.disconnect();
      if (media && media.removeEventListener) {
        media.removeEventListener("change", update);
      } else if (media && media.removeListener) {
        media.removeListener(update);
      }
    };
  }, []);
  return isDark;
}
function createTheme(isDark) {
  var surface = isDark ? "#0f172a" : "#ffffff";
  var canvas = isDark ? "linear-gradient(180deg, rgba(2, 6, 23, 0.94), rgba(15, 23, 42, 0.82))" : "linear-gradient(180deg, rgba(15, 23, 42, 0.02), rgba(15, 23, 42, 0.01))";
  var cardBackground = isDark ? "rgba(15, 23, 42, 0.86)" : "white";
  var mutedCard = isDark ? "rgba(15, 23, 42, 0.7)" : "rgba(248, 250, 252, 0.9)";
  var panelBackground = isDark ? "linear-gradient(135deg, rgba(13, 148, 136, 0.16), rgba(15, 23, 42, 0.26))" : "linear-gradient(135deg, rgba(15, 118, 110, 0.1), rgba(15, 23, 42, 0.02))";
  var text = isDark ? "#e2e8f0" : "#0f172a";
  var muted = isDark ? "#94a3b8" : "#475569";
  var border = isDark ? "rgba(148, 163, 184, 0.22)" : "rgba(148, 163, 184, 0.35)";
  var fieldBorder = isDark ? "rgba(148, 163, 184, 0.24)" : "rgba(15, 23, 42, 0.14)";
  var fieldBackground = isDark ? "rgba(2, 6, 23, 0.72)" : "white";
  var fieldColor = isDark ? "#e2e8f0" : "#0f172a";
  var buttonBackground = isDark ? "rgba(15, 23, 42, 0.9)" : "white";
  var buttonBorder = isDark ? "rgba(148, 163, 184, 0.24)" : "rgba(15, 23, 42, 0.15)";
  var buttonMutedBackground = isDark ? "rgba(148, 163, 184, 0.08)" : "rgba(15, 23, 42, 0.03)";
  var primaryBackground = isDark ? "#f8fafc" : "#0f172a";
  var primaryColor = isDark ? "#0f172a" : "#ffffff";
  var badgeBackground = isDark ? "rgba(20, 184, 166, 0.14)" : "rgba(15, 118, 110, 0.08)";
  var badgeBorder = isDark ? "rgba(45, 212, 191, 0.22)" : "rgba(15, 118, 110, 0.18)";
  var badgeColor = isDark ? "#5eead4" : "#0f766e";
  var dangerBackground = isDark ? "rgba(248, 113, 113, 0.12)" : "rgba(185, 28, 28, 0.08)";
  var dangerBorder = isDark ? "rgba(248, 113, 113, 0.2)" : "rgba(185, 28, 28, 0.18)";
  var dangerColor = isDark ? "#fca5a5" : "#b91c1c";
  return {
    shell: {
      display: "grid",
      gap: "1rem",
      padding: "1rem",
      color: text,
      background: canvas
    },
    card: {
      border: "1px solid " + border,
      borderRadius: "14px",
      padding: "1rem",
      display: "grid",
      gap: "0.75rem",
      background: cardBackground,
      boxShadow: isDark ? "0 12px 32px rgba(2, 6, 23, 0.34)" : "0 1px 0 rgba(15, 23, 42, 0.03)"
    },
    hero: {
      border: "1px solid " + border,
      borderRadius: "14px",
      padding: "1rem",
      display: "grid",
      gap: "0.75rem",
      background: panelBackground,
      boxShadow: isDark ? "0 12px 32px rgba(2, 6, 23, 0.22)" : "0 1px 0 rgba(15, 23, 42, 0.03)"
    },
    row: {
      display: "grid",
      gap: "0.35rem"
    },
    label: {
      fontSize: "0.9rem",
      fontWeight: 600,
      color: text
    },
    input: {
      width: "100%",
      border: "1px solid " + fieldBorder,
      borderRadius: "10px",
      padding: "0.7rem 0.8rem",
      fontSize: "0.94rem",
      background: fieldBackground,
      color: fieldColor,
      WebkitTextFillColor: fieldColor
    },
    select: {
      width: "100%",
      border: "1px solid " + fieldBorder,
      borderRadius: "10px",
      padding: "0.7rem 0.8rem",
      fontSize: "0.94rem",
      background: fieldBackground,
      color: fieldColor,
      WebkitTextFillColor: fieldColor,
      appearance: "none"
    },
    button: {
      width: "fit-content",
      border: "1px solid " + buttonBorder,
      borderRadius: "999px",
      padding: "0.55rem 0.95rem",
      background: buttonBackground,
      color: text,
      cursor: "pointer"
    },
    primaryButton: {
      width: "fit-content",
      border: "1px solid " + buttonBorder,
      borderRadius: "999px",
      padding: "0.55rem 0.95rem",
      background: primaryBackground,
      color: primaryColor,
      cursor: "pointer"
    },
    secondaryButton: {
      width: "fit-content",
      border: "1px solid " + buttonBorder,
      borderRadius: "999px",
      padding: "0.55rem 0.95rem",
      background: buttonMutedBackground,
      color: text,
      cursor: "pointer"
    },
    badge: {
      display: "inline-flex",
      alignItems: "center",
      gap: "0.4rem",
      borderRadius: "999px",
      padding: "0.25rem 0.65rem",
      fontSize: "0.82rem",
      border: "1px solid " + badgeBorder,
      background: badgeBackground,
      color: badgeColor
    },
    dangerBadge: {
      display: "inline-flex",
      alignItems: "center",
      gap: "0.4rem",
      borderRadius: "999px",
      padding: "0.25rem 0.65rem",
      fontSize: "0.82rem",
      border: "1px solid " + dangerBorder,
      background: dangerBackground,
      color: dangerColor
    },
    summaryCard: {
      border: "1px solid " + border,
      borderRadius: "12px",
      padding: "0.75rem",
      display: "grid",
      gap: "0.2rem",
      background: mutedCard
    },
    mutedText: muted,
    codeBackground: isDark ? "rgba(15, 23, 42, 0.75)" : "rgba(15, 23, 42, 0.04)",
    codeColor: isDark ? "#cbd5e1" : "#0f172a"
  };
}
function formatDateInputValue(date) {
  var copy = new Date(date);
  var offsetMs = copy.getTimezoneOffset() * 60 * 1000;
  return new Date(copy.getTime() - offsetMs).toISOString().slice(0, 10);
}
function formatArchiveCount(value) {
  return new Intl.NumberFormat("de-DE").format(value);
}
function normalizeIssueLabel(issue) {
  if (!issue) {
    return "Unknown issue";
  }
  if (typeof issue.identifier === "string" && issue.identifier.trim().length > 0) {
    return issue.identifier.trim();
  }
  if (typeof issue.issueNumber === "number") {
    return `#${issue.issueNumber}`;
  }
  if (typeof issue.title === "string" && issue.title.trim().length > 0) {
    return issue.title.trim();
  }
  return "Unknown issue";
}
async function fetchArchivePayload(payload) {
  var response = await fetch("/session-api/v1/issues/archive", {
    method: "POST",
    credentials: "include",
    headers: {
      "content-type": "application/json"
    },
    body: JSON.stringify(payload)
  });
  var contentType = response.headers.get("content-type") || "";
  var body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    var message = typeof body === "string" ? body : body?.error || `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return body;
}
function IssueSummaryList({ issues, theme }) {
  if (!issues || issues.length === 0) {
    return /* @__PURE__ */ jsx("div", { style: { color: theme.mutedText, fontSize: "0.92rem" }, children: "No matching issues." });
  }
  return /* @__PURE__ */ jsx("div", {
    style: { display: "grid", gap: "0.5rem" },
    children: issues.slice(0, 8).map((issue) => /* @__PURE__ */ jsxs(
      "div",
      {
        style: theme.summaryCard,
        children: [
          /* @__PURE__ */ jsxs("div", {
            style: { display: "flex", justifyContent: "space-between", gap: "0.75rem", flexWrap: "wrap" },
            children: [
              /* @__PURE__ */ jsx("strong", { children: normalizeIssueLabel(issue) }),
              /* @__PURE__ */ jsx("span", { style: theme.badge, children: issue.status || "unknown" })
            ]
          }),
          /* @__PURE__ */ jsx("div", { style: { color: theme.mutedText, fontSize: "0.86rem" }, children: issue.title || "Untitled issue" })
        ]
      },
      issue.id || normalizeIssueLabel(issue)
    ))
  });
}
function ResultCard({ title, result, theme, tone = "normal" }) {
  if (!result) {
    return null;
  }
  var badgeTone = tone === "danger" ? theme.dangerBadge : theme.badge;
  return /* @__PURE__ */ jsxs("div", { style: theme.card, children: [
    /* @__PURE__ */ jsx("div", { style: { fontSize: "1rem", fontWeight: 700 }, children: title }),
    /* @__PURE__ */ jsxs("div", { style: { display: "flex", gap: "0.5rem", flexWrap: "wrap" }, children: [
      /* @__PURE__ */ jsxs("span", { style: badgeTone, children: [
        "Matched: ",
        formatArchiveCount(result.matchedCount ?? 0)
      ] }),
      /* @__PURE__ */ jsxs("span", { style: badgeTone, children: [
        "Archived: ",
        formatArchiveCount(result.archivedCount ?? 0)
      ] }),
      /* @__PURE__ */ jsx("span", { style: badgeTone, children: result.dryRun ? "Preview only" : "Applied" })
    ] }),
    /* @__PURE__ */ jsx(IssueSummaryList, { issues: result.issues ?? [], theme })
  ] });
}
function PaperclipIssueArchiverDrawer() {
  var context = useHostContext();
  var companyId = context.companyId || null;
  var companyPrefix = context.companyPrefix || "company";
  var isDark = useDarkMode();
  var theme = useMemo(function () {
    return createTheme(isDark);
  }, [isDark]);
  var [status, setStatus] = useState("done");
  var [before, setBefore] = useState(function () {
    return formatDateInputValue(new Date());
  });
  var [loading, setLoading] = useState(false);
  var [error, setError] = useState("");
  var [preview, setPreview] = useState(null);
  var [lastArchive, setLastArchive] = useState(null);
  var previewLabel = useMemo(function () {
    return companyId ? `Company ${companyPrefix}` : "No company context";
  }, [companyId, companyPrefix]);
  async function runArchive(dryRun) {
    if (!companyId) {
      setError("No active company context available.");
      return;
    }
    if (!before) {
      setError("Pick a cutoff date first.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      var result = await fetchArchivePayload({
        companyId,
        status,
        before,
        dryRun
      });
      if (dryRun) {
        setPreview(result);
      } else {
        setPreview(null);
        setLastArchive(result);
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setLoading(false);
    }
  }
  return /* @__PURE__ */ jsxs("div", { style: theme.shell, children: [
    /* @__PURE__ */ jsxs("div", { style: theme.hero, children: [
      /* @__PURE__ */ jsx("div", { style: { fontSize: "1.32rem", fontWeight: 800, letterSpacing: "-0.02em" }, children: "Paperclip Issue Archiver" }),
      /* @__PURE__ */ jsx("div", { style: { color: theme.mutedText, maxWidth: "70ch", lineHeight: 1.5 }, children: "Preview old issues and archive every issue with the selected status that was created before the cutoff date. The action is a soft archive and sets hiddenAt." }),
      /* @__PURE__ */ jsx("div", { style: { display: "flex", gap: "0.5rem", flexWrap: "wrap" }, children: companyId ? /* @__PURE__ */ jsxs("span", { style: theme.badge, children: [
        "Company context: ",
        previewLabel
      ] }) : /* @__PURE__ */ jsx("span", { style: theme.dangerBadge, children: "No company context available" }) })
    ] }),
    /* @__PURE__ */ jsxs("div", { style: theme.card, children: [
      /* @__PURE__ */ jsxs("div", { style: theme.row, children: [
        /* @__PURE__ */ jsx("div", { style: theme.label, children: "Issue status" }),
        /* @__PURE__ */ jsx("select", { value: status, onChange: (event) => setStatus(event.target.value), style: theme.select, children: ISSUE_STATUSES.map(function (value) {
          return /* @__PURE__ */ jsx("option", { value, children: value }, value);
        }) })
      ] }),
      /* @__PURE__ */ jsxs("div", { style: theme.row, children: [
        /* @__PURE__ */ jsx("div", { style: theme.label, children: "Cutoff date" }),
        /* @__PURE__ */ jsx("input", { type: "date", value: before, onChange: (event) => setBefore(event.target.value), style: theme.input })
      ] }),
      /* @__PURE__ */ jsxs("div", { style: { display: "flex", gap: "0.65rem", flexWrap: "wrap" }, children: [
        /* @__PURE__ */ jsx("button", { type: "button", onClick: () => void runArchive(true), disabled: loading || !companyId, style: theme.secondaryButton, children: loading ? "Working..." : "Preview" }),
        /* @__PURE__ */ jsx("button", { type: "button", onClick: () => void runArchive(false), disabled: loading || !companyId, style: theme.primaryButton, children: loading ? "Working..." : "Archive" })
      ] }),
      error ? /* @__PURE__ */ jsx("div", { style: theme.dangerBadge, children: error }) : null
    ] }),
    preview ? /* @__PURE__ */ jsx(ResultCard, { title: "Preview results", result: preview, theme }) : lastArchive ? /* @__PURE__ */ jsx(ResultCard, { title: "Archive applied", result: lastArchive, theme }) : null,
    /* @__PURE__ */ jsxs("div", { style: { color: theme.mutedText, fontSize: "0.84rem", lineHeight: 1.45 }, children: [
      "The archive endpoint is ",
      /* @__PURE__ */ jsx("code", { style: { background: theme.codeBackground, color: theme.codeColor, borderRadius: "6px", padding: "0.1rem 0.35rem" }, children: "/v1/issues/archive" }),
      " and accepts ",
      /* @__PURE__ */ jsx("code", { style: { background: theme.codeBackground, color: theme.codeColor, borderRadius: "6px", padding: "0.1rem 0.35rem" }, children: "dryRun" }),
      " for preview-only runs."
    ] })
  ] });
}
export {
  PaperclipIssueArchiverDrawer
};
