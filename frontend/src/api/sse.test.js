import { describe, expect, it } from "vitest";
import { createSSEParser } from "./sse.js";

function collect() {
  const events = [];
  const parser = createSSEParser((name, data) => events.push([name, data]));
  return { events, parser };
}

describe("createSSEParser", () => {
  it("handles events split across network chunks", () => {
    const { events, parser } = collect();
    parser.push('event: tok');
    parser.push('en\ndata: {"text":"He');
    parser.push('llo"}\n');
    expect(events).toEqual([]);
    parser.push('\nevent: token\ndata: {"text":" there"}\n\n');
    expect(events).toEqual([
      ["token", { text: "Hello" }],
      ["token", { text: " there" }],
    ]);
  });

  it("ignores comments and copes with CRLF", () => {
    const { events, parser } = collect();
    parser.push(': keep-alive\r\n\r\nevent: done\r\ndata: {"status":"ok"}\r\n\r\n');
    expect(events).toEqual([["done", { status: "ok" }]]);
  });

  it("defaults the event name and keeps non-JSON data", () => {
    const { events, parser } = collect();
    parser.push("data: plain words\n\n");
    expect(events).toEqual([["message", { raw: "plain words" }]]);
  });

  it("flushes a trailing event with no blank line on end()", () => {
    const { events, parser } = collect();
    parser.push('event: done\ndata: {"a":1}');
    parser.end();
    expect(events).toEqual([["done", { a: 1 }]]);
  });
});
