// Handles the chat API call and the SSE response stream.
import { API_ENDPOINTS } from "./config.js";

// Backend sends chunks as server-sent events. Keep the callbacks small so
// the UI layer can decide how to render each token.
export async function streamChat({ message, history, onToken, onDone, onError, signal }) {
  try {
    const response = await fetch(API_ENDPOINTS.CHAT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history: history || []
      }),
      signal
    });

    if (!response.ok) {
      throw new Error(`Server returned HTTP ${response.status} (${response.statusText})`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop(); // Save the unfinished event for the next chunk.

      for (const evt of events) {
        const trimmed = evt.trim();
        if (!trimmed.startsWith("data: ")) continue;

        try {
          const data = JSON.parse(trimmed.slice(6));
          if (data.done) {
            if (onDone) onDone();
            return;
          }
          if (data.text && onToken) {
            onToken(data.text);
          }
        } catch {
          // Some streams may send raw text instead of JSON.
          const rawToken = trimmed.slice(6);
          if (rawToken && rawToken !== "[DONE]" && onToken) {
            onToken(rawToken);
          }
        }
      }
    }

    if (onDone) onDone();

  } catch (err) {
    if (err.name === "AbortError") {
      console.log("Chat stream aborted by user.");
      return;
    }
    if (onError) onError(err);
  }
}
