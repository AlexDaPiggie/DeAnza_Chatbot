/**
 * Configuration & Markdown Setup Module
 */

export const API_ENDPOINTS = {
  CHAT: "/api/chat",
  FEEDBACK: "/api/feedback",
};

// Configure marked to render secure external links in a new tab
if (window.marked) {
  window.marked.use({
    renderer: {
      link(token, titleArg, textArg) {
        const href = typeof token === "object" && token !== null ? token.href : token;
        const title = typeof token === "object" && token !== null ? token.title : titleArg;
        const text = typeof token === "object" && token !== null ? token.text : textArg;
        const titleAttr = title ? ` title="${title}"` : "";
        return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`;
      }
    }
  });
}

/**
 * Normalizes streaming markdown text and compiles to HTML.
 */
export function formatMarkdown(rawText) {
  if (!rawText) return "";

  const clean = rawText
    // Force double newlines before headers (#, ##, ###)
    .replace(/(?:[^\n]|^)\s*(#{1,6}\s+)/g, "\n\n$1")
    // Split attached inline descriptions from headers (### Title: Description -> ### Title\nDescription)
    .replace(/(#{1,4}\s+[A-Za-z0-9\s/\\-]+?):\s+([A-Za-z])/g, "$1\n$2")
    // Force double newlines before glued bullet lists (including:* -> including:\n\n* )
    .replace(/:\s*\*\s*/g, ":\n\n* ")
    // Force newline before bullet items following punctuation
    .replace(/([.!?])\s*\*\s+/g, "$1\n\n* ")
    // Collapse excessive blank lines
    .replace(/\n{3,}/g, "\n\n");

  return window.marked ? window.marked.parse(clean.trim()) : clean;
}
