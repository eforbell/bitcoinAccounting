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

## Relative Paths and `<base href>` (Subpath Compatibility)

- The server injects a `<base href>` tag into the HTML shell, set to the app's `root_path` (e.g., `/bitcoin-accounting/`). This ensures all relative URLs (CSS, JS, images, `href` attributes) resolve from the app root — even when the browser is on a nested route like `/bitcoin-accounting/wallet/Coldcard`
- **HTML assets** (`href="static/app.css"`, `src="static/app.js"`) use plain relative paths — the `<base>` tag handles resolution
- **JS `fetch()` calls** do NOT follow `<base>` — the `appBase()` helper in `app.js` reads the `<base>` tag's `href` and constructs absolute URLs for API calls
- **Navigation** (`pushState`) uses `appPath()` which also builds from `appBase()` so links work at any route depth
- Never use absolute paths (`/api/...`, `/static/...`) — they break behind nginx subpath mounts
- The `<base href>` injection happens in `web/routes/ui.py` via `_shell_response()`

## Scrollable Tables

- Tables with `min-width` should be wrapped in a `.table-shell` container with:
  ```css
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  min-width: 0;
  max-width: 100%;
  ```
- The table scrolls horizontally inside the shell; the shell stays within the panel

## Adding New SPA Routes

When adding a new page to the SPA (e.g., `/ledger`, `/wallet/{id}`):

1. **Server route** in `web/routes/ui.py` — return `_shell_response(request)` (not `FileResponse`). This injects `<base href>` so assets load correctly at any route depth
2. **Client-side routing** in `app.js`:
   - Add the route to `currentRouteFromLocation()` for URL → page detection on fresh loads
   - Add to `appPath()` for page → URL construction in `pushState`
   - Add to `renderPageState()` to toggle the view's `hidden` class
   - Add to `showLoggedOut()` to hide the view on logout
   - Add wallet/ledger data loaders to both `refreshSession()` and the post-login handler
3. **HTML section** in `index.html` — add a `<section id="xxx-view" class="view-stack hidden">` block
4. **Playwright smoke test** — verify both click-through navigation AND direct URL deep-link work (catches `<base href>` / relative path bugs)

## Shared Rendering Patterns

- Transaction rows are rendered by `renderTransactionRows()` in `app.js` — reuse for any view showing transactions (dashboard, wallet detail, future ledger)
- Wallet list items use `<a class="list-item list-item-link" data-wallet-id="...">` with click handlers calling `navigateToWallet()` — reuse for any clickable list

## Quick Checklist for New UI Components

- [ ] Every grid/flex child has `min-width: 0`
- [ ] Long-text containers have `overflow-wrap: break-word` or `anywhere`
- [ ] Wide interior content (tables) is wrapped in an overflow container
- [ ] All fetch/asset paths are relative (no leading `/`)
- [ ] New SPA routes use `_shell_response()`, not `FileResponse`
- [ ] JS `api()` calls go through `appBase()` (never hardcode paths)
- [ ] Playwright smoke test covers direct URL deep-link for new routes
- [ ] Tested on iPhone viewport (375px) — no horizontal scroll
