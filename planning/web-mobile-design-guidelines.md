# Web UI: Mobile-First CSS Guidelines

Design rules for the Bitcoin Accounting web frontend. These patterns are shared across all Forbell household web apps (see `familyPulse/public/style.css` for the canonical reference).

## Viewport Containment (iPhone / Mobile Safari)

CSS grid and flex children default to `min-width: auto`, which lets interior content (tables with `min-width`, long text) blow the page wider than the viewport on mobile.

**Rules:**
- **Always add `min-width: 0`** on grid/flex children — panels, subpanels, layout grid items, list items, dual-column children
- Use `overflow-wrap: break-word` or `overflow-wrap: anywhere` on text-heavy containers (panel headings, policy summaries, list item text)
- Containers that hold wide interior content (e.g., horizontally-scrollable tables) need `overflow: hidden` or `overflow: auto` plus `min-width: 0`
- `body { overflow-x: hidden }` is the safety net — but fix the root cause (`min-width: 0`) rather than relying on it alone

**Why this matters:** The iPhone viewport broke on the bitcoin accounting web UI because a 580px min-width table and long policy text pushed parent flex/grid containers wider than the screen. The fix was adding `min-width: 0` throughout, matching the familyPulse pattern.

## Relative Paths (Subpath Compatibility)

- All `fetch()` calls, asset hrefs, and `src` attributes must use **relative paths** (`api/tax/gains`, `static/app.css`) — never absolute (`/api/...`, `/static/...`)
- This ensures the app works behind nginx on a subpath mount (`/bitcoin-accounting/`) without rewriting URLs

## Scrollable Tables

- Tables with `min-width` should be wrapped in a `.table-shell` container with:
  ```css
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  min-width: 0;
  max-width: 100%;
  ```
- The table scrolls horizontally inside the shell; the shell stays within the panel

## Quick Checklist for New UI Components

- [ ] Every grid/flex child has `min-width: 0`
- [ ] Long-text containers have `overflow-wrap: break-word` or `anywhere`
- [ ] Wide interior content (tables) is wrapped in an overflow container
- [ ] All fetch/asset paths are relative (no leading `/`)
- [ ] Tested on iPhone viewport (375px) — no horizontal scroll
