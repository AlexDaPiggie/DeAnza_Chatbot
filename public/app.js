const chatContainer = document.getElementById("chat-container");
const inputForm = document.getElementById("input-form");
const inputBox = document.getElementById("input-box");
const sendBtn = document.getElementById("send-btn");

// Configure marked to open all links in a new tab with security attributes
marked.use({
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

let chatHistory = [];

function askQuestion(text) {
  inputBox.value = text;
  autoResizeInput();
  inputForm.dispatchEvent(new Event("submit"));
}

function formatMarkdown(rawText) {
  if (!rawText) return "";

  let clean = rawText
    // 1. Force double newline before all markdown headers (#, ##, ###)
    .replace(/(?:[^\n]|^)\s*(#{1,6}\s+)/g, "\n\n$1")
    // 2. If a header has a colon or attached description on the same line, split the description to a new line
    // e.g. "### Courses: Information about..." -> "### Courses\nInformation about..."
    .replace(/(#{1,4}\s+[A-Za-z0-9\s/\\-]+?):\s+([A-Za-z])/g, "$1\n$2")
    // 3. Force double newline before glued list items (e.g. "including:*" -> "including:\n\n* ")
    .replace(/:\s*\*\s*/g, ":\n\n* ")
    // 4. Force newline before bullet items stuck to periods
    .replace(/([.!?])\s*\*\s+/g, "$1\n\n* ")
    // 5. Clean up excessive newlines
    .replace(/\n{3,}/g, "\n\n");

  return marked.parse(clean.trim());
}

function appendMessage(role, text) {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const msg = document.createElement("div");
  msg.className = `msg ${role}`;

  if (role === "user") {
    msg.textContent = text;
  } else {
    msg.innerHTML = formatMarkdown(text);
  }

  row.appendChild(msg);
  chatContainer.appendChild(row);
  chatContainer.scrollTop = chatContainer.scrollHeight;
  return msg;
}

// Auto-expanding textarea capped at 25% viewport height
function autoResizeInput() {
  inputBox.style.height = "auto";
  const maxHeight = window.innerHeight * 0.25;
  const newHeight = Math.min(Math.max(inputBox.scrollHeight, 44), maxHeight);
  inputBox.style.height = newHeight + "px";
}

inputBox.addEventListener("input", autoResizeInput);

inputBox.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    inputForm.dispatchEvent(new Event("submit"));
  }
});

inputForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = inputBox.value.trim();
  if (!query) return;

  appendMessage("user", query);
  inputBox.value = "";
  inputBox.style.height = "44px";
  sendBtn.disabled = true;

  const botMsgDiv = appendMessage("bot", "Searching catalog & schedule...");
  let fullAnswer = "";

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: query,
        history: chatHistory
      })
    });

    if (!response.ok) {
      throw new Error(`Server returned HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop(); // keep remainder in buffer

      for (const evt of events) {
        const trimmed = evt.trim();
        if (trimmed.startsWith("data: ")) {
          try {
            const data = JSON.parse(trimmed.slice(6));
            if (data.done) break;
            if (data.text) {
              fullAnswer += data.text;
              botMsgDiv.innerHTML = formatMarkdown(fullAnswer);
              chatContainer.scrollTop = chatContainer.scrollHeight;
            }
          } catch (e) {
            const rawToken = trimmed.slice(6);
            if (rawToken && rawToken !== "[DONE]") {
              fullAnswer += rawToken;
              botMsgDiv.innerHTML = formatMarkdown(fullAnswer);
              chatContainer.scrollTop = chatContainer.scrollHeight;
            }
          }
        }
      }
    }

    if (fullAnswer.trim()) {
      chatHistory.push({ role: "user", content: query });
      chatHistory.push({ role: "assistant", content: fullAnswer });
    }

  } catch (err) {
    botMsgDiv.innerHTML = "<p><em>Sorry, I encountered an issue connecting to the assistant. Please try again.</em></p>";
    console.error("Chat error:", err);
  } finally {
    sendBtn.disabled = false;
    inputBox.focus();
  }
});
