# Security policy

## Reporting a vulnerability

Please don't open a public issue. Report it privately through
[GitHub's private vulnerability reporting](https://github.com/asadaslam556/diffsage/security/advisories/new)
with steps to reproduce and the version or commit you tested.

You'll get a reply within a week. Fixes land on `main`; there are no older release branches.

## Scope

In scope: the backend API and gateway (auth, tokens, rate limits, the agent's
tool access), the web app, and the Docker Compose setup as shipped.

Out of scope: issues that need an already-compromised host or a leaked `.env`,
and problems in the model providers themselves (Anthropic, DeepSeek, OpenAI, Ollama).
