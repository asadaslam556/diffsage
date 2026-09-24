---
name: diffsage-ui
description: Design and frontend rules for DiffSage's React UI (plain CSS in frontend/src/styles.css, lucide icons, a lazy three.js hero). Use for any visual, layout, copy, component or accessibility change in frontend/, so it stays consistent with docs/design.md.
---

# DiffSage UI

The full reasoning is in `docs/design.md`; this is the working checklist. Styling is one plain stylesheet, `frontend/src/styles.css`, with tokens on `:root`. **No CSS framework**: don't add Tailwind or shadcn.

## Rules

1. **One accent.** `--accent` (`#5fd4bf`) marks actions, focus and the current page. Don't introduce a second accent or gradients between accents.
2. **Colour means something.** `--add` and `--del` are for diff lines, and `--warn` / `--info` only for `major` / `minor` severities. Violet exists only in the logo gem and the crystal's rim light.
3. **Use the tokens.** Surfaces go `--bg` → `--bg-raise` → `--surface` → `--surface-2`; radius `--r-xs` to `--r-lg` (tighter on small parts); shadows are `--shadow-1` / `--shadow-2`. No raw hex in components.
4. **Type.** Geist for the UI, Geist Mono only for code and model IDs (`.model-id`). Sentence case everywhere: no all-caps labels, no eyebrow tags, no single highlighted word in a headline.
5. **3D and motion are rationed.** The crystal (`HeroScene.jsx`), the isometric chart (`UsageChart.jsx`), and tilt (`TiltCard`) only on the sign-in card and plan cards. One page-entrance animation (`.enter`), not one per card. Transform and opacity only; everything must stop under `prefers-reduced-motion`.
6. **Every screen has its states.** Skeletons shaped like the content while loading, an empty state that says what to do next, and inline errors that say what happened and how to fix it. No `window.alert` or `confirm`.
7. **Accessibility floor.** Visible focus, a label on every icon-only button, decorative icons `aria-hidden`, `aria-invalid` plus a hint on bad fields, text at 4.5:1 or better (`--faint` is the lowest allowed), targets of 40 px or more, no horizontal scroll at 390 px.
8. **Copy.** Plain and specific, active voice, no exclamation marks, errors that don't apologise.

## Keep in mind

- three.js is lazy-loaded into its own chunk (sign-in only). Don't import it anywhere else.
- `Markdown.jsx` builds React elements, never `innerHTML`. Links are limited to `http(s)`. `SEVERITY` accepts `[major]`, `**[major]**` and `[major]:`.
- `Chat.jsx` detaches the live stream when you navigate away (`abortRef` / `patchLast`). Keep that when changing chat state.

## Tools for UI work (from the user's `~/.claude`)

`ui-ux-pro-max` for palettes, fonts and the pre-delivery checklist; `taste-skill:redesign-skill` to audit for generic patterns; `frontend-design` for plan-then-critique. `impeccable` (`/impeccable critique`, `audit`, `polish`) and `web-design-guidelines` are good for reviews.

## Verify

```powershell
cd frontend
npm test
npm run build
```

Then rebuild the container (`docker compose up -d --build frontend`) and **look at it**: screenshot sign-in, Usage, Reviews and Settings at 1440×900 and at 390 px wide, and check the browser console is clean.
