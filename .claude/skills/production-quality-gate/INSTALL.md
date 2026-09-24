# Installation and use

## Project skill

Copy the `production-quality-gate` directory into:

```text
<project>/.claude/skills/production-quality-gate/
```

Commit it so the project and team share the same rules.

## Personal skill

For all projects, copy the directory into:

```text
~/.claude/skills/production-quality-gate/
```

On Windows this is normally:

```text
%USERPROFILE%\.claude\skills\production-quality-gate\
```

## Invoke

```text
/production-quality-gate build
/production-quality-gate pre-push
/production-quality-gate pre-merge
/production-quality-gate pre-launch
/production-quality-gate full
/production-quality-gate full --fix
```

Use `build` at the start of work, `pre-push` before every push, `pre-merge` before approval, and `pre-launch` against the exact release candidate and staging environment.

## Optional repository rule

Add this concise rule to the project's `CLAUDE.md` or `AGENTS.md`:

```markdown
## Mandatory production-quality gate

Use the `production-quality-gate` skill while planning and implementing material changes. Run it in `pre-push` mode before pushing, `pre-merge` mode before declaring a PR ready, and `pre-launch` mode before production. Treat unknown checks as blocked, never claim unrun checks passed, never self-approve or deploy irreversible changes, and do not mark work complete while the skill reports `NOT READY`.
```

## Tools without Agent Skills

Paste `UNIVERSAL-PROMPT.md` into the AI tool's project/system instructions. Keep the prompt version-controlled and pair it with repository-specific commands, architecture, design tokens, data classification, jurisdictions, and release ownership.

## Important limitation

The skill is a control procedure, not proof of security or legal compliance. High-risk and regulated systems still require qualified human review, jurisdiction-specific legal advice, authorized penetration testing, and production-access validation.
