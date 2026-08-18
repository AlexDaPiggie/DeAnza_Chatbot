/**
 * DOM Manipulation & UI Controller Module
 */
import { formatMarkdown } from "./config.js";

/**
 * Appends a new message bubble to the chat container.
 */
export function appendMessage(container, role, initialText = "") {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const msg = document.createElement("div");
  msg.className = `msg ${role}`;

  if (role === "user") {
    msg.textContent = initialText;
  } else {
    msg.innerHTML = formatMarkdown(initialText);
  }

  row.appendChild(msg);
  container.appendChild(row);
  scrollToBottom(container);
  return msg;
}

/**
 * Updates a bot message container with streaming markdown.
 */
export function updateBotMessage(msgElement, rawText) {
  if (!msgElement) return;
  msgElement.innerHTML = formatMarkdown(rawText);
}

/**
 * Smoothly scrolls chat container to bottom.
 */
export function scrollToBottom(container) {
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}

/**
 * Dynamically resizes textarea up to a ratio of viewport height.
 */
export function autoResizeTextarea(textarea, maxHeightRatio = 0.25) {
  if (!textarea) return;
  textarea.style.height = "auto";
  const maxHeight = window.innerHeight * maxHeightRatio;
  const targetHeight = Math.min(Math.max(textarea.scrollHeight, 44), maxHeight);
  textarea.style.height = `${targetHeight}px`;
}

/**
 * Sets submit button enabled/disabled state.
 */
export function setLoadingState(sendBtn, isLoading) {
  if (sendBtn) {
    sendBtn.disabled = isLoading;
  }
}

/**
 * Switches active view between Chat and Authors without reloading page.
 */
export function switchView(targetViewId) {
  const allViews = document.querySelectorAll(".page-view");
  const allNavBtns = document.querySelectorAll(".nav-btn");

  allViews.forEach((view) => {
    if (view.id === targetViewId) {
      view.classList.remove("hidden");
    } else {
      view.classList.add("hidden");
    }
  });

  allNavBtns.forEach((btn) => {
    if (btn.dataset.view === targetViewId) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });
}
