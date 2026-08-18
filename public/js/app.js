/**
 * Main Application Orchestrator
 */
import { streamChat } from "./api.js";
import { appendMessage, updateBotMessage, autoResizeTextarea, scrollToBottom, setLoadingState, switchView } from "./ui.js";

// DOM Elements
const chatContainer = document.getElementById("chat-container");
const inputForm = document.getElementById("input-form");
const inputBox = document.getElementById("input-box");
const sendBtn = document.getElementById("send-btn");
const navBtns = document.querySelectorAll(".nav-btn");

// Conversation State
const state = {
  history: [],
  abortController: null
};

// Navigation Tab Switching (Home vs Authors)
navBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    const targetView = btn.dataset.view;
    switchView(targetView);
    if (targetView === "chat-view" && inputBox) {
      inputBox.focus();
    }
  });
});

// Global helper for quick suggestion chips
window.askQuestion = function (text) {
  if (!inputBox) return;
  inputBox.value = text;
  autoResizeTextarea(inputBox);
  inputForm.dispatchEvent(new Event("submit"));
};

// Textarea Auto-Expansion Event
inputBox.addEventListener("input", () => {
  autoResizeTextarea(inputBox);
});

// Keyboard Actions: Enter to send, Shift+Enter for new line
inputBox.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    inputForm.dispatchEvent(new Event("submit"));
  }
});

// Form Submission & Stream Handling
inputForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = inputBox.value.trim();
  if (!query) return;

  // Cancel any prior in-flight request
  if (state.abortController) {
    state.abortController.abort();
  }
  state.abortController = new AbortController();

  // Render user message & reset input box
  appendMessage(chatContainer, "user", query);
  inputBox.value = "";
  inputBox.style.height = "44px";
  setLoadingState(sendBtn, true);

  // Render initial bot placeholder
  const botMsgElement = appendMessage(chatContainer, "bot", "Searching official catalog, schedule & policies...");
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
      if (fullResponse.trim()) {
        state.history.push({ role: "user", content: query });
        state.history.push({ role: "assistant", content: fullResponse });
      }
      setLoadingState(sendBtn, false);
      inputBox.focus();
    },
    onError: (err) => {
      updateBotMessage(botMsgElement, "Sorry, I encountered an issue connecting to the assistant. Please try again.");
      console.error("Chat Error:", err);
      setLoadingState(sendBtn, false);
      inputBox.focus();
    }
  });
});
