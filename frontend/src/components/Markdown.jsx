// Small markdown renderer for model output.
//
// Builds React elements directly (no innerHTML), so whatever the model
// writes can't inject markup. It only knows what reviews actually use:
// headings, lists, fenced code, quotes, inline code/bold/italic/links.
// It's also fine with half-finished input, which matters while streaming:
// an unclosed ``` just renders as an open code block until the rest arrives.

import { Fragment } from "react";

// models often bold the tag (**[major]**) or add a colon, so allow both
export const SEVERITY = /^(?:\*\*)?\[(blocker|major|minor|nit)\](?:\*\*)?:?\s*/i;

export function parseBlocks(src) {
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    const fence = line.match(/^\s*```\s*([\w+#.-]*)/);
    if (fence) {
      const code = [];
      i++;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) code.push(lines[i++]);
      const closed = i < lines.length;
      i++; // skip the closing fence (or run off the end if it hasn't arrived yet)
      blocks.push({ type: "code", lang: fence[1].toLowerCase(), lines: code, closed });
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length, text: heading[2].trim() });
      i++;
      continue;
    }

    if (/^\s*([-*+]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d/.test(line);
      const items = [];
      while (i < lines.length && /^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) {
        let text = lines[i].replace(/^\s*([-*+]|\d+[.)])\s+/, "");
        i++;
        // indented continuation lines belong to the same bullet
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) {
          text += " " + lines[i].trim();
          i++;
        }
        items.push(text);
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }

    if (/^\s*>/.test(line)) {
      const quote = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ""));
      blocks.push({ type: "quote", text: quote.join(" ") });
      continue;
    }

    if (!line.trim()) {
      i++;
      continue;
    }

    const para = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^\s*```/.test(lines[i]) &&
      !/^#{1,4}\s/.test(lines[i]) &&
      !/^\s*([-*+]|\d+[.)])\s+/.test(lines[i]) &&
      !/^\s*>/.test(lines[i])
    ) {
      para.push(lines[i++].trim());
    }
    blocks.push({ type: "para", text: para.join(" ") });
  }
  return blocks;
}

// `code`, **bold**, *italic* / _italic_, [text](https://...)
const INLINE = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*|_[^_\s][^_]*_|\[[^\]]+\]\([^)\s]+\))/g;

export function Inline({ text }) {
  const parts = text.split(INLINE);
  return parts.map((part, i) => {
    if (!part) return null;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 1) return <code key={i}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if ((part.startsWith("*") && part.endsWith("*")) || (part.startsWith("_") && part.endsWith("_")))
      return <em key={i}>{part.slice(1, -1)}</em>;
    const link = part.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/);
    if (link) {
      // only real web links; javascript: and friends stay as plain text
      if (/^https?:\/\//i.test(link[2]))
        return (
          <a key={i} href={link[2]} target="_blank" rel="noreferrer noopener">
            {link[1]}
          </a>
        );
      return <Fragment key={i}>{link[1]}</Fragment>;
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

function isDiff(block) {
  if (block.lang === "diff" || block.lang === "patch") return true;
  const marked = block.lines.filter((l) => /^[+-](?![+-])/.test(l)).length;
  return marked >= 2 && marked >= block.lines.length / 3;
}

function CodeBlock({ block }) {
  const diff = isDiff(block);
  let n = 0;
  return (
    <figure className="code">
      {block.lang && <figcaption>{block.lang}</figcaption>}
      <pre>
        {block.lines.map((line, i) => {
          let kind = "ctx";
          if (diff && /^\+(?!\+\+)/.test(line)) kind = "add";
          else if (diff && /^-(?!--)/.test(line)) kind = "del";
          else if (diff && line.startsWith("@@")) kind = "hunk";
          const gutter = diff ? { add: "+", del: "−", hunk: "", ctx: "" }[kind] : String(++n);
          const body = diff && (kind === "add" || kind === "del") ? line.slice(1) : line;
          return (
            <div className={`ln ln-${kind}`} key={i}>
              <span className="gut" aria-hidden="true">{gutter}</span>
              <code>{body || " "}</code>
            </div>
          );
        })}
        {!block.closed && <div className="ln ln-ctx"><span className="gut" /><code className="caret"> </code></div>}
      </pre>
    </figure>
  );
}

function ListItem({ text }) {
  const sev = text.match(SEVERITY);
  if (!sev) return <li><Inline text={text} /></li>;
  const level = sev[1].toLowerCase();
  return (
    <li className={`issue sev-${level}`}>
      <span className="sev">{level}</span>
      <span><Inline text={text.slice(sev[0].length)} /></span>
    </li>
  );
}

export default function Markdown({ text }) {
  const blocks = parseBlocks(text || "");
  return (
    <div className="md">
      {blocks.map((b, i) => {
        switch (b.type) {
          case "heading": {
            const Tag = `h${Math.min(b.level + 1, 5)}`;
            return <Tag key={i}><Inline text={b.text} /></Tag>;
          }
          case "code":
            return <CodeBlock key={i} block={b} />;
          case "list": {
            const Tag = b.ordered ? "ol" : "ul";
            const issues = b.items.some((t) => SEVERITY.test(t));
            return (
              <Tag key={i} className={issues ? "issues" : undefined}>
                {b.items.map((t, j) => <ListItem key={j} text={t} />)}
              </Tag>
            );
          }
          case "quote":
            return <blockquote key={i}><Inline text={b.text} /></blockquote>;
          default:
            return <p key={i}><Inline text={b.text} /></p>;
        }
      })}
    </div>
  );
}
