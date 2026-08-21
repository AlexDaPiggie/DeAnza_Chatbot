// Chat screen wiring: view changes, theme state, prompt clicks, and requests.
import { streamChat } from "./api.js";
import {
  appendMessage,
  updateBotMessage,
  autoResizeTextarea,
  scrollToBottom,
  setLoadingState,
  switchView
} from "./ui.js";

const chatContainer = document.getElementById("chat-container");
const scrollContainer = document.querySelector(".content-shell");
const inputForm = document.getElementById("input-form");
const inputBox = document.getElementById("input-box");
const sendBtn = document.getElementById("send-btn");
const navBtns = document.querySelectorAll(".nav-btn");
const promptBtns = document.querySelectorAll("[data-prompt]");
const modeTabs = document.querySelectorAll(".mode-tab");
const welcomePanel = document.querySelector(".welcome-panel");
const brandHome = document.getElementById("brand-home");
const themeToggles = document.querySelectorAll(".theme-switch");
const themeIcons = document.querySelectorAll(".theme-icon");
const typingHeadline = document.querySelector(".typing-headline");
const typingText = typingHeadline?.querySelector(".typing-text");
const sideRail = document.querySelector(".side-rail");
const scrollTopBtn = document.getElementById("scroll-top-btn");
const mobileMenuOpen = document.getElementById("mobile-menu-open");
const mobileMenuClose = document.getElementById("mobile-menu-close");
const mobileMenuBackdrop = document.getElementById("mobile-menu-backdrop");

const state = {
  history: [],
  abortController: null,
  hasStartedChat: false,
  isStreaming: false,
  activeBotMessage: null
};

function getInitialTheme() {
  const savedTheme = localStorage.getItem("anza-theme");
  if (savedTheme === "dark" || savedTheme === "light") return savedTheme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme) {
  document.body.dataset.theme = theme;
  const isDark = theme === "dark";
  themeToggles.forEach((toggle) => {
    toggle.setAttribute("aria-checked", String(isDark));
    toggle.setAttribute("aria-label", isDark ? "Switch to day mode" : "Switch to night mode");
  });
  themeIcons.forEach((icon) => {
    icon.textContent = isDark ? "☀" : "☾";
  });
}

applyTheme(getInitialTheme());

function startTypingHeadline() {
  if (!typingHeadline || !typingText) return;

  const text = typingHeadline.dataset.text || "Start with a question.";
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (reduceMotion) {
    typingText.textContent = text;
    return;
  }

  let index = 0;
  let isDeleting = false;

  function tick() {
    typingText.textContent = text.slice(0, index);

    if (!isDeleting && index < text.length) {
      index += 1;
      window.setTimeout(tick, 72);
      return;
    }

    if (!isDeleting) {
      isDeleting = true;
      window.setTimeout(tick, 4000);
      return;
    }

    if (index > 0) {
      index -= 1;
      window.setTimeout(tick, 42);
      return;
    }

    isDeleting = false;
    window.setTimeout(tick, 520);
  }

  tick();
}

startTypingHeadline();

themeToggles.forEach((toggle) => {
  toggle.addEventListener("click", () => {
    const nextTheme = document.body.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("anza-theme", nextTheme);
    applyTheme(nextTheme);
  });
});

function initMobileNavScroll() {
  return;
}

initMobileNavScroll();

function isMobileMenuLayout() {
  return window.matchMedia("(max-width: 900px)").matches;
}

function openMobileMenu() {
  if (!isMobileMenuLayout()) return;
  document.body.classList.add("mobile-menu-open");
}

function closeMobileMenu() {
  document.body.classList.remove("mobile-menu-open");
}

mobileMenuOpen?.addEventListener("click", openMobileMenu);
mobileMenuClose?.addEventListener("click", closeMobileMenu);
mobileMenuBackdrop?.addEventListener("click", closeMobileMenu);
window.addEventListener("resize", () => {
  if (!isMobileMenuLayout()) closeMobileMenu();
});

function initScrollTopButton() {
  if (!scrollContainer || !scrollTopBtn) return;

  scrollContainer.addEventListener("scroll", () => {
    scrollTopBtn.classList.toggle("visible", scrollContainer.scrollTop > 360);
  }, { passive: true });

  scrollTopBtn.addEventListener("click", () => {
    scrollContainer.scrollTo({ top: 0, behavior: "smooth" });
  });
}

initScrollTopButton();

function getModePlaceholder(tab) {
  const isMobile = window.matchMedia("(max-width: 640px)").matches;
  return isMobile && tab.dataset.mobilePlaceholder
    ? tab.dataset.mobilePlaceholder
    : tab.dataset.placeholder;
}

function syncActiveModePlaceholder() {
  if (!inputBox) return;
  const activeTab = document.querySelector(".mode-tab.active");
  const placeholder = activeTab ? getModePlaceholder(activeTab) : "";
  if (placeholder) inputBox.placeholder = placeholder;
}

