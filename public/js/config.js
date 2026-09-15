// Shared frontend config and markdown helpers.

const RENDER_API_ORIGIN = "https://deanza-chatbot.onrender.com";
const VERCEL_HOST_SUFFIX = ".vercel.app";

function getApiOrigin() {
  const { hostname, port } = window.location;

  if (hostname.endsWith(VERCEL_HOST_SUFFIX)) return RENDER_API_ORIGIN;
  if ((hostname === "localhost" || hostname === "127.0.0.1") && port !== "8000") {
    return RENDER_API_ORIGIN;
  }

  return "";
}

const API_ORIGIN = getApiOrigin();

export const API_ENDPOINTS = {
  CHAT: `${API_ORIGIN}/api/chat`,
};

function escapeHtml(value = "") {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function normalizeUrl(href = "") {
  let url = String(href).trim();

  // Rewrite legacy MyPortal links to official Ellucian portal
  if (/myportal\.deanza\.edu/i.test(url)) {
    return "https://experience.elluciancloud.com/fdaccdso/";
  }

  // Rewrite broken funding-dates hallucination to financialaid homepage
  if (/deanza\.edu\/financialaid\/funding-dates/i.test(url)) {
    return "https://www.deanza.edu/financialaid/";
  }

  return url;
}

function safeHref(href = "") {
  const value = normalizeUrl(href);

  // Validate allowed protocols
  if (/^mailto:/i.test(value)) return escapeHtml(value);
  if (!/^https?:\/\//i.test(value)) return "#";

  // Allowed official domains
  const isAllowedDomain = /^(https?:\/\/)?([a-zA-Z0-9.-]+\.)?(deanza\.edu|fhda\.edu|elluciancloud\.com|elumenapp\.com|assist\.org|studentforms\.com|studentaid\.gov|fafsa\.gov|csac\.ca\.gov|cccco\.edu)/i.test(value);
  if (!isAllowedDomain) {
    return "#";
  }

  return escapeHtml(value);
}

// Keep links safe when markdown comes back from the chatbot.
if (window.marked) {
  window.marked.use({
    renderer: {
      link(token, titleArg, textArg) {
        const href = typeof token === "object" && token !== null ? token.href : token;
        const title = typeof token === "object" && token !== null ? token.title : titleArg;
        const text = typeof token === "object" && token !== null ? token.text : textArg;
        const finalUrl = safeHref(href);

        // If unverified URL stripped to "#", render clean text without broken link
        if (finalUrl === "#") {
          return escapeHtml(text);
        }

        const titleAttr = title ? ` title="${escapeHtml(title)}"` : "";
        return `<a href="${finalUrl}"${titleAttr} target="_blank" rel="noopener noreferrer">${escapeHtml(text)}</a>`;
      }
    }
  });
}

// Streaming chunks can glue headings/lists together, so clean that up before
// passing the text to marked.
export function formatMarkdown(rawText) {
  if (!rawText) return "";

  const clean = escapeHtml(rawText)
    // Put headers back on their own block.
    .replace(/(?:[^\n]|^)\s*(#{1,6}\s+)/g, "\n\n$1")
    // Split attached header descriptions.
    .replace(/(#{1,4}\s+[A-Za-z0-9\s/\\-]+?):\s+([A-Za-z])/g, "$1\n$2")
    // Separate bullet lists that arrive glued to the previous sentence on the same line.
    .replace(/:(?![ \t]*\n)[ \t]*[\*\-][ \t]+/g, ":\n\n* ")
    // Same idea, but for bullets after sentence punctuation on the same line.
    .replace(/([.!?])(?![ \t]*\n)[ \t]+[\*\-][ \t]+/g, "$1\n\n* ")
    // Avoid huge gaps after normalization.
    .replace(/\n{3,}/g, "\n\n");

  return window.marked ? window.marked.parse(clean.trim()) : clean;
}
