import { describe, expect, it } from "vitest";
import { parseBlocks } from "./Markdown.jsx";

describe("parseBlocks", () => {
  it("splits a typical review into sections", () => {
    const blocks = parseBlocks("## Summary\nFine overall.\n\n## Issues\n- [major] leaks a handle\n- [nit] naming\n");
    expect(blocks.map((b) => b.type)).toEqual(["heading", "para", "heading", "list"]);
    expect(blocks[3].items).toEqual(["[major] leaks a handle", "[nit] naming"]);
  });

  it("keeps an unfinished code fence open while streaming", () => {
    const [block] = parseBlocks("```python\ndef f():\n    return 1");
    expect(block).toMatchObject({ type: "code", lang: "python", closed: false });
    expect(block.lines).toHaveLength(2);
  });

  it("joins indented continuation lines into the same bullet", () => {
    const [list] = parseBlocks("- first line\n  carries on\n- second");
    expect(list.items).toEqual(["first line carries on", "second"]);
  });
});

describe("parseBlocks on the chat starter", () => {
  it("reads a fenced diff as one closed code block", () => {
    const [block] = parseBlocks("```diff\n-a = 1\n+a = 2\n```");
    expect(block).toMatchObject({ type: "code", lang: "diff", closed: true, lines: ["-a = 1", "+a = 2"] });
  });
});

describe("severity tags", () => {
  it("recognises bolded tags the way small models write them", async () => {
    const { SEVERITY } = await import("./Markdown.jsx");
    expect("**[major]** SQL built with f-strings".match(SEVERITY)[1]).toBe("major");
    expect("[nit]: naming".match(SEVERITY)[1]).toBe("nit");
    expect("plain bullet".match(SEVERITY)).toBeNull();
  });
});
