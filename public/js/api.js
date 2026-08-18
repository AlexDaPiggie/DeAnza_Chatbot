/**
 * Production Network & Streaming Client
 */
import { API_ENDPOINTS } from "./config.js";

/**
 * Sends chat query to backend and streams response tokens.
 * @param {Object} params
 * @param {string} params.message
 * @param {Array} params.history
 * @param {Function} params.onToken - Callback for each streaming string token
 * @param {Function} params.onDone - Callback when streaming completes
 * @param {Function} params.onError - Callback on HTTP/network error
 * @param {AbortSignal} [params.signal] - AbortController signal
 */
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
      buffer = events.pop(); // Keep incomplete trailing chunk in buffer

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
          // Fallback if plain text SSE token
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