syncActiveModePlaceholder();
window.addEventListener("resize", syncActiveModePlaceholder);

function submitPrompt(text) {
  if (!inputBox || !inputForm) return;
  if (state.isStreaming) {
    inputBox.focus();
    return;
  }
  switchView("chat-view");
  inputBox.value = text;
  autoResizeTextarea(inputBox);
  inputForm.requestSubmit();
}

function markChatStarted() {
  if (state.hasStartedChat) return;
  state.hasStartedChat = true;
  if (welcomePanel) {
    welcomePanel.classList.add("welcome-panel-hidden");
  }
}

function setPromptButtonsDisabled(isDisabled) {
  promptBtns.forEach((btn) => {
    btn.disabled = isDisabled;
    btn.setAttribute("aria-disabled", String(isDisabled));
  });
}

function removeStopButton(botMsgElement = state.activeBotMessage) {
  const row = botMsgElement?.parentElement;
  row?.querySelector(".stop-response-btn")?.remove();
  row?.classList.remove("is-loading");
}

function stopActiveResponse() {
  if (!state.isStreaming) return;

  const activeMessage = state.activeBotMessage;
  state.abortController?.abort();
  state.abortController = null;
  state.isStreaming = false;
  state.activeBotMessage = null;

  removeStopButton(activeMessage);
  setLoadingState(sendBtn, false);
  setPromptButtonsDisabled(false);

  if (activeMessage?.textContent.includes("Searching official De Anza sources")) {
    updateBotMessage(activeMessage, "Stopped.");
  }

  inputBox.focus();
}

function attachStopButton(botMsgElement) {
  const row = botMsgElement?.parentElement;
  if (!row || row.querySelector(".stop-response-btn")) return;

  row.classList.add("is-loading");

  const stopBtn = document.createElement("button");
  stopBtn.type = "button";
  stopBtn.className = "stop-response-btn";
  stopBtn.innerHTML = '<span aria-hidden="true">■</span>';
  stopBtn.setAttribute("aria-label", "Stop response");
  stopBtn.addEventListener("click", stopActiveResponse);

  row.appendChild(stopBtn);
}

navBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    const targetView = btn.dataset.view;
    switchView(targetView);
    closeMobileMenu();
    if (targetView === "chat-view" && inputBox) {
      inputBox.focus();
    }
  });
});

brandHome?.addEventListener("click", () => {
  if (isMobileMenuLayout()) {
    switchView("chat-view");
    closeMobileMenu();
    return;
  }
  switchView("chat-view");
  if (scrollContainer) scrollContainer.scrollTop = 0;
  if (inputBox) inputBox.focus();
});

promptBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    const prompt = btn.dataset.prompt;
    closeMobileMenu();
    if (prompt) submitPrompt(prompt);
  });
});

modeTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    modeTabs.forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    const placeholder = getModePlaceholder(tab);
    if (inputBox && placeholder) {
      inputBox.placeholder = placeholder;
      inputBox.focus();
    }
  });
});

window.askQuestion = submitPrompt;

inputBox.addEventListener("input", () => {
  autoResizeTextarea(inputBox);
});

inputBox.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    inputForm.requestSubmit();
  }
});

inputForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  if (state.isStreaming) {
    inputBox.focus();
    return;
  }

  const query = inputBox.value.trim();
  if (!query) return;

  if (state.abortController) {
    state.abortController.abort();
  }
  state.abortController = new AbortController();

  markChatStarted();
  appendMessage(chatContainer, "user", query);
  scrollToBottom(scrollContainer);
  inputBox.value = "";
  inputBox.style.height = "44px";
  state.isStreaming = true;
  setPromptButtonsDisabled(true);
  setLoadingState(sendBtn, true);

  const botMsgElement = appendMessage(chatContainer, "bot", "__THINKING__");
  state.activeBotMessage = botMsgElement;
  scrollToBottom(scrollContainer);
  let fullResponse = "";

  await streamChat({
    message: query,
    history: state.history,
    signal: state.abortController.signal,
    onToken: (token) => {
      fullResponse += token;
      updateBotMessage(botMsgElement, fullResponse);
      scrollToBottom(scrollContainer);
    },
    onDone: () => {
      removeStopButton(botMsgElement);
      if (fullResponse.trim()) {
        state.history.push({ role: "user", content: query });
        state.history.push({ role: "assistant", content: fullResponse });
      }
      state.isStreaming = false;
      state.activeBotMessage = null;
      setLoadingState(sendBtn, false);
      setPromptButtonsDisabled(false);
      state.abortController = null;
      inputBox.focus();
    },
    onError: (err) => {
      removeStopButton(botMsgElement);
      updateBotMessage(botMsgElement, "Sorry, I hit a connection issue while reaching the assistant. Please try again.");
      console.error("Chat Error:", err);
      state.isStreaming = false;
      state.activeBotMessage = null;
      setLoadingState(sendBtn, false);
      setPromptButtonsDisabled(false);
      state.abortController = null;
      inputBox.focus();
    }
  });
});
