# SAL Design System

Source of truth for exact values is `sal/web/static/css/style.css` (CSS
custom properties) — this file explains the *system* and the reasoning,
not a duplicate value-for-value listing. For the module/page structure
that consumes this system, see `ARCHITECTURE.md`'s Frontend section.

## Philosophy

Enterprise security console — professional, data-dense, trustworthy. Not
playful, not flashy. Every design decision here was made deliberately
because this tool runs against a live, security-sensitive SAP environment,
often on a locked-down client network:

- **Zero external dependencies.** No CDN fonts, icon libraries, or JS.
  System font stack (`"Segoe UI", -apple-system, ...`), inline SVG icons
  only.
- **No build step.** `app.js`/`style.css` are served as-is.

## Theming

Every themable value is a CSS custom property. Light is the base `:root`
palette; dark values are defined twice — once under
`@media (prefers-color-scheme: dark)` guarded by `:not([data-theme="light"])`,
and again under an explicit `:root[data-theme="dark"]` selector — so an
in-app toggle (`#themeToggle` in `app.js`, top-right of the shell bar) can
override the browser's own preference in either direction. Choice persists
per-browser via `localStorage`.

This exists because Chrome and Edge were observed reporting *different*
`prefers-color-scheme` results on the same machine — each browser has its
own independent appearance setting, not always tied to the OS. The toggle
gives an explicit, consistent override regardless of that.

Token categories (see `style.css` for exact values): shell chrome (the top
bar stays on its own fixed dark-navy gradient in both themes, since it's
already dark), surfaces, text, accent/interactive, severity (high/medium/low,
tuned specifically for WCAG AA contrast — the original medium-severity
orange only hit ~3:1 on white before that fix), elevation/shadow, and
input/skeleton tokens.

## Components

- **Tiles** — KPI numbers with a colored top accent bar, used on the
  Dashboard.
- **Panels** — the primary content container (`.panel`), used everywhere:
  Dashboard charts, Jobs table, Systems list, Coverage results.
- **Badges** — always pair a color with text (severity, status, mode) —
  never color alone, since that's an accessibility requirement, not a
  preference. A dedicated dot+label pattern, not just a colored chip.
- **Buttons** — `.btn-primary` (main action), `.btn-secondary` (outlined,
  secondary actions like Export/Manage), `.btn-sm` modifier for
  denser contexts (inline table actions).
- **Tables** — `table.findings`/`table.result`/`table.catalogue-table`,
  each with a real hover state and keyboard-focus row state.
- **Modals** — one shared system (`openModal()` in `app.js`) used for the
  whitelist manager, catalogue editors, and the Systems add/edit form —
  blurred backdrop, elevation, initial focus moved to the close button.
- **Skeleton loaders** — shimmer placeholders shown while a page's first
  API call is in flight.
- **Empty states** — a dashed-border card with centered muted text
  (`.panel > p.muted`). Any *caption* text that happens to sit inside a
  panel but is NOT an empty state must use `.panel-caption` instead of
  `.muted` alone, or it gets mis-styled as an empty-state box — this exact
  bug was found and fixed twice during this project (the SLA panel, then
  the Coverage panel), so it's worth remembering as a real trap, not a
  hypothetical one.

## Accessibility commitments

- WCAG 2.2 AA contrast minimums, checked deliberately (not assumed) when
  the severity palette was set.
- Visible `:focus-visible` outlines globally, with a light-on-dark variant
  for the shell bar's own controls.
- A skip link (hidden until keyboard-focused) and `tabindex="-1"` on
  `main#app`.
- `aria-current="page"` on the active nav link, toggled in `setActiveNav()`.
- `prefers-reduced-motion: reduce` disables animation/transition durations
  globally.
- Known gap, not yet fixed: full keyboard focus-trapping inside modals
  (Escape-to-close and click-outside-to-close work; tab-cycling doesn't
  loop). Flagged during the original redesign, not yet addressed.

## Layout

Single Flask-rendered shell (`sal/web/templates/shell.html`): a fixed
shell bar, a left sidenav (one `<a data-route="...">` per page, icons are
inline SVG matching the same stroke-based style throughout, grouped under
small uppercase `.sidenav-section` labels - Monitoring / Data Collection /
System Health), and a `<main id="app">` that every page's render function
replaces via `innerHTML`. No routing library — `location.hash` + a small
`route()` dispatcher in `app.js`.

**Home is the gate in front of every other page** (2026-09-12, replacing
the old standalone Systems page): with no system chosen yet this browser
(`state.systemChosen` in `app.js`), any route renders Home instead of
erroring or half-rendering against an empty scope - Home's own system
tiles (grouped by environment, one `+ Add system` tile) are both the
entry point and where the systems registry is now managed. Tiles are
styled as SAP Fiori Launchpad tiles (`.fiori-tile*` in `style.css`) -
fixed 176x176 squares, title/subtitle top, an icon anchored bottom-right,
an accent top border matching the Dashboard `.tile` component's visual
language - since this console's audience is specifically SAP-technical.
Edit/Remove live behind each tile's small "more actions" (⋮) popover
rather than a persistent button row. Once a system is chosen (from a Home card, or the shellbar's
`#systemSelect` quick-switch) it's remembered across reloads via
`localStorage` (mirroring the theme toggle's own persistence), and the
shellbar logo links back to Home (`.shellbar-brand`) for switching without
re-picking every visit. The sidenav and the quick-switch are both hidden
(`body.route-home` in `style.css`) while Home itself is showing, since
Home's cards are the picker there.

**Dropdown menu** (`.menu` / `setupDropdownMenu()` in `app.js`) - a
lighter popover than the modal system, used to group a toolbar's related
actions (e.g. the Findings page's CSV/Excel/ITGC export formats behind one
"Export" button) instead of one same-weight button per action. Closes on
outside click, Escape, or an item click; returns focus to the trigger.
