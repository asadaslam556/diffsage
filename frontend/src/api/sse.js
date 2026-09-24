// Server-Sent Events over fetch.
//
// EventSource can't POST or send an Authorization header, so we read the
// response body ourselves and split it into events. Chunks from the network
// don't line up with event boundaries, hence the buffer.

import { authFetch, toApiError } from "./client.js";

export function createSSEParser(onEvent) {
  let buffer = "";

  function flushBlock(block) {
    let event = "message";
    const data = [];
    for (const raw of block.split("\n")) {
      const line = raw.endsWith("\r") ? raw.slice(0, -1) : raw;
      if (!line || line.startsWith(":")) continue; // comments are keep-alives
      const colon = line.indexOf(":");
      const field = colon === -1 ? line : line.slice(0, colon);
      let value = colon === -1 ? "" : line.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") event = value;
      else if (field === "data") data.push(value);
    }
    if (!data.length) return;
    let payload;
    try {
      payload = JSON.parse(data.join("\n"));
    } catch {
      payload = { raw: data.join("\n") };
    }
    onEvent(event, payload);
  }

  return {
    push(text) {
      buffer += text.replace(/\r\n/g, "\n");
      let cut;
      while ((cut = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        flushBlock(block);
      }
    },
    end() {
      if (buffer.trim()) flushBlock(buffer);
      buffer = "";
    },
  };
}

// Posts a chat message and calls onEvent(name, data) for every event as it
// arrives. Rejects with ApiError if the server refused before streaming
// (quota, plan, validation), which is when there's a real status code.
export async function streamChat({ message, sessionId, profile, provider, signal, onEvent }) {
  const response = await authFetch("/api/agent/chat", {
    method: "POST",
    signal,
    headers: { Accept: "text/event-stream" },
    body: JSON.stringify({
      message,
      session_id: sessionId ?? null,
      profile: profile ?? null,
      provider: provider ?? null,
    }),
  });
  if (!response.ok) throw await toApiError(response);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = createSSEParser(onEvent);
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
    }
    parser.push(decoder.decode());
    parser.end();
  } finally {
    reader.releaseLock?.();
  }
}
