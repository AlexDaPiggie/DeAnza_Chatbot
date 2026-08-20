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
const inputForm = document.getElementById("input-form");
const inputBox = document.getElementById("input-box");
const sendBtn = document.getElementById("send-btn");
const navBtns = document.querySelectorAll(".nav-btn");
const promptBtns = document.querySelectorAll("[data-prompt]");
const modeTabs = document.querySelectorAll(".mode-tab");
const welcomePanel = document.querySelector(".welcome-panel");
const brandHome = document.getElementById("brand-home");
const themeToggle = document.getElementById("theme-toggle");
const themeIcon = themeToggle?.querySelector(".theme-icon");

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
  if (!themeToggle || !themeIcon) return;
  const isDark = theme === "dark";
  themeToggle.setAttribute("aria-pressed", String(isDark));
  themeToggle.setAttribute("aria-label", isDark ? "Switch to day mode" : "Switch to night mode");
  themeIcon.textContent = isDark ? "☀" : "☾";
}

applyTheme(getInitialTheme());

themeToggle?.addEventListener("click", () => {
  const nextTheme = document.body.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("anza-theme", nextTheme);
  applyTheme(nextTheme);
});

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
    if (targetView === "chat-view" && inputBox) {
      inputBox.focus();
    }
  });
});

brandHome?.addEventListener("click", () => {
  switchView("chat-view");
  if (chatContainer) chatContainer.scrollTop = 0;
  if (inputBox) inputBox.focus();
});

promptBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    const prompt = btn.dataset.prompt;
    if (prompt) submitPrompt(prompt);
  });
});

modeTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    modeTabs.forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    if (inputBox && tab.dataset.placeholder) {
      inputBox.placeholder = tab.dataset.placeholder;
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
  inputBox.value = "";
  inputBox.style.height = "44px";
  state.isStreaming = true;
  setPromptButtonsDisabled(true);
  setLoadingState(sendBtn, true);

  const botMsgElement = appendMessage(chatContainer, "bot", "Searching official De Anza sources...");
  state.activeBotMessage = botMsgElement;
  attachStopButton(botMsgElement);
  let fullResponse = "";

  await streamChat({
    message: query,
    history: state.history,
    signal: state.abortController.signal,
    onToken: (token) => {
      fullResponse += token;
      updateBotMessage(botMsgElement, fullResponse);
      scrollToBottom(chatContainer);
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
