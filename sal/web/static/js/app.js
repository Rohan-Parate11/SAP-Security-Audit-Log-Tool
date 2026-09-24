(() => {
  "use strict";

  const $app = document.getElementById("app");
  const $systemSelect = document.getElementById("systemSelect");

  const state = {
    systems: [],
    systemId: "",
    client: "",
    actor: null,
    // True once a system has been explicitly chosen this browser (restored
    // from localStorage, picked on the Home page, or switched via the
    // shellbar quick-switch) - distinct from systemId being merely
    // non-empty, since that alone shouldn't skip the Home picker on a
    // fresh visit. See route()'s use of this flag.
    systemChosen: false,
  };

  // ---- Last-selected system (persisted like the theme choice) --------------

  const LAST_SYSTEM_KEY = "sal-last-system";

  function storedSystemChoice() {
    try {
      const raw = localStorage.getItem(LAST_SYSTEM_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed && parsed.systemId ? parsed : null;
    } catch {
      return null;
    }
  }

  function persistSystemChoice(systemId, client) {
    try {
      localStorage.setItem(LAST_SYSTEM_KEY, JSON.stringify({ systemId, client }));
    } catch {
      /* private browsing or storage blocked - choice just won't persist */
    }
  }

  function clearPersistedSystemChoice() {
    try {
      localStorage.removeItem(LAST_SYSTEM_KEY);
    } catch {
      /* ignore */
    }
  }

  // ---- Theme (light/dark) --------------------------------------------------
  //
  // Defaults to following the browser's own prefers-color-scheme setting
  // (no data-theme attribute set). An explicit in-app choice is persisted
  // per-browser in localStorage and overrides that until changed again -
  // added because Chrome and Edge can each report a different preference
  // even on the same OS, depending on each browser's own appearance setting.

  const THEME_KEY = "sal-theme";
  const $themeToggle = document.getElementById("themeToggle");

  const THEME_ICON_FOR_NEXT = {
    light: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
    dark: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>',
  };

  function storedTheme() {
    try {
      const value = localStorage.getItem(THEME_KEY);
      return value === "light" || value === "dark" ? value : null;
    } catch {
      return null;
    }
  }

  function effectiveTheme() {
    const explicit = document.documentElement.getAttribute("data-theme");
    if (explicit) return explicit;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark" : "light";
  }

  function renderThemeToggle() {
    if (!$themeToggle) return;
    const next = effectiveTheme() === "dark" ? "light" : "dark";
    $themeToggle.innerHTML = THEME_ICON_FOR_NEXT[next];
    $themeToggle.setAttribute("aria-label", `Switch to ${next} theme`);
    $themeToggle.title = `Switch to ${next} theme`;
  }

  function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* private browsing or storage blocked - theme just won't persist */
    }
    renderThemeToggle();
  }

  const initialTheme = storedTheme();
  if (initialTheme) document.documentElement.setAttribute("data-theme", initialTheme);
  renderThemeToggle();
  if ($themeToggle) {
    $themeToggle.addEventListener("click", () => {
      setTheme(effectiveTheme() === "dark" ? "light" : "dark");
    });
  }

  // Inline SVG icons for buttons/menus (stroke-based, matching the sidenav's
  // existing icon style - no icon font/library per the zero-external-deps
  // constraint). Kept as small stand-alone strings rather than a build-time
  // sprite since there's no build step in this project.
  const ICON = {
    refresh: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/></svg>',
    list: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>',
    download: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/></svg>',
    chevronDown: '<svg class="menu-chevron" aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
    file: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/></svg>',
    seal: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2 4 6v6c0 5 3.4 8.6 8 9 4.6-.4 8-4 8-9V6l-8-4Z"/><path d="m9 12 2 2 4-4"/></svg>',
    book: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/></svg>',
    plus: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>',
    server: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="7" rx="1.5"/><rect x="2" y="13" width="20" height="7" rx="1.5"/><path d="M6 7.5h.01"/><path d="M6 16.5h.01"/></svg>',
    moreVertical: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><circle cx="12" cy="5" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="12" cy="19" r="1.6"/></svg>',
    pencil: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
    trash: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/><path d="M19 6v13a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>',
    warning: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
    columns: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M9 4v16"/><path d="M15 4v16"/></svg>',
    filter: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4h18l-7 8v6l-4 2v-8Z"/></svg>',
    close: '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="M6 6l12 12"/></svg>',
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  async function api(path) {
    const res = await fetch(path, { headers: { Accept: "application/json" } });
    if (!res.ok) {
      throw new Error(`Request to ${path} failed (${res.status})`);
    }
    return res.json();
  }

  async function apiWrite(path, method, body) {
    const res = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || `Request to ${path} failed (${res.status})`);
    }
    return data;
  }

  // Array values (an Excel-style column-header filter's checked options)
  // become repeated keys (?status=queued&status=running), matching
  // sal/web/api.py's _multi_arg()/request.args.getlist() on the other end -
  // every existing caller passes only plain strings, so this is additive,
  // not a behavior change for any of them.
  function scopeParams(extra = {}) {
    const params = new URLSearchParams({ system_id: state.systemId || "", client: state.client || "" });
    for (const [key, value] of Object.entries(extra)) {
      if (Array.isArray(value)) {
        value.forEach((v) => params.append(key, v));
      } else {
        params.set(key, value);
      }
    }
    return params;
  }

  function setActiveNav(route) {
    document.querySelectorAll(".sidenav a").forEach((a) => {
      const isActive = route.startsWith(a.dataset.route);
      a.classList.toggle("active", isActive);
      if (isActive) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
  }

  function skeleton(height = 120) {
    return `<div class="skeleton" style="height:${height}px"></div>`;
  }

  // ---- KPI tiles / charts -------------------------------------------------

  function tile(label, value, sevClass, opts = {}) {
    const idAttr = opts.valueId ? ` id="${opts.valueId}"` : "";
    const inner = `
      <div class="tile-value"${idAttr}>${escapeHtml(value)}</div>
      <div class="tile-label">${escapeHtml(label)}</div>`;
    if (opts.href) {
      return `<a class="tile ${sevClass}" href="${opts.href}">${inner}</a>`;
    }
    if (opts.catalogue) {
      return `<button type="button" class="tile ${sevClass}" data-catalogue="${opts.catalogue}">${inner}</button>`;
    }
    return `<div class="tile ${sevClass}">${inner}</div>`;
  }

  // Animates a tile's numeric value counting up from 0 on first render -
  // purely a display touch (the real, final value is already in the DOM
  // from tile()'s own escapeHtml(value) before this runs), so any failure
  // mode here (missing element, non-numeric value) just leaves that
  // synchronously-rendered value alone rather than needing its own
  // fallback path.
  function animateCountUp(elId, target) {
    const el = document.getElementById(elId);
    if (!el) return;
    const value = Number(target);
    if (!Number.isFinite(value)) return;
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const duration = 600;
    const start = performance.now();
    function step(now) {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - (1 - progress) ** 3; // ease-out cubic
      el.textContent = Math.round(value * eased).toLocaleString();
      if (progress < 1) requestAnimationFrame(step);
      else el.textContent = value.toLocaleString();
    }
    requestAnimationFrame(step);
  }

  function selectSystem(systemId, client) {
    state.systemId = systemId;
    state.client = client;
    state.systemChosen = true;
    persistSystemChoice(systemId, client);
    renderSystemSelector();
  }

  // ---- Dropdown menu (toolbar "Export" button etc.) -------------------------
  //
  // A lighter-weight popover than the modal system above - no backdrop, closes
  // on outside click or Escape, returns focus to the trigger. Generic so any
  // page can build one: markup is `.menu > (.menu-trigger, .menu-panel)`,
  // trigger toggles the panel, items are `[role="menuitem"]` and close the
  // menu on click (their own href/click handler still runs first).
  // Tracks whichever dropdown menu (if any) is currently open, across every
  // setupDropdownMenu() instance on the page - opening one closes whatever
  // else was open, rather than letting several stack up at once (easy to
  // trigger once a page has more than one, like the Home page's one "more
  // actions" popover per tile).
  let _openDropdownMenuClose = null;

  function setupDropdownMenu(root) {
    const trigger = root.querySelector(".menu-trigger");
    const panel = root.querySelector(".menu-panel");
    if (!trigger || !panel) return;

    function onDocClick(e) {
      if (!root.contains(e.target)) close();
    }
    function onKeydown(e) {
      if (e.key === "Escape") {
        close();
        trigger.focus();
      }
    }
    function close() {
      panel.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onKeydown);
      if (_openDropdownMenuClose === close) _openDropdownMenuClose = null;
    }
    function open() {
      if (_openDropdownMenuClose) _openDropdownMenuClose();
      _openDropdownMenuClose = close;
      panel.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      document.addEventListener("click", onDocClick);
      document.addEventListener("keydown", onKeydown);
    }

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      if (panel.hidden) open(); else close();
    });
    panel.querySelectorAll('[role="menuitem"]').forEach((item) => {
      item.addEventListener("click", close);
    });
  }

  // ---- Toast (generic) -------------------------------------------------------
  //
  // One shared element for any brief, non-blocking confirmation - originally
  // built just for exports (see showExportToast below) since export links are
  // plain <a href> downloads with no other progress feedback, but the same
  // "did that actually work?" gap applies to any write action (delete/restore
  // a job or run, dispose a finding, save a schedule, ...) that otherwise just
  // silently re-renders a list. Only one toast is ever shown at a time - a
  // second call replaces the message and restarts the dismiss timer rather
  // than stacking multiple toasts.
  let _toastTimer = null;

  // variant: "info" (default - a completed action) or "error" (something
  // failed) - found in UAT (JOB-11): a rejected action (e.g. deleting a
  // queued/running job) surfaced its error via the browser's native
  // alert(), which looks and feels jarring/out of place next to the rest
  // of the app's own UI. role="alert" (not "status") on an error toast so
  // it's announced more assertively, matching its higher importance.
  function showToast(message, { duration = 4000, variant = "info" } = {}) {
    let el = document.getElementById("appToast");
    if (!el) {
      el = document.createElement("div");
      el.id = "appToast";
      el.className = "toast";
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.setAttribute("role", variant === "error" ? "alert" : "status");
    el.classList.toggle("toast-error", variant === "error");
    el.classList.add("toast-visible");
    if (_toastTimer) clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => el.classList.remove("toast-visible"), duration);
  }

  function showErrorToast(message) {
    showToast(message, { duration: 6000, variant: "error" });
  }

  function showExportToast() {
    showToast(
      "Preparing your export… large date ranges can take up to a minute. "
      + "It will download automatically when ready - feel free to keep working.",
      { duration: 8000 },
    );
  }

  function setupExportToasts() {
    document.addEventListener("click", (e) => {
      const link = e.target.closest(
        'a[href*="/events/export"], a[href*="/findings/export"], a[href*="/collection-runs/export"]'
      );
      if (!link || e.defaultPrevented) return;
      const href = link.getAttribute("href") || "";
      if (!href || href === "#") return;
      showExportToast();
    });
  }

  // ---- Catalogue modal (critical transactions / sensitive tables) --------

  const CATALOGUE_CONFIG = {
    "critical-transactions": {
      title: "Critical Transactions",
      codeLabel: "Transaction code",
      codeField: "transaction_code",
      idKey: "transaction_code",
    },
    "sensitive-tables": {
      title: "Sensitive Tables",
      codeLabel: "Table name",
      codeField: "table_name",
      idKey: "table_name",
    },
  };

  function closeModal() {
    const el = document.getElementById("modalOverlay");
    if (el) el.remove();
    document.removeEventListener("keydown", handleModalEscape);
  }

  function handleModalEscape(e) {
    if (e.key === "Escape") closeModal();
  }

  function openModal(title) {
    closeModal();
    const overlay = document.createElement("div");
    overlay.id = "modalOverlay";
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
        <div class="modal-head">
          <h2>${escapeHtml(title)}</h2>
          <button type="button" class="modal-close" aria-label="Close">&times;</button>
        </div>
        <div class="modal-body">${skeleton(160)}</div>
      </div>`;
    document.body.appendChild(overlay);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeModal();
    });
    overlay.querySelector(".modal-close").addEventListener("click", closeModal);
    document.addEventListener("keydown", handleModalEscape);
    overlay.querySelector(".modal-close").focus();
    return overlay.querySelector(".modal-body");
  }

  async function openCatalogueModal(kind) {
    const cfg = CATALOGUE_CONFIG[kind];
    if (!cfg) return;
    openModal(cfg.title);
    await loadCatalogue(kind, cfg);
  }

  function renderCatalogueTable(items, cfg) {
    if (!items.length) {
      return '<p class="muted">No entries yet.</p>';
    }
    const rows = items
      .map(
        (item) => `
        <tr>
          <td class="mono">${escapeHtml(item[cfg.idKey])}</td>
          <td>${escapeHtml(item.description || "")}</td>
          <td class="muted">${escapeHtml(item.added_by || "")}</td>
          <td><button type="button" class="link-danger" data-code="${escapeHtml(item[cfg.idKey])}">Remove</button></td>
        </tr>`
      )
      .join("");
    return `
      <table class="catalogue-table">
        <thead><tr><th>${escapeHtml(cfg.codeLabel)}</th><th>Description</th><th>Added by</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  const CATALOGUE_TILE_IDS = {
    "critical-transactions": "tileCriticalTxCount",
    "sensitive-tables": "tileSensitiveTablesCount",
  };

  function refreshCatalogueTileCount(kind, count) {
    const el = document.getElementById(CATALOGUE_TILE_IDS[kind]);
    if (el) el.textContent = count;
  }

  async function loadCatalogue(kind, cfg) {
    const data = await api(`/api/catalogues/${kind}`);
    refreshCatalogueTileCount(kind, data.items.length);
    const body = document.querySelector("#modalOverlay .modal-body");
    if (!body) return; // modal was closed while loading

    body.innerHTML = `
      ${renderCatalogueTable(data.items, cfg)}
      <form class="catalogue-add-form">
        <input type="text" name="code" placeholder="${escapeHtml(cfg.codeLabel)}" required>
        <input type="text" name="description" placeholder="Description (optional)">
        <button type="submit" class="btn-primary btn-sm">Add</button>
      </form>
      <p class="catalogue-error error" hidden></p>`;

    body.querySelectorAll(".link-danger").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
          await apiWrite(`/api/catalogues/${kind}/${encodeURIComponent(btn.dataset.code)}`, "DELETE");
          await loadCatalogue(kind, cfg);
        } catch (err) {
          btn.disabled = false;
          const errEl = body.querySelector(".catalogue-error");
          errEl.textContent = err.message;
          errEl.hidden = false;
        }
      });
    });

    const form = body.querySelector(".catalogue-add-form");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errEl = body.querySelector(".catalogue-error");
      errEl.hidden = true;
      const code = form.code.value.trim();
      if (!code) return;
      try {
        await apiWrite(`/api/catalogues/${kind}`, "POST", {
          [cfg.codeField]: code,
          description: form.description.value.trim(),
        });
        await loadCatalogue(kind, cfg);
      } catch (err) {
        errEl.textContent = err.message;
        errEl.hidden = false;
      }
    });
  }

  function barList(byRule) {
    const max = Math.max(1, ...byRule.map((r) => r.count));
    return byRule
      .map((r) => {
        const pct = Math.round((r.count / max) * 100);
        const href = `#/findings?rule=${encodeURIComponent(r.key)}`;
        return `
          <a class="bar-row" href="${href}">
            <span class="bar-label" title="${escapeHtml(r.label)}">${escapeHtml(r.label)}</span>
            <span class="bar-track"><span class="bar-fill" style="width:${pct}%"></span></span>
            <span class="bar-count">${r.count}</span>
          </a>`;
      })
      .join("");
  }

  function donut(totals) {
    const total = totals.high + totals.medium + totals.low;
    const r = 40;
    const circumference = 2 * Math.PI * r;
    const segments = [
      { value: totals.high, cls: "high", label: "High" },
      { value: totals.medium, cls: "medium", label: "Medium" },
      { value: totals.low, cls: "low", label: "Low" },
    ];
    let offset = 0;
    const circles = segments
      .map((seg) => {
        if (!total || !seg.value) return "";
        const length = (seg.value / total) * circumference;
        const circle = `<circle class="donut-seg donut-${seg.cls}" r="${r}" cx="50" cy="50"
          fill="none" stroke-width="14" stroke-dasharray="${length} ${circumference - length}"
          stroke-dashoffset="${-offset}" transform="rotate(-90 50 50)"/>`;
        offset += length;
        return circle;
      })
      .join("");

    const legend = segments
      .map(
        (seg) => `
        <li><span class="legend-dot legend-${seg.cls}"></span>${seg.label}
          <strong>${seg.value}</strong></li>`
      )
      .join("");

    return `
      <div class="donut-wrap">
        <svg class="donut" viewBox="0 0 100 100">
          <circle r="${r}" cx="50" cy="50" fill="none" stroke="#eef1f4" stroke-width="14"/>
          ${circles || ""}
          <text x="50" y="55" text-anchor="middle" class="donut-total">${total}</text>
        </svg>
        <ul class="legend">${legend}</ul>
      </div>`;
  }

  function relativeTime(iso) {
    if (!iso) return "never";
    const then = new Date(iso);
    if (Number.isNaN(then.getTime())) return escapeHtml(iso);
    const seconds = Math.round((Date.now() - then.getTime()) / 1000);
    const units = [
      ["day", 86400],
      ["hour", 3600],
      ["minute", 60],
    ];
    for (const [label, secs] of units) {
      const n = Math.floor(seconds / secs);
      if (n >= 1) return `${n} ${label}${n > 1 ? "s" : ""} ago`;
    }
    return "just now";
  }

  // ---- Dashboard view ------------------------------------------------------

  // SLA bucket coloring is deliberately about the bucket, not the finding's
  // severity - "breached" is always the alarming (red) state regardless of
  // whether the underlying finding is High/Medium/Low, since a breach is
  // itself the thing demanding attention. Thresholds themselves (High=1,
  // Medium=3, Low=7 business days) are never hardcoded here - only whatever
  // the API returns (data.sla.buckets counts, and each overdue item's own
  // business_days_open/threshold_days) is displayed.
  const SLA_BUCKET_BADGE = { on_track: "success", at_risk: "medium", breached: "high" };
  const SLA_BUCKET_LABEL = { on_track: "On track", at_risk: "At risk", breached: "Breached" };

  // Stacked bar chart above the exact-count table (DASH-07, 2026-09-16) -
  // one row per severity, each a track stacked with up to 3 segments sized
  // by flex-grow (proportional to count within that severity's own total,
  // not the grand total across severities - each row answers "how is THIS
  // severity's SLA doing", which a shared scale across very differently
  // sized severities would obscure). A severity with zero open findings
  // renders a single muted placeholder segment rather than an empty track,
  // so the row still reads as "nothing open" instead of looking broken.
  function renderSlaBucketsChart(buckets) {
    const rows = ["High", "Medium", "Low"]
      .map((sev) => {
        const b = (buckets && buckets[sev]) || { on_track: 0, at_risk: 0, breached: 0 };
        const total = (b.on_track || 0) + (b.at_risk || 0) + (b.breached || 0);
        const track = total
          ? ["on_track", "at_risk", "breached"]
              .filter((bucket) => b[bucket])
              .map((bucket) => `<span class="sla-chart-seg sla-chart-seg-${bucket.replace("_", "-")}"
                  style="flex-grow:${b[bucket]}" title="${escapeHtml(SLA_BUCKET_LABEL[bucket])}: ${b[bucket]}"></span>`)
              .join("")
          : '<span class="sla-chart-seg sla-chart-empty" title="No open findings"></span>';
        return `
          <div class="sla-chart-row">
            <span class="badge badge-${sev.toLowerCase()}">${sev}</span>
            <span class="sla-chart-track" aria-hidden="true">${track}</span>
          </div>`;
      })
      .join("");
    return `
      <div class="sla-chart">
        ${rows}
        <ul class="legend sla-chart-legend">
          <li><span class="legend-dot legend-ontrack"></span>On track</li>
          <li><span class="legend-dot legend-medium"></span>At risk</li>
          <li><span class="legend-dot legend-high"></span>Breached</li>
        </ul>
      </div>`;
  }

  function renderSlaBucketsTable(buckets) {
    const rows = ["High", "Medium", "Low"]
      .map((sev) => {
        const b = (buckets && buckets[sev]) || { on_track: 0, at_risk: 0, breached: 0 };
        const cells = ["on_track", "at_risk", "breached"]
          .map((bucket) => `<td><span class="badge badge-${SLA_BUCKET_BADGE[bucket]}">${b[bucket] || 0}</span></td>`)
          .join("");
        return `
        <tr>
          <td><span class="badge badge-${sev.toLowerCase()}">${sev}</span></td>
          ${cells}
        </tr>`;
      })
      .join("");
    return `
      <table class="catalogue-table">
        <thead><tr><th>Severity</th><th>${SLA_BUCKET_LABEL.on_track}</th>
          <th>${SLA_BUCKET_LABEL.at_risk}</th><th>${SLA_BUCKET_LABEL.breached}</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  function renderMostOverdueTable(items) {
    if (!items.length) {
      return '<p class="muted">No breached findings right now.</p>';
    }
    const rows = items
      .map((o) => `
        <tr>
          <td><span class="badge badge-${o.severity.toLowerCase()}">${escapeHtml(o.severity)}</span></td>
          <td>${escapeHtml(o.rule_label)}</td>
          <td>${escapeHtml(o.user_id || "(multiple users)")}</td>
          <td>${escapeHtml(o.summary)}</td>
          <td>${escapeHtml(o.business_days_open)} of ${escapeHtml(o.threshold_days)} business day${o.threshold_days === 1 ? "" : "s"} open</td>
          <td><a class="btn-secondary btn-sm" href="#/findings?severity=${encodeURIComponent(o.severity)}">View ${escapeHtml(o.severity)} findings</a></td>
        </tr>`)
      .join("");
    return `
      <table class="catalogue-table">
        <thead><tr><th>Severity</th><th>Rule</th><th>User</th><th>Summary</th><th>Aging</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  async function renderDashboard() {
    $app.innerHTML = `
      <div class="page-head"><h1>Dashboard</h1></div>
      <div class="tiles">${skeleton(90)}${skeleton(90)}${skeleton(90)}${skeleton(90)}</div>
      <div class="panels">${skeleton(220)}${skeleton(220)}</div>`;

    const data = await api(`/api/dashboard?${scopeParams()}`);

    const runInfo = data.last_run
      ? `Last collection ${relativeTime(data.last_run.finished_at || data.last_run.started_at)}
         &middot; ${(data.last_run.row_count ?? 0).toLocaleString()} events fetched
         &middot; status: ${escapeHtml(data.last_run.status)}`
      : "No collection runs recorded yet for this system/client.";

    $app.innerHTML = `
      <div class="page-head">
        <h1>Dashboard</h1>
        <p class="muted">
          ${data.event_count.toLocaleString()} events stored for
          <strong>${escapeHtml(state.systemId)} / ${escapeHtml(state.client)}</strong>
          &middot; ${runInfo}
        </p>
      </div>

      <div class="tiles">
        ${tile("Total findings", data.totals.total, "tile-neutral", { href: "#/findings", valueId: "tileTotalFindings" })}
        ${tile("High severity", data.totals.high, "tile-high", { href: "#/findings?severity=High", valueId: "tileHighFindings" })}
        ${tile("Medium severity", data.totals.medium, "tile-medium", { href: "#/findings?severity=Medium", valueId: "tileMediumFindings" })}
        ${tile("Low severity", data.totals.low, "tile-low", { href: "#/findings?severity=Low", valueId: "tileLowFindings" })}
      </div>
      <div class="tiles tiles-secondary">
        ${tile("Critical transactions tracked", data.critical_transaction_count, "tile-neutral", { catalogue: "critical-transactions", valueId: "tileCriticalTxCount" })}
        ${tile("Sensitive tables tracked", data.sensitive_table_count, "tile-neutral", { catalogue: "sensitive-tables", valueId: "tileSensitiveTablesCount" })}
      </div>
      <p class="muted tiles-hint">Click a tracked-items tile to view, add, or remove entries.</p>

      <div class="panels">
        <div class="panel">
          <h2>Findings by rule</h2>
          ${data.by_rule.some((r) => r.count > 0)
            ? barList(data.by_rule)
            : '<p class="muted">No findings yet - run a collection first.</p>'}
        </div>
        <div class="panel">
          <h2>Severity breakdown</h2>
          ${data.totals.total ? donut(data.totals) : '<p class="muted">Nothing to show yet.</p>'}
        </div>
      </div>

      <div class="panel" id="slaPanel" style="margin-top:1.25rem">
        <h2>SLA &amp; aging (open findings)</h2>
        <p class="panel-caption">
          Business days since each finding was first detected (Monday&ndash;Friday, no holiday calendar).
        </p>
        ${renderSlaBucketsChart(data.sla && data.sla.buckets)}
        ${renderSlaBucketsTable(data.sla && data.sla.buckets)}
        <h3 class="panel-subhead">Most overdue</h3>
        ${renderMostOverdueTable((data.sla && data.sla.most_overdue) || [])}
      </div>

      <div class="panel" id="recentHighPanel" style="margin-top:1.25rem">
        <h2>Recent high-severity findings</h2>
        ${renderFindingsTable(data.recent_high)}
      </div>`;

    $app.querySelectorAll("[data-catalogue]").forEach((btn) => {
      btn.addEventListener("click", () => openCatalogueModal(btn.dataset.catalogue));
    });
    attachDispositionHandlers(document.getElementById("recentHighPanel"), renderDashboard);

    animateCountUp("tileTotalFindings", data.totals.total);
    animateCountUp("tileHighFindings", data.totals.high);
    animateCountUp("tileMediumFindings", data.totals.medium);
    animateCountUp("tileLowFindings", data.totals.low);
    animateCountUp("tileCriticalTxCount", data.critical_transaction_count);
    animateCountUp("tileSensitiveTablesCount", data.sensitive_table_count);
  }

  // ---- Findings view ------------------------------------------------------

  function evidenceHtml(evidence) {
    if (!evidence || !Object.keys(evidence).length) return "";
    const items = Object.entries(evidence)
      .map(([k, v]) => `<li><span class="ekey">${escapeHtml(k)}</span>: ${escapeHtml(v)}</li>`)
      .join("");
    return `<details><summary>evidence</summary><ul class="evidence">${items}</ul></details>`;
  }

  const DISPOSITION_OPTIONS = [
    ["open", "Open"],
    ["true_positive", "True positive"],
    ["false_positive", "False positive"],
    ["whitelisted", "Whitelisted"],
  ];

  const DISPOSITION_BADGE_CLASS = {
    open: "medium",
    true_positive: "high",
    false_positive: "success",
    whitelisted: "success",
  };

  // Column-spec-driven (mirrors JOB_COLUMNS/RUN_COLUMNS above), so the
  // Findings page can add Excel-style header filters the same way - but
  // the Rule column's filter options come from the live rules catalogue
  // (not a fixed enum baked into the spec, unlike Severity/Status), so the
  // column list is built fresh from it each call rather than a top-level
  // constant.
  function buildFindingsColumns(rules) {
    return [
      { id: "severity", label: "Severity",
        filter: { type: "options", options: [["High", "High"], ["Medium", "Medium"], ["Low", "Low"]] },
        render: (f) => `<span class="badge badge-lg badge-${f.severity.toLowerCase()}">${escapeHtml(f.severity)}</span>` },
      { id: "rule", label: "Rule",
        filter: { type: "options", options: rules.map((r) => [r.key, r.label]) },
        render: (f) => `<span class="rule-label">${escapeHtml(f.rule_label)}</span>` },
      { id: "user", label: "User", filter: { type: "text" },
        render: (f) => escapeHtml(f.user_id || "(multiple users)") },
      { id: "detected", label: "Detected", render: (f) => formatDateTime(f.detected_at) },
      { id: "summary", label: "Summary", render: (f) => `${escapeHtml(f.summary)}${evidenceHtml(f.evidence)}` },
      { id: "status", label: "Status",
        filter: { type: "options", options: DISPOSITION_OPTIONS },
        render: (f) => `<span class="badge badge-${DISPOSITION_BADGE_CLASS[f.status] || "low"}">${escapeHtml(f.status)}</span>` },
      { id: "disposition", label: "Disposition", render: (f) => {
        const options = DISPOSITION_OPTIONS
          .map(([v, l]) => `<option value="${v}" ${v === f.status ? "selected" : ""}>${l}</option>`)
          .join("");
        return `
          <div class="disp-form">
            <select class="disp-status">${options}</select>
            <input type="text" class="disp-reason" placeholder="reason (optional)">
            <button type="button" class="btn-primary btn-sm disp-save">Save</button>
            <span class="disp-error error" hidden></span>
          </div>`;
      } },
    ];
  }

  // Split head/body for the same reason as renderJobsTableHead/Body above
  // (UAT JOB-02/03/04) - only the full Findings page passes
  // showColumnFilters (Dashboard's mini "Recent high-severity" table never
  // does), so this only matters there in practice.
  function renderFindingsTableHead(showColumnFilters, colFilters, rules) {
    return buildFindingsColumns(rules).map((c) => {
      const filterHtml = showColumnFilters && c.filter
        ? columnFilterHeaderHtml(c.id, c.filter, colFilters[c.id]) : "";
      return `<th>${escapeHtml(c.label)}${filterHtml}</th>`;
    }).join("");
  }

  function renderFindingsTableBody(items, rules) {
    const cols = buildFindingsColumns(rules);
    return items.length
      ? items.map((f) => `<tr data-key="${escapeHtml(f.finding_key)}" class="sev-row-${f.severity.toLowerCase()}">${cols.map((c) => `<td>${c.render(f)}</td>`).join("")}</tr>`).join("")
      : `<tr><td colspan="${cols.length}" class="muted">No findings match these filters.</td></tr>`;
  }

  // Full first-paint render - see renderJobsTable()'s identical comment.
  function renderFindingsTable(items, { showColumnFilters = false, colFilters = {}, rules = [] } = {}) {
    return `
      <table class="findings">
        <thead><tr>${renderFindingsTableHead(showColumnFilters, colFilters, rules)}</tr></thead>
        <tbody>${renderFindingsTableBody(items, rules)}</tbody>
      </table>`;
  }

  // Shared by every view that renders a findings table (Dashboard's
  // "Recent high-severity findings" panel and the Findings page) - each
  // must call this against its own container after inserting the table,
  // since renderFindingsTable() only produces markup, it doesn't wire it up.
  function attachDispositionHandlers(container, onSaved) {
    container.querySelectorAll(".disp-save").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const row = btn.closest("tr");
        const key = row.dataset.key;
        const status = row.querySelector(".disp-status").value;
        const reason = row.querySelector(".disp-reason").value.trim();
        const errEl = row.querySelector(".disp-error");
        errEl.hidden = true;
        btn.disabled = true;
        try {
          await apiWrite(`/api/findings/${key}/dispose`, "POST", {
            status, reason_code: reason,
          });
          const label = (DISPOSITION_OPTIONS.find(([value]) => value === status) || [, status])[1];
          showToast(`Finding marked "${label}".`);
          await onSaved();
        } catch (err) {
          errEl.textContent = err.message;
          errEl.hidden = false;
          btn.disabled = false;
        }
      });
    });
  }

  function parseHashQuery() {
    const q = location.hash.split("?")[1] || "";
    return new URLSearchParams(q);
  }

  async function renderFindings() {
    const initial = parseHashQuery();
    const [{ rules }] = await Promise.all([api("/api/rules")]);

    // Rule/Severity replace what used to be separate top-of-page <select>s
    // with the same Excel-style column-header filters as Jobs/Recovery -
    // seeded from the hash query (e.g. "#/findings?severity=High", used by
    // the Dashboard's severity tile links) so that deep link still lands
    // pre-filtered the same way it did with the old dropdowns. User is a
    // new filter this table never had before (free-text, like Job name
    // elsewhere); Status keeps working the same way, just moved.
    const findingsColFilters = {
      severity: initial.get("severity") ? [initial.get("severity")] : [],
      rule: initial.get("rule") ? [initial.get("rule")] : [],
      user: "",
      status: [],
    };

    // "#/findings?finding_key=..." - the Activity page's finding_dispose
    // entries link here so a raw finding_key isn't a dead end (see
    // summarizeParams() in renderActivity()). An exact single-finding
    // lookup on the backend, deliberately ignoring every column filter
    // above and the current system/client scope (see list_findings()'s
    // own docstring) - the banner below is this view's only way out,
    // since the usual filter controls don't apply to it.
    const findingKeyFilter = initial.get("finding_key") || "";
    const findingKeyBanner = findingKeyFilter
      ? `<p class="callout">Showing one specific finding linked from Activity - column filters above don't
           apply here. <a href="#/findings">Clear and show all findings &rarr;</a></p>`
      : "";

    $app.innerHTML = `
      <div class="page-head">
        <h1>Findings</h1>
        <p class="muted">Click a column's filter icon to narrow it down, same as an Excel column filter.</p>
        ${findingKeyBanner}
        <div class="toolbar">
          <button type="button" id="syncFindingsBtn" class="btn-primary">${ICON.refresh} Sync findings</button>
          <span class="toolbar-divider" aria-hidden="true"></span>
          <div class="menu" id="exportMenu">
            <button type="button" class="btn-secondary menu-trigger" aria-haspopup="true" aria-expanded="false">
              ${ICON.download} Export ${ICON.chevronDown}
            </button>
            <div class="menu-panel" role="menu" hidden>
              <a id="exportCsvBtn" role="menuitem" href="#">${ICON.file} CSV</a>
              <a id="exportXlsxBtn" role="menuitem" href="#">${ICON.file} Excel (.xlsx)</a>
              <a id="exportItgcBtn" role="menuitem" href="#">${ICON.seal} ITGC Report (.xlsx)</a>
            </div>
          </div>
          <button type="button" id="manageWhitelistBtn" class="btn-secondary">${ICON.list} Manage whitelist</button>
          <a id="rulesCatalogBtn" class="btn-secondary" href="/api/rules/export">${ICON.book} Detection Rules</a>
          ${resetFiltersButtonHtml("findingsResetFiltersBtn", "")}
        </div>
        <div id="syncResult"></div>
      </div>
      <div class="filter-bar">
        <span id="fCount" class="muted"></span>
      </div>
      <div id="findingsBody">${skeleton(300)}</div>`;

    setupDropdownMenu(document.getElementById("exportMenu"));

    // Same reasoning as jobsTableInitialized (Jobs tab) above - a data
    // reload only touches <tbody> once the table exists, so an open
    // filter dropdown or mid-typing search box is never disturbed by one.
    let findingsTableInitialized = false;

    resetColumnFilters("findingsResetFiltersBtn", findingsColFilters,
      { severity: [], rule: [], user: "", status: [] }, () => {
        findingsTableInitialized = false;
        load();
      });

    async function load() {
      try {
        const params = scopeParams({
          rule: findingsColFilters.rule, severity: findingsColFilters.severity,
          status: findingsColFilters.status, user_id: findingsColFilters.user,
          finding_key: findingKeyFilter,
          limit: 200,
        });
        const data = await api(`/api/findings?${params}`);
        document.getElementById("fCount").textContent =
          `${data.items.length} of ${data.total} finding(s)`;
        const container = document.getElementById("findingsBody");
        if (!findingsTableInitialized) {
          container.innerHTML = renderFindingsTable(data.items, {
            showColumnFilters: true, colFilters: findingsColFilters, rules,
          });
          wireColumnFilterHeaders(container.querySelector("thead"), findingsColFilters, load);
          findingsTableInitialized = true;
        } else {
          container.querySelector("tbody").innerHTML = renderFindingsTableBody(data.items, rules);
        }
        attachDispositionHandlers(container.querySelector("tbody"), load);
        document.getElementById("exportCsvBtn").href = `/api/findings/export?${params}&format=csv`;
        document.getElementById("exportXlsxBtn").href = `/api/findings/export?${params}&format=xlsx`;
        document.getElementById("exportItgcBtn").href = `/api/findings/export?${params}&format=itgc`;
      } catch (err) {
        // Resets the flag, not just the DOM: the catch below replaces
        // #findingsBody's entire contents with a plain error message,
        // destroying the table (head included) - found in review: without
        // this reset, the *next* load() call would still take the
        // tbody-only branch above and call .querySelector("tbody") on a
        // table that no longer exists, throwing on a null result and
        // permanently wedging the page (a transient failure, e.g. one
        // dropped request, would otherwise break every future filter/
        // pagination/sync/disposition action for the rest of the visit).
        findingsTableInitialized = false;
        const body = document.getElementById("findingsBody");
        if (body) body.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
      }
    }

    document.getElementById("syncFindingsBtn").addEventListener("click", async () => {
      const btn = document.getElementById("syncFindingsBtn");
      const out = document.getElementById("syncResult");
      btn.disabled = true;
      out.innerHTML = '<p class="muted">Syncing&hellip;</p>';
      try {
        const result = await apiWrite(`/api/findings/sync?${scopeParams()}`, "POST");
        out.innerHTML = `<p class="ok">Synced: ${result.new} new of ${result.computed} computed finding(s).</p>`;
        await load();
      } catch (err) {
        out.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("manageWhitelistBtn").addEventListener("click", () => openWhitelistModal(rules));

    await load();
  }

  // ---- Whitelist modal (time-bound suppression of a rule/user pattern) ----

  // rules: looked up here for the friendly label (e.g. "Data Exports")
  // instead of the raw rule_key ("data_export") - found in UAT (FIND-09).
  // Falls back to the raw key only if a rule was since removed from the
  // catalogue entirely (rather than showing nothing).
  function renderWhitelistTable(items, rules) {
    if (!items.length) {
      return '<p class="muted">No whitelist entries yet.</p>';
    }
    const labelFor = (key) => (rules.find((r) => r.key === key) || {}).label || key;
    const rows = items
      .map(
        (w) => `
        <tr>
          <td>${escapeHtml(labelFor(w.rule_key))}</td>
          <td>${escapeHtml(w.user_id || "any user")}</td>
          <td>${escapeHtml([w.source_system, w.client].filter(Boolean).join(" / ") || "any system")}</td>
          <td>${escapeHtml(w.reason)}</td>
          <td>${escapeHtml((w.expires_at || "").slice(0, 10))}</td>
          <td><button type="button" class="link-danger" data-id="${w.id}" data-rule-label="${escapeHtml(labelFor(w.rule_key))}">Remove</button></td>
        </tr>`
      )
      .join("");
    return `
      <table class="catalogue-table">
        <thead><tr><th>Rule</th><th>User</th><th>System/Client</th><th>Reason</th>
          <th>Expires</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  async function loadWhitelist(body, rules) {
    const data = await api("/api/whitelist");
    if (!document.querySelector("#modalOverlay .modal-body")) return;

    body.innerHTML = `
      ${renderWhitelistTable(data.items, rules)}
      <form class="catalogue-add-form whitelist-add-form">
        <select name="rule_key" required>
          <option value="">Rule&hellip;</option>
          ${rules.map((r) => `<option value="${escapeHtml(r.key)}">${escapeHtml(r.label)}</option>`).join("")}
        </select>
        <input type="text" name="user_id" placeholder="User (optional)">
        <input type="text" name="reason" placeholder="Reason" required>
        <input type="date" name="expires_at" required>
        <button type="submit" class="btn-primary btn-sm">Add</button>
      </form>
      <p class="whitelist-error error" hidden></p>`;

    // Reason required, matching every other delete/restore action in the
    // app (UAT FIND-10) - the add form above already requires one,
    // removal didn't. Deliberately an inline row-swap, not
    // promptForReason()'s own modal: this whitelist UI already lives
    // inside a modal (openWhitelistModal() below), and openModal() closes
    // whatever modal is currently open before showing a new one - nesting
    // a second modal here would silently destroy this one out from under
    // itself instead of stacking on top of it.
    body.querySelectorAll(".link-danger").forEach((btn) => {
      btn.addEventListener("click", () => {
        const row = btn.closest("tr");
        const ruleLabel = btn.dataset.ruleLabel;
        row.innerHTML = `
          <td colspan="6">
            <div class="catalogue-add-form" style="align-items:center;">
              <span class="muted">Remove "${escapeHtml(ruleLabel)}"?</span>
              <input type="text" class="wl-remove-reason" placeholder="Reason" required style="flex:1;">
              <button type="button" class="link-danger wl-remove-confirm">Remove</button>
              <button type="button" class="btn-secondary btn-sm wl-remove-cancel">Cancel</button>
              <span class="wl-remove-error error" hidden></span>
            </div>
          </td>`;
        const reasonInput = row.querySelector(".wl-remove-reason");
        reasonInput.focus();
        row.querySelector(".wl-remove-cancel").addEventListener("click", () => loadWhitelist(body, rules));
        row.querySelector(".wl-remove-confirm").addEventListener("click", async () => {
          const reason = reasonInput.value.trim();
          const rowErrEl = row.querySelector(".wl-remove-error");
          if (!reason) {
            rowErrEl.textContent = "A reason is required.";
            rowErrEl.hidden = false;
            return;
          }
          try {
            await apiWrite(`/api/whitelist/${btn.dataset.id}`, "DELETE", { reason });
            showToast("Whitelist entry removed.");
            await loadWhitelist(body, rules);
          } catch (err) {
            rowErrEl.textContent = err.message;
            rowErrEl.hidden = false;
          }
        });
      });
    });

    const form = body.querySelector(".whitelist-add-form");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errEl = body.querySelector(".whitelist-error");
      errEl.hidden = true;
      const ruleKey = form.rule_key.value;
      const reason = form.reason.value.trim();
      const expiresDate = form.expires_at.value;
      if (!ruleKey || !reason || !expiresDate) return;
      try {
        await apiWrite("/api/whitelist", "POST", {
          rule_key: ruleKey,
          user_id: form.user_id.value.trim(),
          reason,
          expires_at: `${expiresDate}T23:59:59+00:00`,
          system_id: state.systemId,
          client: state.client,
        });
        showToast("Whitelist entry added.");
        await loadWhitelist(body, rules);
      } catch (err) {
        errEl.textContent = err.message;
        errEl.hidden = false;
      }
    });
  }

  async function openWhitelistModal(rules) {
    const body = openModal("Whitelist");
    await loadWhitelist(body, rules);
  }

  // ---- Connection test view -------------------------------------------------

  async function renderConnection() {
    $app.innerHTML = `
      <div class="page-head"><h1>SAP Connection</h1></div>
      <div class="panel">
        <p class="muted">Test RFC connectivity to the selected SAP system.</p>
        <button id="testBtn" class="btn-primary">
          Test connection to ${escapeHtml(state.systemId) || "..."}
        </button>
        <div id="connResult" style="margin-top:1rem"></div>
      </div>`;

    document.getElementById("testBtn").addEventListener("click", async () => {
      const btn = document.getElementById("testBtn");
      const out = document.getElementById("connResult");
      btn.disabled = true;
      out.innerHTML = '<p class="muted">Connecting&hellip;</p>';
      try {
        const res = await fetch("/api/connection-test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ system_id: state.systemId }),
        });
        const data = await res.json();
        if (data.ok) {
          const r = data.result;
          out.innerHTML = `
            <table class="result">
              <tr><th>System ID</th><td>${escapeHtml(r.system_id)}</td></tr>
              <tr><th>SAP Release</th><td>${escapeHtml(r.sap_release)}</td></tr>
              <tr><th>App server</th><td>${escapeHtml(r.host)}</td></tr>
              <tr><th>DB host</th><td>${escapeHtml(r.db_host)}</td></tr>
              <tr><th>OS</th><td>${escapeHtml(r.os)}</td></tr>
            </table>
            <p class="ok">Connection succeeded.</p>`;
        } else {
          out.innerHTML = `<p class="error">${escapeHtml(data.error)}</p>`;
        }
      } catch (err) {
        out.innerHTML = `<p class="error">Request failed: ${escapeHtml(err.message)}</p>`;
      } finally {
        btn.disabled = false;
      }
    });
  }

  // ---- Collect view (SM20/RSAU_READ_LOG-style selection screen) ----------

  function toYmd(dateInputValue) {
    return dateInputValue.replaceAll("-", "");
  }

  function toHms(timeInputValue) {
    if (!timeInputValue) return "";
    const [h, m] = timeInputValue.split(":");
    return `${h}${m}00`;
  }

  function defaultDateInput(daysAgo) {
    const d = new Date();
    d.setDate(d.getDate() - daysAgo);
    return d.toISOString().slice(0, 10);
  }

  // Builds the same /api/events/export URL Collect's own "Export data" menu
  // does, but from a specific run row's own stored dat_from/dat_to/
  // filters_json instead of the form's current field values - so a run
  // from days ago can still be re-downloaded today, using exactly the
  // criteria that run itself used, without retyping them into the form.
  function buildRunEventsExportUrl(run, fmt) {
    const filters = run.filters_json ? JSON.parse(run.filters_json) : {};
    const params = scopeParams({
      dat_from: run.dat_from || "",
      dat_to: run.dat_to || "",
      tim_from: filters.tim_from || "000000",
      tim_to: filters.tim_to || "235959",
      format: fmt,
    });
    ["user", "transaction_code", "report", "instance", "msg_code"].forEach((name) => {
      const value = filters[name];
      if (value) params.set(name, Array.isArray(value) ? value.join(",") : value);
    });
    return `/api/events/export?${params}`;
  }

  const RUN_STATUS_BADGE = { running: "medium", success: "success", error: "high" };

  // Locale pinned explicitly to "en-US" (found in review: toLocaleDateString(
  // undefined, ...) renders differently per *viewer's* browser/OS locale -
  // "Sep 12, 2026" for one analyst, "12 Sept 2026" for another looking at
  // the exact same date - which is exactly the "inconsistent format"
  // complaint this whole formatter exists to fix. One locale, everywhere,
  // regardless of who's looking at it.
  function formatDisplayDate(yyyymmdd) {
    if (!yyyymmdd || yyyymmdd.length !== 8) return escapeHtml(yyyymmdd || "-");
    const iso = `${yyyymmdd.slice(0, 4)}-${yyyymmdd.slice(4, 6)}-${yyyymmdd.slice(6, 8)}`;
    const d = new Date(`${iso}T00:00:00`);
    if (Number.isNaN(d.getTime())) return escapeHtml(yyyymmdd);
    return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  }

  // Canonical date/time display for every field in the app, whatever shape
  // it happens to be stored in server-side (found in review: three
  // independently-drifted formatters existed - a raw YYYYMMDD/HHMMSS
  // digit-string render, this file's own formatDateRange()/
  // formatDisplayDate() pair, and a separate naive ISO-slice formatter -
  // consolidated into one). Never converts timezone (matches this app's
  // existing convention of displaying stored UTC wall-clock values as-is,
  // not localized) - a plain string parse, not a Date-object round-trip,
  // for the time portion.
  function formatDateTime(value) {
    if (!value) return "-";
    const s = String(value);
    if (/^\d{8}$/.test(s)) return formatDisplayDate(s);
    if (/^\d{6}$/.test(s)) return `${s.slice(0, 2)}:${s.slice(2, 4)}:${s.slice(4, 6)}`;
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/);
    if (!m) return escapeHtml(s);
    const [, y, mo, d, hh, mm, ss] = m;
    return `${formatDisplayDate(`${y}${mo}${d}`)}, ${hh}:${mm}:${ss}`;
  }

  // Replaces raw "20260912" pairs with something readable at a glance - a
  // single-day run (dat_from === dat_to) collapses to one date instead of
  // repeating it either side of a dash.
  function formatDateRange(datFrom, datTo) {
    if (!datFrom && !datTo) return "-";
    if (datFrom === datTo) return formatDisplayDate(datFrom);
    return `${formatDisplayDate(datFrom)} &ndash; ${formatDisplayDate(datTo)}`;
  }

  // Shared by Collect's own-job progress panel and the Collection History
  // page - deletedView swaps the per-row action from Delete to Restore and
  // surfaces the stored delete_reason/deleted_by (both only ever present on
  // a soft-deleted row - see sal/web/api.py's delete_collection_run).
  // currentJobId: pass the job whose own page/panel this table is embedded
  // in (Job Detail's "runs produced by this job", Collect's live progress
  // panel) so that job's own row doesn't link back to itself (found in
  // review: it silently reopened the identical page in a new tab).
  // Collection History has no "current job" - every row there links out.
  // Column-spec-driven, mirroring JOB_COLUMNS above - currentJobId (a
  // render-time option, not a filter) suppresses linking a run's Job cell
  // back to the very job page already showing this table, so it doesn't
  // link to itself. showColumnFilters (see renderRunsTable below) is
  // opt-in per call site: Recovery's "Deleted collection runs" panel is
  // the only one with header filters - Job Detail's Job Log and Collect's
  // progress panel are already scoped to one job/one submission, where a
  // handful of rows never need filtering.
  const RUN_COLUMNS = [
    { id: "run_number", label: "#", render: (r) => `<span class="mono">${r.run_number ?? "-"}</span>` },
    { id: "job", label: "Job", filter: { type: "text" }, render: (r, { deletedView, currentJobId }) => {
      // job_name/job_description/job_mode come from the LEFT JOIN in
      // GET /api/collection-runs - NULL for any run predating the job_id
      // link or from scripts/collect_sm20.py's CLI backfill path. Reuses
      // jobLabelHtml() so the same name/fallback wording appears in both
      // places.
      const linkJobId = r.job_id != null && r.job_id !== currentJobId ? r.job_id : null;
      const jobLabel = (r.job_name || r.job_mode)
        ? jobLabelHtml({ mode: r.job_mode, job_name: r.job_name, job_description: r.job_description }, linkJobId)
        : '<span class="muted">&mdash;</span>';
      const deletedNote = deletedView && r.delete_reason
        ? `<br><span class="muted">Reason: ${escapeHtml(r.delete_reason)}${r.deleted_by ? ` &middot; ${escapeHtml(r.deleted_by)}` : ""}</span>`
        : "";
      return `${jobLabel}${deletedNote}`;
    } },
    { id: "started", label: "Started", render: (r) => formatDateTime(r.started_at) },
    { id: "range", label: "Range", render: (r) => formatDateRange(r.dat_from, r.dat_to) },
    { id: "status", label: "Status",
      filter: { type: "options", options: [["running", "Running"], ["success", "Success"], ["error", "Error"]] },
      render: (r) => `<span class="badge badge-${RUN_STATUS_BADGE[r.status] || "high"}">${escapeHtml(r.status)}</span>` },
    { id: "rows", label: "Rows", render: (r) => r.row_count ?? "-" },
    { id: "error", label: "Error", render: (r) => jobErrorHtml(r.error_message, r.error_message_friendly) },
    { id: "actions", label: "", render: (r, { deletedView }) => {
      const jobNameAttr = escapeHtml(r.job_name || "");
      const actionBtn = deletedView
        ? `<button type="button" class="btn-secondary btn-sm run-restore-btn" data-run-id="${escapeHtml(r.run_id)}" data-job-name="${jobNameAttr}">${ICON.refresh} Restore</button>`
        : `<button type="button" class="link-danger run-delete-btn" data-run-id="${escapeHtml(r.run_id)}" data-job-name="${jobNameAttr}">${ICON.trash} Delete</button>`;
      return `
        <div class="run-actions">
          <div class="menu">
            <button type="button" class="btn-secondary btn-sm menu-trigger" aria-haspopup="true" aria-expanded="false">
              ${ICON.download} Data ${ICON.chevronDown}
            </button>
            <div class="menu-panel" role="menu" hidden>
              <a role="menuitem" href="${buildRunEventsExportUrl(r, "xlsx")}">${ICON.file} Raw Excel</a>
              <a role="menuitem" href="${buildRunEventsExportUrl(r, "itgc")}">${ICON.seal} ITGC Format</a>
            </div>
          </div>
          ${actionBtn}
        </div>`;
    } },
  ];

  // Split head/body for the same reason as renderJobsTableHead/Body above
  // (UAT JOB-02/03/04) - only Recovery's "Deleted collection runs" panel
  // ever passes showColumnFilters, so this only matters there in practice.
  function renderRunsTableHead(showColumnFilters, colFilters) {
    return RUN_COLUMNS.map((c) => {
      const filterHtml = showColumnFilters && c.filter
        ? columnFilterHeaderHtml(c.id, c.filter, colFilters[c.id]) : "";
      return `<th>${escapeHtml(c.label)}${filterHtml}</th>`;
    }).join("");
  }

  function renderRunsTableBody(items, { deletedView = false, currentJobId = null, showColumnFilters = false } = {}) {
    const ctx = { deletedView, currentJobId };
    const emptyMessage = `No ${deletedView ? "deleted " : ""}collection runs${showColumnFilters ? " match the current filters" : " yet"}.`;
    return items.length
      ? items.map((r) => `<tr>${RUN_COLUMNS.map((c) => `<td>${c.render(r, ctx)}</td>`).join("")}</tr>`).join("")
      : `<tr><td colspan="${RUN_COLUMNS.length}" class="muted">${escapeHtml(emptyMessage)}</td></tr>`;
  }

  // Full first-paint render - see renderJobsTable()'s identical comment.
  function renderRunsTable(items, { deletedView = false, currentJobId = null,
                                     showColumnFilters = false, colFilters = {} } = {}) {
    return `
      <table class="findings">
        <thead><tr>${renderRunsTableHead(showColumnFilters, colFilters)}</tr></thead>
        <tbody>${renderRunsTableBody(items, { deletedView, currentJobId, showColumnFilters })}</tbody>
      </table>`;
  }

  // ---- Delete/restore-with-reason (auditor-facing: every removal from or
  // return to Collection History must be justified and attributable - see
  // sal/web/api.py's delete_collection_run/restore_collection_run) --------

  function promptForReason(title, message) {
    return new Promise((resolve) => {
      const body = openModal(title);
      body.innerHTML = `
        <p class="muted">${escapeHtml(message)}</p>
        <form id="reasonForm" class="catalogue-add-form" style="flex-direction:column; align-items:stretch;">
          <label>Reason <span class="req">*</span>
            <input type="text" name="reason" required placeholder="Why?">
          </label>
          <div class="toolbar">
            <button type="submit" class="btn-primary">Confirm</button>
            <button type="button" class="btn-secondary" id="reasonCancelBtn">Cancel</button>
          </div>
          <p class="reason-error error" hidden></p>
        </form>`;
      const form = body.querySelector("#reasonForm");
      const errEl = body.querySelector(".reason-error");
      // Deliberately not the native `autofocus` attribute: openModal()
      // already moved focus to its own close button synchronously before
      // returning, and HTML autofocus is a one-shot per-document flag that
      // may or may not have already fired by then (e.g. depending on
      // whether the identity modal happened to autofocus earlier this
      // session) - an explicit .focus() call here is the only
      // deterministic way to land focus on this input every time.
      form.reason.focus();
      let settled = false;
      function finish(value) {
        if (settled) return;
        settled = true;
        observer.disconnect();
        if (document.getElementById("modalOverlay")) closeModal();
        resolve(value);
      }
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        const reason = form.reason.value.trim();
        if (!reason) {
          errEl.textContent = "A reason is required.";
          errEl.hidden = false;
          return;
        }
        finish(reason);
      });
      body.querySelector("#reasonCancelBtn").addEventListener("click", () => finish(null));
      // openModal()'s own Escape/backdrop/x-close paths all remove the
      // overlay directly, bypassing the cancel button above - watching for
      // that removal is what keeps this promise from hanging forever if the
      // user dismisses the modal any of those other ways instead.
      const overlay = document.getElementById("modalOverlay");
      const observer = new MutationObserver(() => {
        if (overlay && !document.body.contains(overlay)) finish(null);
      });
      observer.observe(document.body, { childList: true });
    });
  }

  // Yes/no confirmation using the app's own modal instead of the browser's
  // native confirm() - found in UAT (RET-02): a native confirm() popup
  // looks out of place next to the rest of this app's UI. Mirrors
  // promptForReason()'s exact same "resolve on any dismissal path"
  // structure, just without the reason field.
  function confirmModal(title, message, { confirmLabel = "Confirm", danger = false } = {}) {
    return new Promise((resolve) => {
      const body = openModal(title);
      body.innerHTML = `
        <p class="muted">${escapeHtml(message)}</p>
        <div class="toolbar">
          <button type="button" class="${danger ? "link-danger" : "btn-primary"}" id="confirmOkBtn">${escapeHtml(confirmLabel)}</button>
          <button type="button" class="btn-secondary" id="confirmCancelBtn">Cancel</button>
        </div>`;
      let settled = false;
      function finish(value) {
        if (settled) return;
        settled = true;
        observer.disconnect();
        if (document.getElementById("modalOverlay")) closeModal();
        resolve(value);
      }
      body.querySelector("#confirmOkBtn").addEventListener("click", () => finish(true));
      body.querySelector("#confirmCancelBtn").addEventListener("click", () => finish(false));
      body.querySelector("#confirmCancelBtn").focus();
      const overlay = document.getElementById("modalOverlay");
      const observer = new MutationObserver(() => {
        if (overlay && !document.body.contains(overlay)) finish(false);
      });
      observer.observe(document.body, { childList: true });
    });
  }

  async function handleRunDelete(runId, jobName, onDone) {
    const reason = await promptForReason(
      "Delete collection run",
      `Delete ${jobName ? `"${jobName}"` : "this collection run"}? This only removes it from ` +
      "Collection History - it does not affect already-collected data, and it can be restored later.",
    );
    if (reason === null) return;
    try {
      await apiWrite(`/api/collection-runs/${encodeURIComponent(runId)}`, "DELETE", { reason });
      showToast(`Deleted ${jobName ? `"${jobName}"` : "the run"} - restore it from Recovery any time.`);
      await onDone();
    } catch (err) {
      showErrorToast(err.message);
    }
  }

  async function handleRunRestore(runId, jobName, onDone) {
    const reason = await promptForReason(
      "Restore collection run",
      `Restore ${jobName ? `"${jobName}"` : "this collection run"} back into Collection History?`,
    );
    if (reason === null) return;
    try {
      await apiWrite(`/api/collection-runs/${encodeURIComponent(runId)}/restore`, "POST", { reason });
      showToast(`Restored ${jobName ? `"${jobName}"` : "the run"}.`);
      await onDone();
    } catch (err) {
      showErrorToast(err.message);
    }
  }

  function wireRunRowActions(container, onDone) {
    container.querySelectorAll(".run-delete-btn").forEach((btn) => {
      btn.addEventListener("click", () => handleRunDelete(btn.dataset.runId, btn.dataset.jobName, onDone));
    });
    container.querySelectorAll(".run-restore-btn").forEach((btn) => {
      btn.addEventListener("click", () => handleRunRestore(btn.dataset.runId, btn.dataset.jobName, onDone));
    });
  }

  // Scoped to one just-submitted job (not the full history - see
  // Collection History below for that) so Collect's own progress panel
  // shows only the day-by-day rows this submission is producing.
  async function loadJobProgress(jobId) {
    const container = document.getElementById("collectRunsBody");
    if (!container) return; // navigated away
    const data = await api(`/api/collection-runs?job_id=${encodeURIComponent(jobId)}&limit=500`);
    container.innerHTML = renderRunsTable(data.items, { currentJobId: jobId });
    container.querySelectorAll(".menu").forEach((menu) => setupDropdownMenu(menu));
    wireRunRowActions(container, () => loadJobProgress(jobId));
  }

  const JOB_POLL_MS = 1500;

  // Status "tab" (a real .badge, not just inline text) so a glance shows
  // whether a job is still active - Queued/Running are visually distinct
  // from the terminal Completed/Partial/Failed states onCollectSubmit()
  // renders once pollJobStatus() returns, rather than the same plain
  // sentence just changing its last word.
  const JOB_STATUS_TAB = {
    queued: ["low", "Queued"],
    running: ["medium", "Running"],
  };

  // Lets a newer submission take over the shared progress panel from an
  // older one still polling - found in UAT: the Submit button used to stay
  // disabled for a whole job's runtime (not just the POST /api/collect
  // call), so a second ad-hoc job couldn't be queued while the first was
  // still running, even though the backend queue already supports
  // multiple queued jobs (sal/jobs.py's _claim_next_queued_job() claims by
  // priority). Once the button is freed up right after queuing, two polls
  // could otherwise race and stomp on the same #collectResult/
  // #collectRunsBody elements - each poll checks this token before every
  // DOM write and quietly stops once a newer submission has superseded it.
  let collectSubmitToken = 0;

  async function pollJobStatus(jobId, out, token) {
    while (true) {
      if (collectSubmitToken !== token) return null; // superseded by a newer submission
      const { item: job } = await api(`/api/jobs/${jobId}`);
      if (collectSubmitToken !== token) return null;
      if (job.status === "queued" || job.status === "running") {
        const progress = job.last_completed_date
          ? ` &middot; through ${formatDateTime(job.last_completed_date)} so far`
          : "";
        const label = job.job_name ? ` (${escapeHtml(job.job_name)})` : "";
        const [tabCls, tabLabel] = JOB_STATUS_TAB[job.status];
        out.innerHTML = `<p class="muted">
          <span class="badge badge-${tabCls}">${tabLabel}</span>
          Job #${jobId}${label}${progress}
        </p>`;
        // A wide-range job chunks into one collection_runs row per day
        // (sal/jobs.py), each appearing/completing as SAP is called one
        // day at a time - previously this table only refreshed once at
        // the very start and once after the whole job finished, so a
        // multi-day pull looked frozen the entire time it ran, and a
        // manual refresh showed a sudden jump in rows that read as
        // duplication rather than steady progress becoming visible.
        // Refreshing on the same cadence as the status poll above shows
        // each day's row (starting "running", then "success") as it
        // actually happens.
        await loadJobProgress(jobId);
        await new Promise((resolve) => setTimeout(resolve, JOB_POLL_MS));
        continue;
      }
      return job;
    }
  }

  async function onCollectSubmit(e) {
    e.preventDefault();
    const form = e.target;
    const btn = document.getElementById("collectSubmit");
    const out = document.getElementById("collectResult");

    const payload = {
      system_id: state.systemId,
      client: form.client.value.trim(),
      dat_from: toYmd(form.dat_from.value),
      dat_to: toYmd(form.dat_to.value),
      tim_from: toHms(form.tim_from.value),
      tim_to: toHms(form.tim_to.value),
      user: form.user.value.trim(),
      transaction_code: form.transaction_code.value.trim(),
      report: form.report.value.trim(),
      instance: form.instance.value.trim(),
      msg_code: form.msg_code.value.trim(),
      job_name: form.job_name.value.trim(),
      job_description: form.job_description.value.trim(),
      job_class: form.job_class.value,
    };

    const token = ++collectSubmitToken;
    btn.disabled = true;
    out.innerHTML = '<p class="muted">Submitting job&hellip;</p>';
    let jobId = null;
    try {
      const submitted = await apiWrite("/api/collect", "POST", payload);
      jobId = submitted.job_id;
      // Re-enabled here, not in `finally` - a submission only needs to be
      // blocked for the moment of the POST itself (prevents a double-click
      // double-submitting), not for the job's whole runtime. The backend
      // queue already accepts more jobs while one is still processing.
      btn.disabled = false;
      if (collectSubmitToken !== token) return; // superseded before this one even finished queuing
      document.getElementById("collectProgressPanel").hidden = false;
      out.innerHTML = `<p class="muted">
        <span class="badge badge-low">Queued</span>
        Job #${submitted.job_id} queued&hellip; this can take a while for wide date ranges.
      </p>`;
      const job = await pollJobStatus(submitted.job_id, out, token);
      if (job === null) return; // superseded mid-poll - a newer submission now owns this panel
      if (job.status === "success") {
        out.innerHTML = `
          <p class="ok"><span class="badge badge-success">Completed</span>
          Collection complete through ${job.last_completed_date ? formatDateTime(job.last_completed_date) : ""}.
          <a href="#/dashboard">View dashboard &rarr;</a></p>`;
      } else if (job.status === "partial") {
        out.innerHTML = `
          <p class="error"><span class="badge badge-high">Partial</span>
          Stopped partway, completed through
          ${job.last_completed_date ? formatDateTime(job.last_completed_date) : "none"}: ${job.error_message ? jobErrorHtml(job.error_message, job.error_message_friendly) : "unknown error"}</p>`;
      } else {
        out.innerHTML = `
          <p class="error"><span class="badge badge-high">Failed</span>
          ${job.error_message ? jobErrorHtml(job.error_message, job.error_message_friendly) : "Collection failed."}</p>`;
      }
      await loadJobProgress(jobId);
    } catch (err) {
      if (collectSubmitToken === token) out.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
    } finally {
      btn.disabled = false;
    }
  }

  async function renderCollect() {
    $app.innerHTML = `
      <div class="page-head">
        <h1>Collect Data</h1>
        <p class="muted">
          Pull Security Audit Log events directly from
          <strong>${escapeHtml(state.systemId) || "the selected system"}</strong>,
          using the same selection criteria as SM20/RSAU_READ_LOG - the same role SM36 plays for
          defining a background job in SAP: parameters, priority, and start condition together.
          Looking for a previous pull? See <a href="#/jobs">Jobs</a>.
        </p>
      </div>
      <div class="panel">
        <h2>One-time collection</h2>
        <form id="collectForm" class="collect-form" aria-label="One-time SAP collection">
          <div class="field-grid">
            <label class="field-full">Job name
              <input type="text" name="job_name" placeholder="e.g. Weekly SU01 spot-check">
            </label>
            <label class="field-full">Description
              <input type="text" name="job_description" placeholder="What this pull is for, so it's easy to tell apart later">
            </label>
            <label>Priority
              <select name="job_class">
                <option value="A">High</option>
                <option value="B" selected>Medium</option>
                <option value="C">Low</option>
              </select>
            </label>
            <label>Date from <span class="req">*</span>
              <input type="date" name="dat_from" value="${defaultDateInput(7)}" required>
            </label>
            <label>Date to <span class="req">*</span>
              <input type="date" name="dat_to" value="${defaultDateInput(0)}" required>
            </label>
            <label>Time from
              <input type="time" name="tim_from" value="00:00">
            </label>
            <label>Time to
              <input type="time" name="tim_to" value="23:59">
            </label>
            <label>Client
              <input type="text" name="client" value="${escapeHtml(state.client)}">
            </label>
            <label>User(s)
              <input type="text" name="user" placeholder="e.g. TRAIN123_S23, TRAIN124_S23">
            </label>
            <label>Transaction code(s)
              <input type="text" name="transaction_code" placeholder="e.g. SU01, SM30">
            </label>
            <label>Report / program
              <input type="text" name="report" placeholder="e.g. RSBTCRTE">
            </label>
            <label>Instance
              <input type="text" name="instance" placeholder="e.g. ALINHANAS423_S23_00">
            </label>
            <label>Message code(s)
              <input type="text" name="msg_code" placeholder="e.g. AU1, AU2, DU9">
            </label>
          </div>
          <div class="toolbar">
            <button type="submit" class="btn-primary" id="collectSubmit">${ICON.download} Fetch from SAP</button>
            <span class="toolbar-divider" aria-hidden="true"></span>
            <div class="menu" id="eventsExportMenu">
              <button type="button" class="btn-secondary menu-trigger" aria-haspopup="true" aria-expanded="false">
                ${ICON.file} Export data ${ICON.chevronDown}
              </button>
              <div class="menu-panel" role="menu" hidden>
                <a id="exportEventsCsvBtn" role="menuitem" href="#">${ICON.file} CSV</a>
                <a id="exportEventsXlsxBtn" role="menuitem" href="#">${ICON.file} Excel (.xlsx)</a>
              </div>
            </div>
          </div>
        </form>
        <p class="panel-caption" style="margin-top:0.6rem">
          "Export data" downloads whatever SM20 events already match these fields in SAL's own
          database (no new pull from SAP) - use it right after a "Fetch from SAP" above to get the
          raw rows behind that run, not just its synced findings.
        </p>
        <div id="collectResult" style="margin-top:1rem"></div>
      </div>

      <div class="panel" style="margin-top:1.25rem" id="collectProgressPanel" hidden>
        <h2>This submission's progress</h2>
        <div id="collectRunsBody"></div>
      </div>

      <div class="panel" style="margin-top:1.25rem">
        <h2>Automatic daily collection</h2>
        <p class="callout">
          <strong>This schedule has no filters of its own - every run collects every user and every
          transaction, unfiltered.</strong> The User(s)/Transaction code(s)/etc. fields in the
          "Fetch from SAP" form above only apply to a one-time ad-hoc pull; they are never applied to
          this recurring background collection, on purpose - every detection rule above depends on
          this feed staying complete, so it can never be narrowed. What you configure below is only
          <em>how often</em> <strong>${escapeHtml(state.systemId) || "the selected system"}</strong>
          runs this same full, unfiltered pull (a fixed daily time, or every N hours) - not
          <em>what</em> it collects.
        </p>
        <form id="scheduleForm" class="field-grid" aria-label="Collection schedule">
          <label>Frequency
            <select id="scheduleType" name="interval_type">
              <option value="daily">Daily at a fixed time</option>
              <option value="interval">Every N hours</option>
            </select>
          </label>
          <label id="scheduleDailyFields" class="field-full">
            Time of day
            <input type="time" id="scheduleTime" name="anchor_time" required>
          </label>
          <div id="scheduleIntervalFields" class="field-full" hidden>
            <label for="scheduleIntervalHours">Every how many hours (1-168)</label>
            <input type="number" id="scheduleIntervalHours" name="interval_hours" min="1" max="168" required style="width:6rem; margin-top:0.3rem;">
          </div>
          <div class="toolbar field-full">
            <button type="submit" class="btn-primary">Save schedule</button>
          </div>
        </form>
        <p id="scheduleNextRun" class="muted" style="margin-top:0.75rem" aria-live="polite"></p>
        <div id="scheduleResult" style="margin-top:0.5rem" role="status"></div>
      </div>

      <div class="panel" style="margin-top:1.25rem">
        <h2>Recurring filtered collections</h2>
        <p class="panel-caption">
          Unlike the automatic daily collection above (always the full, unfiltered log), a recurring
          filtered collection pulls only the User(s)/Transaction code(s)/etc. you set below, on its
          own cadence - useful for a standing check ("daily SU01 usage for these 3 users") without
          submitting it by hand every time. Each run pulls the last 2 days (today and yesterday) -
          there's no catch-up, so a run missed while the app was down simply isn't backfilled.
        </p>
        <form id="filteredScheduleForm" class="field-grid" aria-label="Add or edit a recurring filtered collection">
          <input type="hidden" name="id" value="">
          <label class="field-full">Name <span class="req">*</span>
            <input type="text" name="name" placeholder="e.g. Daily SU01 spot-check" required>
          </label>
          <label>User(s)
            <input type="text" name="user" placeholder="e.g. TRAIN123_S23, TRAIN124_S23">
          </label>
          <label>Transaction code(s)
            <input type="text" name="transaction_code" placeholder="e.g. SU01, SM30">
          </label>
          <label>Report / program
            <input type="text" name="report">
          </label>
          <label>Instance
            <input type="text" name="instance">
          </label>
          <label>Message code(s)
            <input type="text" name="msg_code">
          </label>
          <label>Frequency
            <select id="filteredScheduleType" name="interval_type">
              <option value="daily">Daily at a fixed time</option>
              <option value="interval">Every N hours</option>
            </select>
          </label>
          <label id="filteredScheduleDailyFields" class="field-full">
            Time of day
            <input type="time" id="filteredScheduleTime" name="anchor_time" required>
          </label>
          <div id="filteredScheduleIntervalFields" class="field-full" hidden>
            <label for="filteredScheduleIntervalHours">Every how many hours (1-168)</label>
            <input type="number" id="filteredScheduleIntervalHours" name="interval_hours" min="1" max="168" style="width:6rem; margin-top:0.3rem;">
          </div>
          <div class="toolbar field-full">
            <button type="submit" class="btn-primary" id="filteredScheduleSubmit">Add recurring collection</button>
            <button type="button" class="btn-secondary" id="filteredScheduleCancelEdit" hidden>Cancel edit</button>
          </div>
        </form>
        <div id="filteredScheduleResult" style="margin-top:0.5rem" role="status"></div>
        <div id="filteredSchedulesList" style="margin-top:1rem"></div>
      </div>`;

    document.getElementById("scheduleType").addEventListener("change", toggleScheduleFields);
    document.getElementById("scheduleForm").addEventListener("submit", onScheduleSubmit);
    loadSchedule();

    document.getElementById("filteredScheduleType").addEventListener("change", toggleFilteredScheduleFields);
    document.getElementById("filteredScheduleForm").addEventListener("submit", onFilteredScheduleSubmit);
    document.getElementById("filteredScheduleCancelEdit").addEventListener("click", resetFilteredScheduleForm);
    toggleFilteredScheduleFields();
    loadFilteredSchedules();

    const collectForm = document.getElementById("collectForm");
    collectForm.addEventListener("submit", onCollectSubmit);
    setupDropdownMenu(document.getElementById("eventsExportMenu"));

    const csvLink = document.getElementById("exportEventsCsvBtn");
    const xlsxLink = document.getElementById("exportEventsXlsxBtn");
    const EVENTS_EXPORT_FIELDS = [
      "dat_from", "dat_to", "tim_from", "tim_to", "client",
      "user", "transaction_code", "report", "instance", "msg_code",
    ];
    // Kept as real <a href> links, refreshed on every field change - the
    // same reactive pattern the Findings/Collection-Runs export links
    // already use, rather than computing the URL only at click time. This
    // also downloads whatever's already in the events table matching the
    // form's current values - a query against local data, not a fresh SAP
    // pull, so it works right after a fetch (the data behind that run) or
    // independently for any previously-collected range.
    function updateEventsExportLinks() {
      if (!collectForm.dat_from.value || !collectForm.dat_to.value) {
        csvLink.href = "#";
        xlsxLink.href = "#";
        return;
      }
      const params = scopeParams({
        dat_from: toYmd(collectForm.dat_from.value),
        dat_to: toYmd(collectForm.dat_to.value),
        tim_from: toHms(collectForm.tim_from.value),
        tim_to: toHms(collectForm.tim_to.value),
        client: collectForm.client.value.trim(),
        user: collectForm.user.value.trim(),
        transaction_code: collectForm.transaction_code.value.trim(),
        report: collectForm.report.value.trim(),
        instance: collectForm.instance.value.trim(),
        msg_code: collectForm.msg_code.value.trim(),
      });
      csvLink.href = `/api/events/export?${params}&format=csv`;
      xlsxLink.href = `/api/events/export?${params}&format=xlsx`;
    }
    function guardEventsExportClick(e) {
      if (!collectForm.dat_from.value || !collectForm.dat_to.value) {
        e.preventDefault();
        showErrorToast("Date from and date to are required to export.");
      }
    }
    EVENTS_EXPORT_FIELDS.forEach((name) => {
      collectForm[name].addEventListener("input", updateEventsExportLinks);
    });
    csvLink.addEventListener("click", guardEventsExportClick);
    xlsxLink.addEventListener("click", guardEventsExportClick);
    updateEventsExportLinks();
  }

  // ---- Schedule (per-system daily-collection cadence) - embedded inside
  // ---- renderCollect() above, not its own page/tab (see the "Automatic
  // ---- daily collection" panel's own caption for why: the owner was
  // ---- confused seeing cadence controls with no visible relationship to
  // ---- what actually gets collected, so this now sits right below the
  // ---- ad-hoc form it is deliberately NOT connected to).               ----

  function toggleScheduleFields() {
    const type = document.getElementById("scheduleType").value;
    document.getElementById("scheduleDailyFields").hidden = type !== "daily";
    document.getElementById("scheduleIntervalFields").hidden = type !== "interval";
  }

  async function loadSchedule() {
    if (!state.systemId) return; // no system chosen yet
    const data = await api(`/api/systems/${encodeURIComponent(state.systemId)}/schedule`);
    const cfg = data.item;
    const typeEl = document.getElementById("scheduleType");
    if (!typeEl) return; // navigated away before this resolved
    typeEl.value = cfg.interval_type;
    const hh = String(cfg.anchor_hour ?? 2).padStart(2, "0");
    const mm = String(cfg.anchor_minute ?? 0).padStart(2, "0");
    document.getElementById("scheduleTime").value = `${hh}:${mm}`;
    document.getElementById("scheduleIntervalHours").value = cfg.interval_hours ?? 6;
    toggleScheduleFields();
    document.getElementById("scheduleNextRun").textContent = cfg.next_scheduled_run
      ? `Next scheduled run: ${formatDateTime(cfg.next_scheduled_run)}`
      : "No scheduled run currently registered for this system.";
  }

  async function onScheduleSubmit(e) {
    e.preventDefault();
    const form = e.target;
    const out = document.getElementById("scheduleResult");
    const type = form.interval_type.value;
    const payload = { interval_type: type };
    if (type === "daily") {
      const [hh, mm] = (form.anchor_time.value || "02:00").split(":");
      payload.anchor_hour = Number(hh);
      payload.anchor_minute = Number(mm);
    } else {
      payload.interval_hours = Number(form.interval_hours.value);
    }
    try {
      await apiWrite(`/api/systems/${encodeURIComponent(state.systemId)}/schedule`, "PUT", payload);
      out.innerHTML = '<p class="ok">Schedule updated.</p>';
      // Found in UAT (COL-04): the inline message above is easy to miss -
      // every other write action in the app confirms via a toast, so this
      // one should too rather than being the one silent exception.
      showToast("Schedule updated.");
      await loadSchedule();
    } catch (err) {
      out.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
      showErrorToast(err.message);
    }
  }

  // ---- Recurring filtered collections (sal/filtered_schedule.py) ----------
  //
  // Genuinely separate from the single "Automatic daily collection" above -
  // any number of saved, independently-cadenced FILTERED pulls per system.
  // One form serves both add and edit (mirroring openSystemModal()'s own
  // add/edit-in-one-modal pattern elsewhere in this app) - a hidden "id"
  // field is empty for a fresh add, and set (switching the submit button to
  // PATCH instead of POST) once a row's Edit link populates the form.

  function toggleFilteredScheduleFields() {
    const type = document.getElementById("filteredScheduleType").value;
    document.getElementById("filteredScheduleDailyFields").hidden = type !== "daily";
    document.getElementById("filteredScheduleIntervalFields").hidden = type !== "interval";
  }

  function resetFilteredScheduleForm() {
    const form = document.getElementById("filteredScheduleForm");
    if (!form) return;
    form.reset();
    form.id.value = "";
    document.getElementById("filteredScheduleSubmit").textContent = "Add recurring collection";
    document.getElementById("filteredScheduleCancelEdit").hidden = true;
    toggleFilteredScheduleFields();
  }

  function editFilteredSchedule(item) {
    const form = document.getElementById("filteredScheduleForm");
    if (!form) return;
    form.id.value = item.id;
    form.name.value = item.name || "";
    form.user.value = item.user_filter || "";
    form.transaction_code.value = item.transaction_code || "";
    form.report.value = item.report || "";
    form.instance.value = item.instance || "";
    form.msg_code.value = item.msg_code || "";
    form.interval_type.value = item.interval_type;
    if (item.interval_type === "interval") {
      document.getElementById("filteredScheduleIntervalHours").value = item.interval_hours ?? 6;
    } else {
      const hh = String(item.anchor_hour ?? 2).padStart(2, "0");
      const mm = String(item.anchor_minute ?? 0).padStart(2, "0");
      document.getElementById("filteredScheduleTime").value = `${hh}:${mm}`;
    }
    toggleFilteredScheduleFields();
    document.getElementById("filteredScheduleSubmit").textContent = "Save changes";
    document.getElementById("filteredScheduleCancelEdit").hidden = false;
    form.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function onFilteredScheduleSubmit(e) {
    e.preventDefault();
    const form = e.target;
    const out = document.getElementById("filteredScheduleResult");
    const id = form.id.value;
    const type = form.interval_type.value;
    const payload = {
      name: form.name.value.trim(),
      user: form.user.value.trim(), transaction_code: form.transaction_code.value.trim(),
      report: form.report.value.trim(), instance: form.instance.value.trim(),
      msg_code: form.msg_code.value.trim(), interval_type: type,
    };
    if (type === "daily") {
      const [hh, mm] = (form.anchor_time.value || "02:00").split(":");
      payload.anchor_hour = Number(hh);
      payload.anchor_minute = Number(mm);
    } else {
      payload.interval_hours = Number(form.interval_hours.value);
    }
    try {
      if (id) {
        await apiWrite(`/api/filtered-schedules/${encodeURIComponent(id)}?${scopeParams()}`, "PATCH", payload);
        showToast("Recurring collection updated.");
      } else {
        await apiWrite(`/api/filtered-schedules?${scopeParams()}`, "POST", payload);
        showToast("Recurring collection added.");
      }
      out.innerHTML = "";
      resetFilteredScheduleForm();
      await loadFilteredSchedules();
    } catch (err) {
      out.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
      showErrorToast(err.message);
    }
  }

  async function toggleFilteredScheduleEnabled(item) {
    try {
      await apiWrite(`/api/filtered-schedules/${encodeURIComponent(item.id)}?${scopeParams()}`, "PATCH", {
        enabled: !item.enabled,
      });
      showToast(item.enabled ? "Paused." : "Resumed.");
      await loadFilteredSchedules();
    } catch (err) {
      showErrorToast(err.message);
    }
  }

  async function deleteFilteredSchedule(item) {
    const reason = await promptForReason(
      `Remove "${item.name}"?`, "This recurring collection will stop running.",
    );
    if (reason == null) return;
    try {
      await apiWrite(`/api/filtered-schedules/${encodeURIComponent(item.id)}?${scopeParams()}`, "DELETE", { reason });
      showToast(`Removed "${item.name}".`);
      await loadFilteredSchedules();
    } catch (err) {
      showErrorToast(err.message);
    }
  }

  function filteredScheduleFrequencyText(item) {
    if (item.interval_type === "interval") return `Every ${item.interval_hours}h`;
    const hh = String(item.anchor_hour ?? 0).padStart(2, "0");
    const mm = String(item.anchor_minute ?? 0).padStart(2, "0");
    return `Daily at ${hh}:${mm}`;
  }

  function renderFilteredSchedulesList(items) {
    if (!items.length) {
      return '<p class="muted">No recurring filtered collections yet - add one above.</p>';
    }
    return `
      <table class="findings">
        <thead><tr><th>Name</th><th>Filters</th><th>Frequency</th><th>Next run</th><th>Status</th><th>Action</th></tr></thead>
        <tbody>
          ${items.map((item, i) => {
            const filterParts = [
              item.user_filter && `User: ${item.user_filter}`,
              item.transaction_code && `Tcode: ${item.transaction_code}`,
              item.report && `Report: ${item.report}`,
              item.instance && `Instance: ${item.instance}`,
              item.msg_code && `Msg: ${item.msg_code}`,
            ].filter(Boolean);
            return `
            <tr>
              <td>${escapeHtml(item.name)}</td>
              <td class="muted">${escapeHtml(filterParts.join(", ") || "(no filters set)")}</td>
              <td>${escapeHtml(filteredScheduleFrequencyText(item))}</td>
              <td class="muted">${item.next_scheduled_run ? escapeHtml(formatDateTime(item.next_scheduled_run)) : "-"}</td>
              <td><span class="badge badge-${item.enabled ? "success" : "low"}">${item.enabled ? "Active" : "Paused"}</span></td>
              <td>
                <button type="button" class="btn-secondary btn-sm" data-edit="${i}">Edit</button>
                <button type="button" class="btn-secondary btn-sm" data-toggle="${i}">${item.enabled ? "Pause" : "Resume"}</button>
                <button type="button" class="link-danger" data-remove="${i}">${ICON.trash} Remove</button>
              </td>
            </tr>`;
          }).join("")}
        </tbody>
      </table>`;
  }

  async function loadFilteredSchedules() {
    const container = document.getElementById("filteredSchedulesList");
    if (!container || !state.systemId) return;
    const data = await api(`/api/filtered-schedules?${scopeParams()}`);
    if (!document.getElementById("filteredSchedulesList")) return; // navigated away mid-fetch
    container.innerHTML = renderFilteredSchedulesList(data.items);
    container.querySelectorAll("[data-edit]").forEach((btn) => {
      btn.addEventListener("click", () => editFilteredSchedule(data.items[Number(btn.dataset.edit)]));
    });
    container.querySelectorAll("[data-toggle]").forEach((btn) => {
      btn.addEventListener("click", () => toggleFilteredScheduleEnabled(data.items[Number(btn.dataset.toggle)]));
    });
    container.querySelectorAll("[data-remove]").forEach((btn) => {
      btn.addEventListener("click", () => deleteFilteredSchedule(data.items[Number(btn.dataset.remove)]));
    });
  }

  // ---- Identity (attribution only, not access control) --------------------
  //
  // SAL records who searches, collects and changes data so activity can be
  // reconstructed later (S1-11). This display name is how that "who" is
  // captured - it is not a password and does not gate access to anything.

  function renderIdentityOverlay(allowClose) {
    const overlay = document.createElement("div");
    overlay.id = "identityOverlay";
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true" aria-label="Who are you?">
        <div class="modal-head">
          <h2>Who are you?</h2>
          ${allowClose ? '<button type="button" class="modal-close" aria-label="Close">&times;</button>' : ""}
        </div>
        <div class="modal-body">
          <p class="muted">
            SAL records who searches, collects and changes data so activity
            can be reconstructed later. This name is for attribution only
            &mdash; it is not a password or an access control.
          </p>
          <form id="identityForm" class="catalogue-add-form">
            <input type="text" name="name" placeholder="e.g. Rohan Parate" required autofocus>
            <button type="submit" class="btn-primary">Continue</button>
          </form>
          <p class="identity-error error" hidden></p>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    if (allowClose) {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) overlay.remove();
      });
      overlay.querySelector(".modal-close").addEventListener("click", () => overlay.remove());
    }
    return overlay;
  }

  function promptForIdentity(allowClose = false) {
    return new Promise((resolve) => {
      const overlay = renderIdentityOverlay(allowClose);
      const form = overlay.querySelector("#identityForm");
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const errEl = overlay.querySelector(".identity-error");
        errEl.hidden = true;
        const name = form.name.value.trim();
        if (!name) return;
        try {
          const data = await apiWrite("/api/identity", "POST", { name });
          overlay.remove();
          resolve(data.actor);
        } catch (err) {
          errEl.textContent = err.message;
          errEl.hidden = false;
        }
      });
    });
  }

  function renderActorLabel() {
    const el = document.getElementById("actorLabel");
    if (!el) return;
    el.textContent = state.actor ? `Acting as: ${state.actor}` : "";
  }

  async function ensureIdentity() {
    const data = await api("/api/identity");
    state.actor = data.actor || (await promptForIdentity(false));
    renderActorLabel();

    const label = document.getElementById("actorLabel");
    if (!label) return;
    const changeIdentity = async () => {
      const newActor = await promptForIdentity(true);
      if (newActor) {
        state.actor = newActor;
        renderActorLabel();
      }
    };
    label.addEventListener("click", changeIdentity);
    label.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        changeIdentity();
      }
    });
  }

  // ---- Activity view (S1-11 application audit trail) ----------------------

  // Friendly labels for every audit.record() call site in sal/web/api.py -
  // kept as a lookup (not the source of truth for *which* actions exist,
  // see renderActivity() below, which asks the server for that) so a known
  // action still gets a readable label even though the dropdown itself is
  // populated dynamically.
  const AUDIT_ACTION_LABELS = {
    view_dashboard: "Viewed dashboard",
    findings_search: "Searched findings",
    findings_export: "Exported findings",
    findings_sync: "Synced findings",
    finding_dispose: "Disposed finding",
    collect: "Ran collection",
    connection_test: "Tested connection",
    catalogue_add: "Added catalogue entry",
    catalogue_remove: "Removed catalogue entry",
    system_add: "Added system",
    system_update: "Updated system",
    system_remove: "Removed system",
    schedule_update: "Updated schedule",
    audit_config_check: "Checked audit config (SM19)",
    role_context_refresh: "Refreshed role context",
    role_context_user_lookup: "Looked up user's role context",
    retention_purge: "Ran retention purge",
    rules_catalog_export: "Exported rules catalog",
    whitelist_add: "Added whitelist entry",
    whitelist_remove: "Removed whitelist entry",
    job_delete: "Deleted job",
    job_restore: "Restored job",
    collection_run_delete: "Deleted collection run",
    collection_run_restore: "Restored collection run",
    collection_runs_export: "Exported collection runs",
    events_export: "Exported events",
    credential_view: "Viewed stored credential",
    credential_set: "Saved stored credential",
    credential_remove: "Removed stored credential",
  };

  // Falls back to a humanized version of the raw action string for
  // anything not yet in the label map above - so a future audit.record()
  // call site that forgets to add a label here still reads as something
  // sensible instead of a blank option, rather than needing this map kept
  // in lockstep with the backend by hand.
  function humanizeAuditAction(action) {
    return action.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
  }

  function auditActionLabel(action) {
    return AUDIT_ACTION_LABELS[action] || humanizeAuditAction(action);
  }

  // Returns an already-escaped HTML string, not plain text - callers must
  // NOT run this back through escapeHtml() themselves (that would
  // double-escape and print the finding_key link as literal markup).
  // finding_key gets special treatment: requested directly ("it logs the
  // activity and gives there finding key, now if I want to know what
  // finding that was ... how to do that") - a raw finding_key on its own
  // is an opaque SHA-256 hash with no way back to the actual finding, so
  // any params blob carrying one becomes a link straight to it
  // (#/findings?finding_key=..., a new exact-match lookup - see
  // findings.list_findings()'s own docstring for why it deliberately
  // bypasses the current system/client scope for this one case) instead
  // of dumping the raw hash as inert text.
  function summarizeParams(paramsJson) {
    if (!paramsJson) return "";
    let obj;
    try {
      obj = JSON.parse(paramsJson);
    } catch {
      return escapeHtml(paramsJson);
    }
    const parts = [];
    for (const [k, v] of Object.entries(obj)) {
      if (v === null || v === undefined || v === "") continue;
      if (k === "finding_key" && typeof v === "string") {
        const short = escapeHtml(v.length > 12 ? `${v.slice(0, 12)}…` : v);
        parts.push(
          `<a href="#/findings?finding_key=${encodeURIComponent(v)}" title="Open this finding">` +
          `View finding (${short}) &rarr;</a>`,
        );
        continue;
      }
      parts.push(`${escapeHtml(k)}=${escapeHtml(String(v))}`);
    }
    return parts.join(", ");
  }

  function renderActivityTable(items) {
    if (!items.length) {
      return '<p class="muted">No activity recorded yet.</p>';
    }
    const rows = items
      .map((a) => {
        const outcomeCls = a.outcome === "ok" ? "success" : "high";
        const scope = [a.source_system, a.client].filter(Boolean).join(" / ");
        const countSuffix = a.result_count != null
          ? ` <span class="muted">(${a.result_count})</span>` : "";
        return `
        <tr>
          <td>${escapeHtml((a.occurred_at || "").slice(0, 19).replace("T", " "))}</td>
          <td>${escapeHtml(a.actor)}</td>
          <td>${escapeHtml(auditActionLabel(a.action))}</td>
          <td>${escapeHtml(scope)}</td>
          <td>${summarizeParams(a.params_json)}${countSuffix}</td>
          <td><span class="badge badge-${outcomeCls}">${escapeHtml(a.outcome)}</span></td>
        </tr>`;
      })
      .join("");
    return `
      <table class="findings">
        <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>System/Client</th><th>Details</th><th>Outcome</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  async function renderActivity() {
    $app.innerHTML = `
      <div class="page-head"><h1>Activity</h1></div>
      <div class="filter-bar">
        <input type="text" id="aActor" placeholder="Filter by actor">
        <select id="aAction">
          <option value="">All actions</option>
        </select>
        <span id="aCount" class="muted"></span>
      </div>
      <div id="activityBody">${skeleton(300)}</div>`;

    const $actor = document.getElementById("aActor");
    const $action = document.getElementById("aAction");

    // Populated from what has actually been recorded (GET /api/audit/actions)
    // rather than a hardcoded list here - found in a user report that a real,
    // working action (job_delete) had silently become unfilterable because
    // this list was never updated after it was added. Self-maintaining going
    // forward: any new audit.record() action shows up the first time it fires.
    const { actions } = await api("/api/audit/actions");
    actions.forEach((key) => {
      const opt = document.createElement("option");
      opt.value = key;
      opt.textContent = auditActionLabel(key);
      $action.appendChild(opt);
    });

    // Found in a UAT report: selecting a new Action sometimes appeared to
    // do nothing. Root cause - this function is invoked from a bare
    // change/debounced-input callback, never awaited by anything, so a
    // rejected api() call (a transient network blip, or exactly the
    // database-lock 500 fixed alongside this) had nowhere to go: the
    // promise rejection was silently swallowed by the browser and the
    // table just stayed on its old data with zero visible feedback.
    async function load() {
      try {
        const params = scopeParams({
          actor: $actor.value.trim(),
          action: $action.value,
          limit: 200,
        });
        const data = await api(`/api/audit?${params}`);
        document.getElementById("aCount").textContent =
          `${data.items.length} of ${data.total} entr${data.total === 1 ? "y" : "ies"}`;
        document.getElementById("activityBody").innerHTML = renderActivityTable(data.items);
      } catch (err) {
        const body = document.getElementById("activityBody");
        if (body) body.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
      }
    }

    let debounceHandle;
    $actor.addEventListener("input", () => {
      clearTimeout(debounceHandle);
      debounceHandle = setTimeout(load, 300);
    });
    $action.addEventListener("change", load);
    await load();
  }

  // ---- Systems view (SAP system/environment registry) ---------------------
  //
  // renderSystemFormBody() below also carries an optional RFC user/password
  // pair (2026-09-16, Password Manager) that saves to the central
  // credential store (sal/credentials.py), not to this registry - the
  // systems table itself still has no password column. See that module's
  // docstring for the full reasoning; .env remains supported unchanged for
  // any system that hasn't had a password saved centrally.

  const SYSTEM_ENVIRONMENTS = ["Development", "Quality", "Production", "Sandbox"];

  function renderSystemFormBody(system) {
    const isEdit = !!system;
    const envOptions = SYSTEM_ENVIRONMENTS
      .map((env) => `<option value="${escapeHtml(env)}" ${system && system.environment === env ? "selected" : ""}>${escapeHtml(env)}</option>`)
      .join("");
    return `
      <form id="systemForm" class="field-grid">
        <label>System ID <span class="req">*</span>
          <input type="text" name="system_id" class="mono" value="${escapeHtml(system?.system_id || "")}"
            ${isEdit ? "disabled" : "required"} maxlength="20" placeholder="e.g. S23" style="text-transform:uppercase">
        </label>
        <label>Environment <span class="req">*</span>
          <select name="environment" required>${envOptions}</select>
        </label>
        <label>Application server (ashost) <span class="req">*</span>
          <input type="text" name="ashost" value="${escapeHtml(system?.ashost || "")}" required placeholder="e.g. sapapp01.example.com">
        </label>
        <label>System number (sysnr) <span class="req">*</span>
          <input type="text" name="sysnr" value="${escapeHtml(system?.sysnr || "")}" required maxlength="2" placeholder="e.g. 00">
        </label>
        <label>Client <span class="req">*</span>
          <input type="text" name="client" value="${escapeHtml(system?.client || "")}" required maxlength="3" placeholder="e.g. 100">
        </label>
        <label class="field-full">Description
          <input type="text" name="description" value="${escapeHtml(system?.description || "")}" placeholder="e.g. Production ECC">
        </label>
        <label>RFC user
          <input type="text" name="rfc_user" autocomplete="off" placeholder="e.g. SAL_RFC">
        </label>
        <label>Password
          <input type="password" name="password" autocomplete="new-password">
        </label>
        <p class="callout field-full">
          RFC user/password above are optional and save to the central credential store (Password
          Manager, linked from Home) &mdash; leave both blank to keep using <code>.env</code> instead
          (set <code>SAL_SAP_&lt;SYSTEM_ID&gt;_PASSWD</code> there and restart the app). Either way
          works; a password saved here takes over for this system as soon as you save.
        </p>
        <p class="system-form-error error field-full" hidden></p>
        <button type="submit" class="btn-primary field-full">${isEdit ? "Save changes" : "Add system"}</button>
      </form>`;
  }

  function openSystemModal(system) {
    const isEdit = !!system;
    const body = openModal(isEdit ? `Edit system: ${system.system_id}` : "Add system");
    body.innerHTML = renderSystemFormBody(system);
    const form = body.querySelector("#systemForm");
    const errEl = body.querySelector(".system-form-error");

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      errEl.hidden = true;
      const systemId = isEdit ? system.system_id : form.system_id.value.trim().toUpperCase();
      const payload = {
        environment: form.environment.value,
        ashost: form.ashost.value.trim(),
        sysnr: form.sysnr.value.trim(),
        client: form.client.value.trim(),
        description: form.description.value.trim(),
      };
      if (!isEdit && !systemId) {
        errEl.textContent = "System ID is required";
        errEl.hidden = false;
        return;
      }
      const rfcUser = form.rfc_user.value.trim();
      const password = form.password.value;
      const submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      try {
        const result = isEdit
          ? await apiWrite(`/api/systems/${encodeURIComponent(systemId)}`, "PATCH", payload)
          : await apiWrite("/api/systems", "POST", { system_id: systemId, ...payload });
        // Optional - saved to the central credential store only if BOTH
        // fields were filled in; leaving both blank keeps .env (or a
        // previously-saved central credential) untouched, on purpose.
        if (rfcUser && password) {
          await apiWrite(`/api/credentials/${encodeURIComponent(systemId)}`, "POST", {
            rfc_user: rfcUser, password,
          });
        }
        closeModal();
        applySystemsUpdate(result.items || []);
        const notice = document.getElementById("homeNotice");
        if (notice) {
          notice.innerHTML = (!isEdit && !(rfcUser && password))
            ? `<p class="callout">System <strong>${escapeHtml(systemId)}</strong> added.
                Set <code>SAL_SAP_${escapeHtml(systemId)}_PASSWD</code> in <code>.env</code>
                (or save a password for it from the <a href="#/credentials">Password Manager</a>)
                and restart the app before this system can connect.</p>`
            : "";
        }
        if (isEdit) showToast(`System "${systemId}" updated.`);
        else if (rfcUser && password) showToast(`System "${systemId}" added, with its password saved centrally.`);
      } catch (err) {
        errEl.textContent = err.message;
        errEl.hidden = false;
        submitBtn.disabled = false;
      }
    });
  }

  // ---- Home (system picker + registry management) --------------------------
  //
  // Replaces the old standalone Systems page: picking a system here is how
  // you enter its workspace (Dashboard/Findings/Jobs/...), and add/edit/
  // remove now lives on each card instead of a separate admin page - see
  // Docs/CHANGELOG.md for why (folded in rather than kept alongside the
  // shellbar quick-switch, which stays for switching without leaving a page).

  // Fiori-style app-launcher tiles: fixed square footprint, title/subtitle
  // at top, a representative icon anchored bottom-right (SAP's own "static
  // tile" layout), and a corner "more actions" popover instead of a
  // persistent Edit/Remove button row - this is an SAP-specific console, so
  // its own design language reads as more at-home here than a generic web
  // card grid. The popover reuses setupDropdownMenu() (built for the
  // Findings page's Export menu) rather than a bespoke mechanism.
  // Environment -> the CSS custom property naming that tier's accent color
  // (style.css's --env-production/--env-sandbox/--env-quality/
  // --env-development - deliberately distinct hues from the severity
  // palette). Falls back to Sandbox's color for an unrecognized value,
  // matching SYSTEM_ENVIRONMENTS' own "unknown environment -> Sandbox"
  // convention used elsewhere (e.g. renderSystemSelector()).
  const ENV_COLOR_VAR = {
    Development: "--env-development",
    Quality: "--env-quality",
    Production: "--env-production",
    Sandbox: "--env-sandbox",
  };

  function renderHomeCard(s) {
    const envVar = ENV_COLOR_VAR[s.environment] || "--env-sandbox";
    // Found in UAT (HOME-01): this icon already carried role="img" +
    // aria-label (so screen readers always explained it), but relied on
    // the native title="" tooltip for sighted mouse users - which most
    // browsers delay by a second or more, easy to miss on a quick hover.
    // data-tooltip (below, CSS-driven, appears instantly) replaces that;
    // tabindex="0" also lets a keyboard user reach it directly rather
    // than needing a mouse at all.
    const flag = s.has_credentials
      ? ""
      : `<span class="fiori-tile-flag" role="img" tabindex="0" aria-label="Credentials missing - set SAL_SAP_${escapeHtml(s.system_id)}_PASSWD and other required vars in .env" data-tooltip="Credentials not maintained - set SAL_SAP_${escapeHtml(s.system_id)}_PASSWD (and other required vars) in .env">${ICON.warning}</span>`;
    return `
      <div class="fiori-tile" data-system-id="${escapeHtml(s.system_id)}" style="--env-c:var(${envVar})">
        <button type="button" class="fiori-tile-select"
          aria-label="Open ${escapeHtml(s.description || s.system_id)} (${escapeHtml(s.system_id)}, client ${escapeHtml(s.client)})">
          <span class="fiori-tile-icon" aria-hidden="true">${ICON.server}</span>
          <span class="fiori-tile-title">${escapeHtml(s.description || s.system_id)}</span>
          <span class="fiori-tile-subtitle mono">${escapeHtml(s.system_id)} &middot; client ${escapeHtml(s.client)}</span>
          <span class="fiori-tile-pill">${escapeHtml(s.environment)}</span>
        </button>
        ${flag}
        <div class="menu fiori-tile-menu">
          <button type="button" class="tile-menu-trigger menu-trigger" aria-haspopup="true" aria-expanded="false"
            aria-label="More actions for ${escapeHtml(s.system_id)}" title="More actions">
            ${ICON.moreVertical}
          </button>
          <div class="menu-panel" role="menu" hidden>
            <button type="button" role="menuitem" class="sys-edit-btn">${ICON.pencil} Edit</button>
            <button type="button" role="menuitem" class="sys-remove-btn">${ICON.trash} Remove</button>
          </div>
        </div>
      </div>`;
  }

  function renderHomeCards(items) {
    const byEnv = new Map();
    items.forEach((s) => {
      const env = SYSTEM_ENVIRONMENTS.includes(s.environment) ? s.environment : "Sandbox";
      if (!byEnv.has(env)) byEnv.set(env, []);
      byEnv.get(env).push(s);
    });
    const sections = SYSTEM_ENVIRONMENTS
      .filter((env) => byEnv.has(env))
      .map((env) => `
        <section class="system-section">
          <h2 class="sidenav-section">${escapeHtml(env)}</h2>
          <div class="tile-grid">${byEnv.get(env).map(renderHomeCard).join("")}</div>
        </section>`)
      .join("");
    const emptyNote = items.length
      ? ""
      : '<p class="muted">No systems configured yet - add one below to get started.</p>';
    return `
      ${sections}
      ${emptyNote}
      <section class="system-section">
        <h2 class="sidenav-section">Management</h2>
        <div class="tile-grid">
          <div class="fiori-tile">
            <a href="#/credentials" class="fiori-tile-select" aria-label="Password Manager - manage saved SAP credentials">
              <span class="fiori-tile-icon" aria-hidden="true">${ICON.list}</span>
              <span class="fiori-tile-title">Password Manager</span>
              <span class="fiori-tile-subtitle">Manage saved SAP credentials</span>
            </a>
          </div>
          <div class="fiori-tile fiori-tile-add">
            <button type="button" class="fiori-tile-select" id="addSystemBtn" aria-label="Add system">
              ${ICON.plus}
              <span class="fiori-tile-title">Add system</span>
            </button>
          </div>
        </div>
      </section>`;
  }

  function attachHomeCardHandlers(items) {
    document.querySelectorAll(".fiori-tile[data-system-id] .fiori-tile-select").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.closest(".fiori-tile").dataset.systemId;
        const sys = items.find((s) => s.system_id === id);
        if (!sys) return;
        selectSystem(sys.system_id, sys.client);
        location.hash = "#/dashboard";
      });
    });
    document.querySelectorAll(".fiori-tile-menu").forEach((menu) => setupDropdownMenu(menu));
    document.querySelectorAll(".sys-edit-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.closest(".fiori-tile").dataset.systemId;
        const sys = items.find((s) => s.system_id === id);
        if (sys) openSystemModal(sys);
      });
    });
    document.querySelectorAll(".sys-remove-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.closest(".fiori-tile").dataset.systemId;
        const ok = await confirmModal(
          "Remove system", `Remove system ${id}? This does not delete data already collected for it.`,
          { confirmLabel: "Remove", danger: true },
        );
        if (!ok) return;
        btn.disabled = true;
        try {
          const result = await apiWrite(`/api/systems/${encodeURIComponent(id)}`, "DELETE");
          const notice = document.getElementById("homeNotice");
          if (notice) notice.innerHTML = "";
          showToast(`System "${id}" removed.`);
          applySystemsUpdate(result.items || []);
        } catch (err) {
          btn.disabled = false;
          const notice = document.getElementById("homeNotice");
          if (notice) notice.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
        }
      });
    });
    const addBtn = document.getElementById("addSystemBtn");
    if (addBtn) addBtn.addEventListener("click", () => openSystemModal(null));
  }

  // Shared by the initial page load and every add/edit/remove - renders from
  // an items array the caller already has (either the GET response or the
  // items a write endpoint returns), so mutations never need a second
  // round-trip just to refresh the list.
  function applySystemsUpdate(items) {
    syncSystemsState(items);
    const body = document.getElementById("homeBody");
    if (!body) return; // navigated away
    body.innerHTML = renderHomeCards(items);
    attachHomeCardHandlers(items);
  }

  async function renderHome() {
    $app.innerHTML = `
      <div class="page-head">
        <h1>Choose a system</h1>
        <p class="muted">Pick a configured SAP system to open its dashboard, findings, and collection tools.</p>
      </div>
      <div id="homeNotice" aria-live="polite"></div>
      <div id="homeBody">${skeleton(150)}${skeleton(150)}</div>`;

    const data = await api("/api/systems");
    applySystemsUpdate(data.systems || []);
  }

  // ---- Password Manager (sal/credentials.py) -------------------------------
  //
  // Requested directly, 2026-09-16 ("Create a similar page for password
  // manager on the home screen besides the systems a central repository
  // that will store passwords for all the systems"). Reachable from Home
  // (see the link above) without a system having to be chosen first - same
  // reasoning route()'s own systemChosen-gate exemption uses.

  function credentialSourceBadge(source) {
    if (source === "central") return `<span class="badge badge-success">Central store</span>`;
    if (source === "env") return `<span class="badge badge-low">.env</span>`;
    return `<span class="badge badge-high">Not configured</span>`;
  }

  async function renderCredentials() {
    $app.innerHTML = `
      <div class="page-head">
        <h1>Password Manager</h1>
        <p class="muted">
          A central, encrypted repository for SAP system passwords - an alternative to maintaining
          them by hand in .env. A system with nothing saved here keeps working exactly as before,
          reading its credentials from .env; saving a password here takes over for that system going
          forward. <a href="#/home">&larr; Back to systems</a>
        </p>
      </div>
      <div class="panel">
        <div id="credentialsBody">${skeleton(220)}</div>
      </div>`;

    async function load() {
      const container = document.getElementById("credentialsBody");
      try {
        const data = await api("/api/credentials");
        if (!document.getElementById("credentialsBody")) return; // navigated away mid-fetch
        if (!data.items.length) {
          container.innerHTML = `<p class="muted">No systems registered yet.
            <a href="#/home">Add one from the systems page</a> first.</p>`;
          return;
        }
        container.innerHTML = `
          <table class="findings">
            <thead><tr><th>System</th><th>Environment</th><th>Credential source</th><th>Action</th></tr></thead>
            <tbody>${data.items.map((item) => `
              <tr>
                <td>${escapeHtml(item.description || item.system_id)}
                  <span class="muted mono">(${escapeHtml(item.system_id)})</span></td>
                <td>${escapeHtml(item.environment)}</td>
                <td>${credentialSourceBadge(item.source)}</td>
                <td>
                  <button type="button" class="btn-secondary btn-sm cred-edit-btn"
                    data-system-id="${escapeHtml(item.system_id)}">
                    ${item.source === "central" ? "View / edit" : "Set password"}
                  </button>
                  ${item.source === "central" ? `
                    <button type="button" class="link-danger cred-remove-btn"
                      data-system-id="${escapeHtml(item.system_id)}">${ICON.trash} Remove</button>
                  ` : ""}
                </td>
              </tr>`).join("")}
            </tbody>
          </table>`;

        container.querySelectorAll(".cred-edit-btn").forEach((btn) => {
          btn.addEventListener("click", () => openCredentialModal(btn.dataset.systemId, load));
        });
        container.querySelectorAll(".cred-remove-btn").forEach((btn) => {
          btn.addEventListener("click", async () => {
            const systemId = btn.dataset.systemId;
            const reason = await promptForReason(
              `Remove the stored password for ${systemId}?`,
              `${systemId} will fall back to .env, if configured there - otherwise it won't be able to connect until a password is set again.`,
            );
            if (reason === null) return;
            try {
              await apiWrite(`/api/credentials/${encodeURIComponent(systemId)}`, "DELETE", { reason });
              showToast(`Removed the stored password for ${systemId}.`);
              await load();
            } catch (err) {
              showErrorToast(err.message);
            }
          });
        });
      } catch (err) {
        container.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
      }
    }

    await load();
  }

  // Shared by the Password Manager's "Set password"/"View / edit" buttons
  // and the Add/Edit System modal's own optional password field (see
  // openSystemModal()) - one modal, two entry points, so the two "set a
  // system's password" flows this feature has can't drift apart.
  async function openCredentialModal(systemId, onSaved) {
    let existing = null;
    try {
      existing = await api(`/api/credentials/${encodeURIComponent(systemId)}`);
    } catch {
      existing = null; // nothing stored yet (404) - fine, the form just starts blank
    }

    const body = openModal(`Password for ${systemId}`);
    body.innerHTML = `
      <p class="muted" id="credModalNote"></p>
      <form id="credentialForm" class="field-grid">
        <label class="field-full">RFC user
          <input type="text" name="rfc_user" required value="${escapeHtml(existing?.rfc_user || "")}"
            autocomplete="off">
        </label>
        <label class="field-full">Password
          <input type="text" name="password" required autocomplete="new-password"
            value="${escapeHtml(existing?.password || "")}" spellcheck="false">
        </label>
        <div class="toolbar field-full">
          <button type="submit" class="btn-primary">Save</button>
        </div>
      </form>`;
    // type="text", not "password" (unmasked, on purpose) - matching the
    // note below and the project owner's own explicit choice for this
    // whole feature: viewable, not write-only. Masking-with-the-value-
    // still-copyable would be friction with no real security benefit
    // here, and previously left this field blank even when `existing`
    // held the real decrypted value fetched (and audit-logged as
    // credential_view) moments earlier - security-reviewer, MEDIUM: that
    // meant every "View / edit" click logged a reveal that the UI never
    // actually showed.
    document.getElementById("credModalNote").textContent = existing
      ? `Last updated by ${existing.updated_by} on ${formatDateTime(existing.updated_at)}. The password above is shown in full - anyone who can open this page can view it, since this store has no access control of its own beyond the tool's normal attribution.`
      : "No password stored centrally for this system yet - it's currently reading from .env, if configured there.";

    document.getElementById("credentialForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const form = e.target;
      const btn = form.querySelector("button[type=submit]");
      btn.disabled = true;
      try {
        await apiWrite(`/api/credentials/${encodeURIComponent(systemId)}`, "POST", {
          rfc_user: form.rfc_user.value.trim(),
          password: form.password.value,
        });
        showToast(`Saved the password for ${systemId}.`);
        closeModal();
        if (onSaved) await onSaved();
      } catch (err) {
        showErrorToast(err.message);
      } finally {
        btn.disabled = false;
      }
    });
  }

  // ---- Jobs view (collection job queue/history) ----------------------------

  const JOB_STATUS_BADGE = { queued: "low", running: "medium", success: "success", partial: "medium", error: "high" };
  const JOB_MODE_BADGE = { scheduled: "low", adhoc: "medium", filtered_scheduled: "high" };
  // SM36/SM37 parity: SAP's own Job Class vocabulary (A=High, B=Medium,
  // C=Low) - also the queue order the single worker thread claims by
  // (see sal/jobs.py's _claim_next_queued_job()), not just a display label.
  const JOB_CLASS_LABEL = { A: "High", B: "Medium", C: "Low" };
  const JOB_CLASS_BADGE = { A: "high", B: "medium", C: "low" };

  // Elapsed wall-clock time between two ISO timestamps, or "-" if either is
  // missing - used for SM37's own "Duration" (started->finished) and
  // "Delay" (submitted->started, i.e. queue wait time) columns.
  function formatElapsed(fromIso, toIso) {
    if (!fromIso || !toIso) return "-";
    const seconds = Math.round((new Date(toIso).getTime() - new Date(fromIso).getTime()) / 1000);
    if (!Number.isFinite(seconds) || seconds < 0) return "-";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }

  function formatEta(seconds) {
    if (seconds == null) return "-";
    const total = Math.max(0, Math.round(seconds));
    const m = Math.floor(total / 60);
    const s = total % 60;
    return m > 0 ? `~${m}m ${s}s remaining` : `~${s}s remaining`;
  }

  function jobProgressHtml(job) {
    if (job.days_total == null) return '<span class="muted">-</span>';
    // Ad-hoc jobs run their whole date range as a single collect_and_store()
    // call now (not chunked by day - see sal/jobs.py's module docstring),
    // so days_total is always 1 for them regardless of how wide a range
    // was requested. An "X of 1 day" bar would misleadingly suggest
    // day-by-day progress that doesn't happen here, so show a plain
    // running/done indicator instead; the real per-day bar still applies
    // to scheduled jobs, which do still chunk.
    if (job.mode === "adhoc") {
      // Branch on job.status, not days_completed - a failed/partial job
      // never sets days_completed either, so keying off that alone showed
      // "Running..." forever right next to a Status badge that already
      // said "error" (found by python-reviewer). Anything else terminal
      // (queued/partial/error) shows "-" instead of duplicating what the
      // Status column already states authoritatively.
      if (job.status === "success") return '<span class="ok">Done</span>';
      if (job.status === "running") return '<span class="muted">Running&hellip;</span>';
      return '<span class="muted">-</span>';
    }
    const completed = job.days_completed || 0;
    const pct = job.days_total ? Math.round((completed / job.days_total) * 100) : 0;
    return `
      <div class="job-progress">
        <span class="job-progress-track"><span class="bar-fill" style="width:${pct}%"></span></span>
        <span>${completed} of ${job.days_total} day${job.days_total === 1 ? "" : "s"}</span>
      </div>`;
  }

  // job_name/job_description are optional (added after earlier jobs already
  // existed, and still optional going forward) - fall back to a plain
  // mode-based label so older/unnamed rows still read sensibly rather than
  // showing a blank cell.
  // jobId is optional (Collection History rows predating the job_id link,
  // or from scripts/collect_sm20.py's CLI backfill path, have none) - only
  // linkify to the job-detail page when there's an actual job to show.
  // Opens in a new tab (rel="noopener" - the new tab must not get a handle
  // back to window.opener) so clicking through from a long Jobs/Collection
  // History list doesn't lose your place in it.
  function jobLabelHtml(j, jobId) {
    const fallback = j.mode === "scheduled" ? "Daily scheduled collection"
      : j.mode === "filtered_scheduled" ? "Recurring filtered collection" : "Ad-hoc collection";
    const name = j.job_name
      ? escapeHtml(j.job_name)
      : `<span class="muted">${fallback}</span>`;
    const description = j.job_description
      ? `<br><span class="muted">${escapeHtml(j.job_description)}</span>`
      : "";
    const label = `<strong>${name}</strong>${description}`;
    return jobId != null
      ? `<a href="#/jobs/${encodeURIComponent(jobId)}" target="_blank" rel="noopener">${label}</a>`
      : label;
  }

  // Prepends a short, analyst-facing explanation + suggested next step
  // (error_message_friendly - see sal/friendly_errors.py) above the raw
  // technical error text, when the backend recognized the error; falls
  // back to the raw text alone otherwise. Never replaces the raw text -
  // an engineer/admin still needs it. Used everywhere a job/run's
  // error_message is shown (Jobs, Job Detail, Collect's live progress
  // panel, Recovery).
  function jobErrorHtml(errorMessage, friendly) {
    if (!errorMessage) return "";
    if (!friendly) return escapeHtml(errorMessage);
    return `<strong>${escapeHtml(friendly.explanation)}</strong> ${escapeHtml(friendly.suggestion)}` +
      `<br><span class="muted">Technical detail: ${escapeHtml(errorMessage)}</span>`;
  }

  // Same content as jobErrorHtml() above, flattened to plain text for a
  // native title/aria-label attribute (the Status badge's compact warning
  // glyph - see JOB_COLUMNS below - has no room for the <strong>/<br> markup).
  function jobErrorTooltipText(errorMessage, friendly) {
    if (!errorMessage) return "";
    return friendly
      ? `${friendly.explanation} ${friendly.suggestion} (Technical detail: ${errorMessage})`
      : errorMessage;
  }

  // Ad-hoc jobs are one-time pulls - no recurring cadence applies. A
  // scheduled job's frequency reflects its system's *current* Schedule-tab
  // setting (schedule_settings holds one live row per system, not a
  // per-job historical snapshot) - the same simplification
  // next_scheduled_run elsewhere on this page already makes.
  function formatJobFrequency(j) {
    if (j.mode !== "scheduled") return '<span class="muted">One-time</span>';
    if (j.schedule_interval_type === "interval") {
      return `Every ${j.schedule_interval_hours}h`;
    }
    // No "?? 0" fallback here on purpose (found in review): 00:00 is itself
    // a legitimate configured time, so silently defaulting a missing value
    // to it would make a future data problem (get_schedule() ever
    // returning a null anchor for 'daily') visually indistinguishable from
    // "really scheduled for midnight" instead of surfacing as unexpected.
    if (j.schedule_anchor_hour == null || j.schedule_anchor_minute == null) {
      return '<span class="muted">Daily (time unknown)</span>';
    }
    const hh = String(j.schedule_anchor_hour).padStart(2, "0");
    const mm = String(j.schedule_anchor_minute).padStart(2, "0");
    return `Daily at ${hh}:${mm}`;
  }

  // Each job is its own separate, flat row - no nested/expandable runs
  // (explicitly requested: keep jobs separate rather than grouped with
  // the run(s) they produced). To see what a specific job actually
  // collected, open its Job Detail page (jobLabelHtml()'s link) - which
  // still shows the full "Job log" of runs that job produced.
  //
  // Column-spec-driven (rather than one hardcoded <tr> template) so a
  // column can be shown/hidden without touching the row markup - requested
  // directly: 15 columns of dense detail forced horizontal scrolling just
  // to reach the Delete button, so the default view now shows only the
  // few that matter for a quick scan, with the rest opt-in via the
  // "Columns" picker (renderColumnPickerHtml/wireColumnPicker below).
  // Both the Jobs tab and Recovery's "Deleted jobs" panel render through
  // this same table, so they share one column spec and one saved
  // preference - a personal display choice, not data, so plain
  // localStorage is enough (see getVisibleJobColumnIds/setVisibleJobColumnIds).
  const JOB_COLUMNS = [
    { id: "job", label: "Job", always: true, filter: { type: "text" }, render: (j, deletedView) => {
      const deletedNote = deletedView && j.delete_reason
        ? `<br><span class="muted">Reason: ${escapeHtml(j.delete_reason)}${j.deleted_by ? ` &middot; ${escapeHtml(j.deleted_by)}` : ""}${j.deleted_at ? ` &middot; ${formatDateTime(j.deleted_at)}` : ""}</span>`
        : "";
      return `${jobLabelHtml(j, j.id)}${deletedNote}`;
    } },
    { id: "system", label: "System", render: (j) =>
      `<span class="mono">${escapeHtml(j.system_id)}${j.client ? `<span class="muted"> / ${escapeHtml(j.client)}</span>` : ""}</span>` },
    { id: "mode", label: "Mode",
      filter: { type: "options", options: [["scheduled", "Scheduled"], ["adhoc", "Ad-hoc"], ["filtered_scheduled", "Filtered recurring"]] },
      render: (j) => `<span class="badge badge-${JOB_MODE_BADGE[j.mode] || "low"}">${escapeHtml(j.mode)}</span>` },
    { id: "priority", label: "Priority",
      filter: { type: "options", options: [["A", "High"], ["B", "Medium"], ["C", "Low"]] },
      render: (j) =>
        `<span class="badge badge-${JOB_CLASS_BADGE[j.job_class] || "low"}">${escapeHtml(JOB_CLASS_LABEL[j.job_class] || j.job_class)}</span>` },
    { id: "frequency", label: "Frequency", render: (j) => formatJobFrequency(j) },
    // A live (queued/running) status pulses via badge-live - the one status
    // most worth noticing at a glance since it's the only one still changing.
    // A failed/partial job also gets a small warning glyph with the error
    // message as a native title tooltip - the Error column itself is opt-in
    // (hidden by default), so this is what keeps a failure from being
    // completely invisible in the default column set.
    { id: "status", label: "Status",
      filter: { type: "options", options: [
        ["queued", "Queued"], ["running", "Running"], ["success", "Success"],
        ["partial", "Partial"], ["error", "Error"],
      ] },
      render: (j) => {
        const live = j.status === "queued" || j.status === "running" ? " badge-live" : "";
        const warn = j.error_message
          ? (() => {
              const tip = jobErrorTooltipText(j.error_message, j.error_message_friendly);
              return ` <span class="status-error-flag" role="img" aria-label="Error: ${escapeHtml(tip)}" title="${escapeHtml(tip)}">${ICON.warning}</span>`;
            })()
          : "";
        return `<span class="badge badge-${JOB_STATUS_BADGE[j.status] || "low"}${live}">${escapeHtml(j.status)}</span>${warn}`;
      } },
    { id: "submitted", label: "Submitted", render: (j) => formatDateTime(j.submitted_at) },
    { id: "started", label: "Started", render: (j) => formatDateTime(j.started_at) },
    { id: "delay", label: "Delay", render: (j) => formatElapsed(j.submitted_at, j.started_at) },
    { id: "finished", label: "Finished", render: (j) => formatDateTime(j.finished_at) },
    { id: "duration", label: "Duration", render: (j) => formatElapsed(j.started_at, j.finished_at) },
    { id: "progress", label: "Progress", render: (j) => jobProgressHtml(j) },
    { id: "eta", label: "ETA", render: (j) => escapeHtml(formatEta(j.eta_seconds)) },
    { id: "error", label: "Error", render: (j) =>
      j.error_message ? `<span class="error">${jobErrorHtml(j.error_message, j.error_message_friendly)}</span>` : '<span class="muted">-</span>' },
    { id: "actions", label: "", always: true, render: (j, deletedView) => {
      const jobNameAttr = escapeHtml(j.job_name || "");
      return deletedView
        ? `<button type="button" class="btn-secondary btn-sm job-restore-btn" data-job-id="${j.id}" data-job-name="${jobNameAttr}">${ICON.refresh} Restore</button>`
        : `<button type="button" class="link-danger job-delete-btn" data-job-id="${j.id}" data-job-name="${jobNameAttr}">${ICON.trash} Delete</button>`;
    } },
  ];
  // "Error" is deliberately not in the default set even though failures
  // matter - it's opt-in, but a failed job's Status badge still gets a
  // visible warning icon (see the "status" column render above being
  // extended below) so nothing failing is silently invisible by default.
  const DEFAULT_VISIBLE_JOB_COLUMNS = ["job", "status", "frequency", "actions"];
  const JOB_COLUMNS_STORAGE_KEY = "sal.jobColumns.v1";

  function getVisibleJobColumnIds() {
    try {
      const raw = localStorage.getItem(JOB_COLUMNS_STORAGE_KEY);
      if (!raw) return new Set(DEFAULT_VISIBLE_JOB_COLUMNS);
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return new Set(DEFAULT_VISIBLE_JOB_COLUMNS);
      const known = new Set(JOB_COLUMNS.map((c) => c.id));
      return new Set(parsed.filter((id) => known.has(id)));
    } catch {
      return new Set(DEFAULT_VISIBLE_JOB_COLUMNS);
    }
  }

  function setVisibleJobColumnIds(ids) {
    try {
      localStorage.setItem(JOB_COLUMNS_STORAGE_KEY, JSON.stringify([...ids]));
    } catch {
      // Private-browsing/storage-disabled - the picker still works for this
      // page view, it just won't remember the choice on the next visit.
    }
  }

  // Reuses the existing .menu/.menu-trigger/.menu-panel dropdown (same one
  // the per-row "Data" export menu uses), but with plain <label>/<input
  // type=checkbox> items instead of [role=menuitem] links - setupDropdownMenu
  // only auto-closes the panel on a [role=menuitem] click, so toggling one
  // checkbox deliberately leaves the panel open to toggle more.
  function columnPickerHtml(pickerId, visibleIds) {
    const items = JOB_COLUMNS.filter((c) => !c.always)
      .map((c) => `
        <label class="menu-checkbox-item">
          <input type="checkbox" class="col-toggle" data-col-id="${c.id}" ${visibleIds.has(c.id) ? "checked" : ""}>
          ${escapeHtml(c.label)}
        </label>`)
      .join("");
    return `
      <div class="menu columns-picker-menu" id="${pickerId}">
        <button type="button" class="btn-secondary btn-sm menu-trigger" aria-expanded="false">
          ${ICON.columns} Columns ${ICON.chevronDown}
        </button>
        <div class="menu-panel" role="group" aria-label="Choose visible columns" hidden>
          ${items}
        </div>
      </div>`;
  }

  function wireColumnPicker(pickerId, onChange) {
    const picker = document.getElementById(pickerId);
    if (!picker) return;
    setupDropdownMenu(picker);
    picker.querySelectorAll(".col-toggle").forEach((cb) => {
      cb.addEventListener("change", () => {
        const visible = getVisibleJobColumnIds();
        if (cb.checked) visible.add(cb.dataset.colId); else visible.delete(cb.dataset.colId);
        setVisibleJobColumnIds(visible);
        onChange();
      });
    });
  }

  // A plain button, not a dropdown - requested directly in the Round 2 UAT
  // retest (JOB-02/JOB-03): once a filter combination matches nothing, the
  // filters themselves are still only reachable one at a time via their own
  // header icons, with no single control to clear all of them back to "no
  // filter" at once. `sizeClass` defaults to "btn-sm" (matches its sibling
  // buttons in Jobs'/Recovery's own panel-head-actions, e.g. the Columns
  // picker trigger and CSV/Excel export links, all btn-sm there) - pass ""
  // where the surrounding toolbar's other buttons are base-size instead
  // (Findings), so this control is never the odd one out (found directly:
  // "the button sizes seem different for each button ... in Findings").
  function resetFiltersButtonHtml(id, sizeClass = "btn-sm") {
    const sizeAttr = sizeClass ? ` ${sizeClass}` : "";
    return `<button type="button" class="btn-secondary${sizeAttr}" id="${id}">${ICON.close} Reset filters</button>`;
  }

  // `filterState` is the same plain per-table object wireColumnFilterHeaders()
  // already mutates; `defaults` is that object's own empty shape (kept at the
  // call site, next to where the table's other per-page state is
  // (re)initialized, rather than guessed generically here). `onReset` is the
  // caller's own responsibility to (a) flip its `xTableInitialized` flag back
  // to false - forcing the next reload to rebuild <thead> too, so every
  // filter control's own displayed value (checked boxes, typed text)
  // visibly clears, not just the underlying state object (the normal per-
  // keystroke/per-checkbox reload path only ever touches <tbody> - see
  // renderJobsTableHead/Body's comment) - and (b) actually reload.
  function resetColumnFilters(id, filterState, defaults, onReset) {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.addEventListener("click", () => {
      Object.keys(filterState).forEach((k) => delete filterState[k]);
      Object.assign(filterState, defaults);
      onReset();
    });
  }

  // ---- Excel-style column-header filters -----------------------------------
  //
  // Requested directly: "make these tables filterable by each column...
  // same way we use filters in Excel." Reuses the .menu/.menu-trigger/
  // .menu-panel dropdown (same component as the Columns picker above and
  // the per-row Data-export menu) - a small funnel icon in the header cell
  // opens either a checkbox multi-select (for a column with a fixed, known
  // set of values - Status, Mode, Priority, Severity, Rule) or a single
  // "contains" text search box (for free-text columns - Job name, User).
  // A full distinct-value checkbox list for free-text columns - closer to
  // literal Excel behavior - was considered and declined in favor of the
  // search box: it would need a new backend lookup of every unique value
  // across the whole (possibly large) dataset per column, kept in sync as
  // data changes, for a payoff a search box already delivers more simply.
  //
  // State shape: one plain object per table, keyed by column id - an
  // "options" column holds an array of currently-checked values, a "text"
  // column holds the current search string. Missing/empty either way means
  // "no filter on this column".
  //
  // wireColumnFilterHeaders() is called exactly once per <thead>'s
  // lifetime (see renderJobsTableHead/Body's comment below) - a filter
  // change only ever replaces <tbody>, so the dropdown these controls live
  // in, and whatever's focused/mid-typing inside it, is never touched by
  // the reload it triggers. An earlier version of this fully re-rendered
  // the whole table (head included) on every change and tried to
  // synthetically reopen/refocus afterward; that had real edge cases
  // (found in UAT: a checked box couldn't be followed by a second one
  // without reloading the page, and typing a space into the text search
  // got silently dropped) - removed in favor of this simpler split.

  function columnFilterHeaderHtml(colId, filterSpec, currentValue) {
    const active = filterSpec.type === "text"
      ? !!currentValue
      : !!(currentValue && currentValue.length);
    const panelInner = filterSpec.type === "text"
      ? `<input type="text" class="col-filter-text" data-col-id="${escapeHtml(colId)}"
           placeholder="Search&hellip;" value="${escapeHtml(currentValue || "")}">`
      : filterSpec.options.map(([v, l]) => `
          <label class="menu-checkbox-item">
            <input type="checkbox" class="col-filter-option" data-col-id="${escapeHtml(colId)}"
              value="${escapeHtml(v)}" ${(currentValue || []).includes(v) ? "checked" : ""}>
            ${escapeHtml(l)}
          </label>`).join("");
    return `
      <div class="menu col-filter-menu" data-col-id="${escapeHtml(colId)}">
        <button type="button" class="col-filter-trigger menu-trigger${active ? " col-filter-active" : ""}"
          aria-expanded="false" aria-label="Filter">
          ${ICON.filter}
        </button>
        <div class="menu-panel" role="group" aria-label="Filter" hidden>
          ${panelInner}
        </div>
      </div>`;
  }

  // container: element whose descendants include the .col-filter-menu
  // widgets (normally the whole table - they live in <thead>). filterState:
  // the plain object described above, mutated in place. onChange: called
  // after any filter value changes - callers reset pagination offset to 0
  // and reload from the server inside this callback.
  function wireColumnFilterHeaders(container, filterState, onChange) {
    container.querySelectorAll(".col-filter-menu").forEach((menu) => setupDropdownMenu(menu));
    container.querySelectorAll(".col-filter-option").forEach((cb) => {
      cb.addEventListener("change", () => {
        const colId = cb.dataset.colId;
        const current = new Set(filterState[colId] || []);
        if (cb.checked) current.add(cb.value); else current.delete(cb.value);
        filterState[colId] = [...current];
        onChange();
      });
    });
    let debounceHandle;
    container.querySelectorAll(".col-filter-text").forEach((input) => {
      input.addEventListener("input", () => {
        clearTimeout(debounceHandle);
        const colId = input.dataset.colId;
        debounceHandle = setTimeout(() => {
          filterState[colId] = input.value.trim();
          onChange();
        }, 300);
      });
    });
  }

  // deletedView renders the Recovery tab's list instead of the normal Jobs
  // list: same columns, but the Job cell also shows who deleted it and why
  // (mirroring renderRunsTable()'s deletedView), and the action button is
  // Restore instead of Delete - see handleJobDelete/handleJobRestore below.
  // colFilters: this table's column-header-filter state (see
  // columnFilterHeaderHtml/wireColumnFilterHeaders above) - the header row
  // still renders even with zero matching items, on purpose, so the filter
  // controls stay reachable (a real Excel filter never hides its own
  // header just because it matched nothing).
  // Split into head/body on purpose (found in UAT: JOB-02/03/04) - a data
  // reload used to replace the *entire* table including <thead>, which
  // destroyed and resynthesized every column-header filter's dropdown/
  // text-input on every single filter change. That made checking a second
  // box (or typing a second word) unreliable: the dropdown had to be
  // synthetically reopened via trigger.click() and the text input's value
  // had to be captured/restored around the rebuild, both of which had
  // real edge cases. Now a data reload only ever touches <tbody> - the
  // header (and whatever dropdown is open, whatever text is mid-typing)
  // is never destroyed by one, so there is nothing to restore. The header
  // only gets rebuilt when the *set of columns itself* changes (the
  // Columns picker), a separate, deliberate action - see wireColumnPicker
  // in renderJobs()/renderRecovery() below.
  function renderJobsTableHead(colFilters) {
    const cols = JOB_COLUMNS.filter((c) => c.always || getVisibleJobColumnIds().has(c.id));
    return cols.map((c) => {
      const filterHtml = c.filter ? columnFilterHeaderHtml(c.id, c.filter, colFilters[c.id]) : "";
      return `<th>${escapeHtml(c.label)}${filterHtml}</th>`;
    }).join("");
  }

  function renderJobsTableBody(items, { deletedView = false } = {}) {
    const cols = JOB_COLUMNS.filter((c) => c.always || getVisibleJobColumnIds().has(c.id));
    const emptyMessage = deletedView
      ? "No deleted jobs - anything removed from the Jobs tab will show up here."
      : "No jobs match the current filters.";
    return items.length
      ? items.map((j) => `<tr>${cols.map((c) => `<td>${c.render(j, deletedView)}</td>`).join("")}</tr>`).join("")
      : `<tr><td colspan="${cols.length}" class="muted">${escapeHtml(emptyMessage)}</td></tr>`;
  }

  // Full first-paint render (head + body together) - only used once, when
  // a page/panel has no table in the DOM yet. Every subsequent update
  // touches <tbody> alone (see loadJobs()/loadRecovery() below).
  function renderJobsTable(items, { deletedView = false, colFilters = {} } = {}) {
    return `
      <div class="table-scroll">
        <table class="findings">
          <thead><tr>${renderJobsTableHead(colFilters)}</tr></thead>
          <tbody>${renderJobsTableBody(items, { deletedView })}</tbody>
        </table>
      </div>`;
  }

  // ---- Delete/restore-with-reason for jobs themselves (Recovery tab) -
  // mirrors handleRunDelete/handleRunRestore exactly, but against
  // /api/jobs/<id> (soft-deletes the collection_jobs row - see
  // sal/web/api.py's delete_job/restore_job) rather than a collection run.

  async function handleJobDelete(jobId, jobName, onDone) {
    const reason = await promptForReason(
      "Delete job",
      `Delete ${jobName ? `"${jobName}"` : "this job"}? It will move to the Recovery tab and can be ` +
      "restored later - the data it already collected is not affected.",
    );
    if (reason === null) return;
    try {
      await apiWrite(`/api/jobs/${encodeURIComponent(jobId)}`, "DELETE", { reason });
      showToast(`Deleted ${jobName ? `"${jobName}"` : "the job"} - restore it from Recovery any time.`);
      await onDone();
    } catch (err) {
      showErrorToast(err.message);
    }
  }

  async function handleJobRestore(jobId, jobName, onDone) {
    const reason = await promptForReason(
      "Restore job",
      `Restore ${jobName ? `"${jobName}"` : "this job"} back into the Jobs tab?`,
    );
    if (reason === null) return;
    try {
      await apiWrite(`/api/jobs/${encodeURIComponent(jobId)}/restore`, "POST", { reason });
      showToast(`Restored ${jobName ? `"${jobName}"` : "the job"}.`);
      await onDone();
    } catch (err) {
      showErrorToast(err.message);
    }
  }

  function wireJobRowActions(container, onDone) {
    container.querySelectorAll(".job-delete-btn").forEach((btn) => {
      btn.addEventListener("click", () => handleJobDelete(btn.dataset.jobId, btn.dataset.jobName, onDone));
    });
    container.querySelectorAll(".job-restore-btn").forEach((btn) => {
      btn.addEventListener("click", () => handleJobRestore(btn.dataset.jobId, btn.dataset.jobName, onDone));
    });
  }

  function renderNextScheduledRun(items) {
    const el = document.getElementById("jobsNextRun");
    if (!el) return;
    if (!state.systemId) {
      el.textContent = "";
      return;
    }
    const withNext = items.find((j) => j.next_scheduled_run);
    if (withNext) {
      el.textContent = `Next scheduled run for ${state.systemId}: ${formatDateTime(withNext.next_scheduled_run)}`;
    } else if (items.length) {
      el.textContent = `No scheduled run currently registered for ${state.systemId}.`;
    } else {
      el.textContent = `No collection jobs recorded yet for ${state.systemId} - next scheduled run isn't known until the first job runs.`;
    }
  }

  let jobsState = { offset: 0, limit: 20, date_from: "", date_to: "" };

  // Excel-style column-header filter state (see columnFilterHeaderHtml
  // above) - job/mode/priority/status replace what used to be separate
  // top-of-page form fields for the same data, now moved into the table's
  // own headers; date range stays a top-of-page range picker (a checkbox
  // list or single search box doesn't fit a date range the way it fits
  // these).
  let jobsColFilters = { job: "", mode: [], priority: [], status: [] };

  // Tracks whether the *last successful* fetch had a queued/running job -
  // needed so a poll tick skipped by the focus guard below still knows
  // whether to keep polling at all.
  let jobsHasActive = false;

  // Cached so the Columns picker (rendered once, outside this function -
  // see renderJobs()) can re-render the table from the last fetch when the
  // visible-column set changes, without an extra round-trip to the server.
  let lastJobsItems = [];

  // fromPoll distinguishes the automatic ~1.5s background refresh from
  // every other caller (pager buttons, date-range change, a column-header
  // filter change) - only the automatic poll should ever be skipped to
  // protect an in-progress interaction; a filter checkbox living inside
  // #jobsBody would otherwise trip that same guard on its own deliberate
  // click and silently appear to do nothing.
  // True once the table (head + body) has been painted at least once this
  // page visit - after that, a reload only ever touches <tbody> (see
  // renderJobsTableHead/Body's comment above for why).
  let jobsTableInitialized = false;

  async function loadJobs(fromPoll = false) {
    const container = document.getElementById("jobsBody");
    if (!container) return; // navigated away - stop polling
    // Found in a11y review: a full innerHTML rebuild every ~1.5s (while any
    // job is active) yanks focus to <body> mid-interaction if the user has
    // an expanded row's Delete/Restore/export controls focused. Skip this
    // tick's rebuild (but keep polling) rather than destroy their focus -
    // the tradeoff is one skipped progress refresh, not a lost action.
    if (fromPoll && jobsHasActive && container.contains(document.activeElement)) {
      setTimeout(() => loadJobs(true), JOB_POLL_MS);
      return;
    }
    const params = scopeParams({
      job_name: jobsColFilters.job, mode: jobsColFilters.mode, status: jobsColFilters.status,
      job_class: jobsColFilters.priority,
      date_from: jobsState.date_from, date_to: jobsState.date_to,
      limit: jobsState.limit, offset: jobsState.offset,
    });
    const data = await api(`/api/jobs?${params}`);
    if (!document.getElementById("jobsBody")) return; // navigated away mid-fetch
    lastJobsItems = data.items;
    if (!jobsTableInitialized) {
      container.innerHTML = renderJobsTable(data.items, { colFilters: jobsColFilters });
      wireColumnFilterHeaders(container.querySelector("thead"), jobsColFilters, () => { jobsState.offset = 0; loadJobs(); });
      jobsTableInitialized = true;
    } else {
      container.querySelector("tbody").innerHTML = renderJobsTableBody(data.items);
    }
    wireJobRowActions(container.querySelector("tbody"), loadJobs);
    renderNextScheduledRun(data.items);

    const start = data.total === 0 ? 0 : jobsState.offset + 1;
    const end = Math.min(jobsState.offset + jobsState.limit, data.total);
    const pager = document.getElementById("jobsPager");
    pager.innerHTML = `
      <button type="button" class="btn-secondary btn-sm" id="jobsPrevBtn" ${jobsState.offset === 0 ? "disabled" : ""}>&larr; Prev</button>
      <span class="muted">${start}&ndash;${end} of ${data.total}</span>
      <button type="button" class="btn-secondary btn-sm" id="jobsNextBtn" ${end >= data.total ? "disabled" : ""}>Next &rarr;</button>`;
    document.getElementById("jobsPrevBtn").addEventListener("click", () => {
      jobsState.offset = Math.max(0, jobsState.offset - jobsState.limit);
      loadJobs();
    });
    document.getElementById("jobsNextBtn").addEventListener("click", () => {
      jobsState.offset += jobsState.limit;
      loadJobs();
    });

    // Export is deliberately the full unfiltered history (see
    // collection_runs_export()'s own docstring) - the on-screen
    // search/pagination is for finding one job, not for scoping an export.
    const exportParams = scopeParams();
    document.getElementById("exportRunsCsvBtn").href = `/api/collection-runs/export?${exportParams}&format=csv`;
    document.getElementById("exportRunsXlsxBtn").href = `/api/collection-runs/export?${exportParams}&format=xlsx`;

    jobsHasActive = data.items.some((j) => j.status === "queued" || j.status === "running");
    if (jobsHasActive) {
      setTimeout(() => loadJobs(true), JOB_POLL_MS);
    }
  }

  async function renderJobs() {
    jobsState = { offset: 0, limit: 20, date_from: "", date_to: "" };
    jobsColFilters = { job: "", mode: [], priority: [], status: [] };
    jobsHasActive = false;
    jobsTableInitialized = false;
    $app.innerHTML = `
      <div class="page-head">
        <h1>Jobs</h1>
        <p class="muted">
          Search, monitor, and drill into every collection job for this system - the same role
          SM37 plays for background jobs in SAP. Click a column's filter icon to narrow it down,
          same as an Excel column filter.
        </p>
        <p class="muted" id="jobsNextRun"></p>
      </div>
      <div class="panel">
        <form id="jobsFilterForm" class="field-grid">
          <label>Submitted from
            <input type="date" name="date_from">
          </label>
          <label>Submitted to
            <input type="date" name="date_to">
          </label>
        </form>
      </div>
      <div class="panel" style="margin-top:1.25rem">
        <h2>Jobs
          <span class="panel-head-actions">
            ${columnPickerHtml("jobsColumnsPicker", getVisibleJobColumnIds())}
            ${resetFiltersButtonHtml("jobsResetFiltersBtn")}
            <a id="exportRunsCsvBtn" class="btn-secondary btn-sm" href="#">${ICON.file} CSV</a>
            <a id="exportRunsXlsxBtn" class="btn-secondary btn-sm" href="#">${ICON.file} Excel</a>
          </span>
        </h2>
        <div id="jobsBody">${skeleton(300)}</div>
        <div id="jobsPager" class="toolbar" style="margin-top:0.75rem"></div>
      </div>`;

    wireColumnPicker("jobsColumnsPicker", () => {
      // Unlike a data reload, showing/hiding a column changes the column
      // *set* itself, so both head and body genuinely need to be rebuilt
      // here (a deliberate, occasional action - not the per-keystroke/
      // per-checkbox case renderJobsTableHead/Body's split protects).
      const container = document.getElementById("jobsBody");
      if (!container) return;
      container.innerHTML = renderJobsTable(lastJobsItems, { colFilters: jobsColFilters });
      wireColumnFilterHeaders(container.querySelector("thead"), jobsColFilters, () => { jobsState.offset = 0; loadJobs(); });
      wireJobRowActions(container.querySelector("tbody"), loadJobs);
    });

    resetColumnFilters("jobsResetFiltersBtn", jobsColFilters,
      { job: "", mode: [], priority: [], status: [] }, () => {
        jobsTableInitialized = false;
        jobsState.offset = 0;
        loadJobs();
      });

    const form = document.getElementById("jobsFilterForm");
    form.addEventListener("change", () => {
      jobsState.date_from = form.date_from.value || "";
      jobsState.date_to = form.date_to.value || "";
      jobsState.offset = 0;
      loadJobs();
    });

    await loadJobs();
  }

  // ---- Recovery - everything soft-deleted lands here, one level for jobs
  // (deleted from the Jobs tab) and one level for the individual runs a job
  // produced (deleted from a Job Detail page's Job Log) - two independent
  // lifecycles (see sal/web/api.py's delete_job/restore_job vs
  // delete_collection_run/restore_collection_run), but a user shouldn't have
  // to know which one applies or go dig through a specific job's page to
  // find and undo either kind of delete - both show up here directly.
  // No active-job polling here: delete_job() refuses a queued/running job,
  // so nothing in the deleted-jobs list is ever still in flight.

  let recoveryState = { offset: 0, limit: 20, date_from: "", date_to: "" };

  // Same shape/reasoning as jobsColFilters above - shared column ids since
  // this panel renders through the same renderJobsTable()/JOB_COLUMNS.
  let recoveryColFilters = { job: "", mode: [], priority: [], status: [] };

  // Same reasoning as lastJobsItems above - lets the shared Columns picker
  // re-render this panel from the last fetch without a re-fetch.
  let lastRecoveryItems = [];

  // Same reasoning as jobsTableInitialized above.
  let recoveryTableInitialized = false;

  async function loadRecovery() {
    const container = document.getElementById("recoveryBody");
    if (!container) return; // navigated away
    const params = scopeParams({
      job_name: recoveryColFilters.job, mode: recoveryColFilters.mode, status: recoveryColFilters.status,
      job_class: recoveryColFilters.priority,
      date_from: recoveryState.date_from, date_to: recoveryState.date_to,
      limit: recoveryState.limit, offset: recoveryState.offset,
      view: "deleted",
    });
    const data = await api(`/api/jobs?${params}`);
    if (!document.getElementById("recoveryBody")) return; // navigated away mid-fetch
    lastRecoveryItems = data.items;
    if (!recoveryTableInitialized) {
      container.innerHTML = renderJobsTable(data.items, { deletedView: true, colFilters: recoveryColFilters });
      wireColumnFilterHeaders(container.querySelector("thead"), recoveryColFilters, () => { recoveryState.offset = 0; loadRecovery(); });
      recoveryTableInitialized = true;
    } else {
      container.querySelector("tbody").innerHTML = renderJobsTableBody(data.items, { deletedView: true });
    }
    wireJobRowActions(container.querySelector("tbody"), loadRecovery);

    const start = data.total === 0 ? 0 : recoveryState.offset + 1;
    const end = Math.min(recoveryState.offset + recoveryState.limit, data.total);
    const pager = document.getElementById("recoveryPager");
    pager.innerHTML = `
      <button type="button" class="btn-secondary btn-sm" id="recoveryPrevBtn" ${recoveryState.offset === 0 ? "disabled" : ""}>&larr; Prev</button>
      <span class="muted">${start}&ndash;${end} of ${data.total}</span>
      <button type="button" class="btn-secondary btn-sm" id="recoveryNextBtn" ${end >= data.total ? "disabled" : ""}>Next &rarr;</button>`;
    document.getElementById("recoveryPrevBtn").addEventListener("click", () => {
      recoveryState.offset = Math.max(0, recoveryState.offset - recoveryState.limit);
      loadRecovery();
    });
    document.getElementById("recoveryNextBtn").addEventListener("click", () => {
      recoveryState.offset += recoveryState.limit;
      loadRecovery();
    });
  }

  // Deleted runs get column-header filters (Job/Status) but no separate
  // top-of-page form or pagination (limit only) - same choice Job Detail's
  // own Job Log already makes for its (much shorter, one-job-scoped) run
  // list, just with Excel-style filtering layered on since this panel can
  // span every job, not one.
  let recoveryRunsColFilters = { job: "", status: [] };

  // Same reasoning as jobsTableInitialized above.
  let recoveryRunsTableInitialized = false;

  async function loadRecoveryRuns() {
    const container = document.getElementById("recoveryRunsBody");
    if (!container) return; // navigated away
    const params = scopeParams({
      view: "deleted", limit: 500,
      job_name: recoveryRunsColFilters.job, status: recoveryRunsColFilters.status,
    });
    const data = await api(`/api/collection-runs?${params}`);
    if (!document.getElementById("recoveryRunsBody")) return; // navigated away mid-fetch
    if (!recoveryRunsTableInitialized) {
      container.innerHTML = renderRunsTable(data.items, {
        deletedView: true, showColumnFilters: true, colFilters: recoveryRunsColFilters,
      });
      wireColumnFilterHeaders(container.querySelector("thead"), recoveryRunsColFilters, loadRecoveryRuns);
      recoveryRunsTableInitialized = true;
    } else {
      container.querySelector("tbody").innerHTML = renderRunsTableBody(data.items, {
        deletedView: true, showColumnFilters: true,
      });
    }
    // Per-row "Data" export menu - re-wired every time since tbody rows
    // (and their menus) are recreated on every reload, unlike the header
    // filters above.
    container.querySelector("tbody").querySelectorAll(".menu").forEach((menu) => setupDropdownMenu(menu));
    wireRunRowActions(container.querySelector("tbody"), loadRecoveryRuns);
  }

  async function renderRecovery() {
    recoveryState = { offset: 0, limit: 20, date_from: "", date_to: "" };
    recoveryColFilters = { job: "", mode: [], priority: [], status: [] };
    recoveryRunsColFilters = { job: "", status: [] };
    recoveryTableInitialized = false;
    recoveryRunsTableInitialized = false;
    $app.innerHTML = `
      <div class="page-head">
        <h1>Recovery</h1>
        <p class="muted">
          Anything soft-deleted lands here, never gone outright - whole jobs deleted from the
          Jobs tab, and individual collection runs deleted from a Job Detail page's Job Log.
          Restore either one to send it back where it came from, with the reason kept either way
          (see Activity for the full audit trail).
        </p>
      </div>
      <div class="panel">
        <form id="recoveryFilterForm" class="field-grid">
          <label>Submitted from
            <input type="date" name="date_from">
          </label>
          <label>Submitted to
            <input type="date" name="date_to">
          </label>
        </form>
      </div>
      <div class="panel" style="margin-top:1.25rem">
        <h2>Deleted jobs
          <span class="panel-head-actions">
            ${columnPickerHtml("recoveryColumnsPicker", getVisibleJobColumnIds())}
            ${resetFiltersButtonHtml("recoveryResetFiltersBtn")}
          </span>
        </h2>
        <div id="recoveryBody">${skeleton(300)}</div>
        <div id="recoveryPager" class="toolbar" style="margin-top:0.75rem"></div>
      </div>
      <div class="panel" style="margin-top:1.25rem">
        <h2>Deleted collection runs
          <span class="panel-head-actions">
            ${resetFiltersButtonHtml("recoveryRunsResetFiltersBtn")}
          </span>
        </h2>
        <p class="panel-caption">
          One level below a job: an individual collection run deleted from a Job Detail page's
          Job Log, without the job itself being deleted.
        </p>
        <div id="recoveryRunsBody">${skeleton(200)}</div>
      </div>`;

    wireColumnPicker("recoveryColumnsPicker", () => {
      const container = document.getElementById("recoveryBody");
      if (!container) return;
      container.innerHTML = renderJobsTable(lastRecoveryItems, { deletedView: true, colFilters: recoveryColFilters });
      wireColumnFilterHeaders(container.querySelector("thead"), recoveryColFilters, () => { recoveryState.offset = 0; loadRecovery(); });
      wireJobRowActions(container.querySelector("tbody"), loadRecovery);
    });

    resetColumnFilters("recoveryResetFiltersBtn", recoveryColFilters,
      { job: "", mode: [], priority: [], status: [] }, () => {
        recoveryTableInitialized = false;
        recoveryState.offset = 0;
        loadRecovery();
      });

    resetColumnFilters("recoveryRunsResetFiltersBtn", recoveryRunsColFilters,
      { job: "", status: [] }, () => {
        recoveryRunsTableInitialized = false;
        loadRecoveryRuns();
      });

    const form = document.getElementById("recoveryFilterForm");
    form.addEventListener("change", () => {
      recoveryState.date_from = form.date_from.value || "";
      recoveryState.date_to = form.date_to.value || "";
      recoveryState.offset = 0;
      loadRecovery();
    });

    await Promise.all([loadRecovery(), loadRecoveryRuns()]);
  }

  // ---- Job detail (opened in a new tab from a Jobs/Collection History row -
  // ---- see jobLabelHtml()) - the exact parameters a job was submitted
  // ---- with, plus the day-by-day collection_runs it produced.           ----

  const FILTER_LABELS = [
    ["user", "User(s)"],
    ["transaction_code", "Transaction code(s)"],
    ["report", "Report / program"],
    ["instance", "Instance"],
    ["msg_code", "Message code(s)"],
  ];

  // Each pushed value is already safe HTML by the time it lands in `rows`
  // (either pre-escaped here, or - for formatDateRange()'s return value -
  // safe by construction) - the final render below does NOT re-escape, to
  // avoid double-escaping formatDateRange()'s own "&ndash;" markup into
  // literal "&amp;ndash;" text (found in live verification).
  function jobFiltersHtml(filtersJson) {
    const filters = filtersJson ? JSON.parse(filtersJson) : {};
    const rows = [];
    if (filters.dat_from || filters.dat_to) {
      rows.push(["Date range", formatDateRange(filters.dat_from, filters.dat_to)]);
    }
    if (filters.tim_from || filters.tim_to) {
      rows.push(["Time range",
        `${formatDateTime(filters.tim_from || "000000")} &ndash; ${formatDateTime(filters.tim_to || "235959")}`]);
    }
    // Multi-value filters (e.g. several transaction codes) get one row per
    // value rather than a single comma-joined cell (JOB-09/JD-01, 2026-09-16)
    // - each value then sits alone in its own cell, so it can be selected
    // and copied on its own instead of having to hand-split a CSV string.
    FILTER_LABELS.forEach(([key, label]) => {
      const value = filters[key];
      if (!value) return;
      if (Array.isArray(value)) {
        value.forEach((v) => rows.push([label, escapeHtml(String(v))]));
      } else {
        rows.push([label, escapeHtml(String(value))]);
      }
    });
    if (!rows.length) {
      return '<p class="muted">No additional filters - full date/time range, all users/tcodes.</p>';
    }
    // A row-header cell (<th scope="row">) is only emitted on the first row
    // of each label's group, spanning the rest via rowspan - so a screen
    // reader announces "Transaction code(s)" once as the group's header
    // rather than re-announcing it before every exploded value, while each
    // value still sits alone in its own independently-selectable cell.
    const bodyRows = rows
      .map(([k, v], i) => {
        if (i > 0 && rows[i - 1][0] === k) return `<tr><td>${v}</td></tr>`;
        let span = 1;
        while (rows[i + span] && rows[i + span][0] === k) span++;
        const rowspanAttr = span > 1 ? ` rowspan="${span}"` : "";
        return `<tr><th scope="row" class="mono"${rowspanAttr}>${escapeHtml(k)}</th><td>${v}</td></tr>`;
      })
      .join("");
    return `
      <table class="findings">
        <tbody>${bodyRows}</tbody>
      </table>`;
  }

  // showDeleted surfaces runs deleted from this job's log (via the Delete
  // button on each row below) so they're actually recoverable somewhere -
  // deleting a *run* here is a separate action from deleting the *job*
  // itself on the Jobs tab (see Recovery tab for that), and previously
  // there was no way back into a deleted run at all once the standalone
  // Collection History page (which had this same active/deleted toggle)
  // was folded into Jobs - found via a user report of an "unrecoverable"
  // deleted job that turned out to be a deleted run instead.
  async function loadJobDetailRuns(jobId, showDeleted = false) {
    const container = document.getElementById("jobDetailRuns");
    if (!container) return; // navigated away
    const view = showDeleted ? "&view=deleted" : "";
    const data = await api(`/api/collection-runs?job_id=${encodeURIComponent(jobId)}&limit=500${view}`);
    container.innerHTML = renderRunsTable(data.items, { currentJobId: jobId, deletedView: showDeleted });
    container.querySelectorAll(".menu").forEach((menu) => setupDropdownMenu(menu));
    wireRunRowActions(container, () => loadJobDetailRuns(jobId, showDeleted));
  }

  async function renderJobDetail(jobId) {
    $app.innerHTML = `
      <div class="page-head">
        <h1>Job #${jobId}</h1>
        <p class="muted"><a href="#/jobs">&larr; Back to Jobs</a></p>
      </div>
      <div id="jobDetailBody">${skeleton(200)}</div>`;

    let data;
    try {
      data = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    } catch (err) {
      document.getElementById("jobDetailBody").innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
      return;
    }
    const j = data.item;
    const statusCls = JOB_STATUS_BADGE[j.status] || "low";
    const modeCls = JOB_MODE_BADGE[j.mode] || "low";

    document.getElementById("jobDetailBody").innerHTML = `
      <div class="panel">
        <h2>${jobLabelHtml(j)}</h2>
        <div class="field-grid">
          <div><span class="muted">System</span><br>${escapeHtml(j.system_id)}${j.client ? ` / ${escapeHtml(j.client)}` : ""}</div>
          <div><span class="muted">Mode</span><br><span class="badge badge-${modeCls}">${escapeHtml(j.mode)}</span></div>
          <div><span class="muted">Frequency</span><br>${formatJobFrequency(j)}</div>
          <div><span class="muted">Priority</span><br><span class="badge badge-${JOB_CLASS_BADGE[j.job_class] || "low"}">${escapeHtml(JOB_CLASS_LABEL[j.job_class] || j.job_class)}</span></div>
          <div><span class="muted">Status</span><br><span class="badge badge-${statusCls}">${escapeHtml(j.status)}</span></div>
          <div><span class="muted">Triggered by</span><br>${escapeHtml(j.triggered_by)}</div>
          <div><span class="muted">Submitted</span><br>${formatDateTime(j.submitted_at)}</div>
          <div><span class="muted">Started</span><br>${formatDateTime(j.started_at)}</div>
          <div><span class="muted">Finished</span><br>${formatDateTime(j.finished_at)}</div>
          <div><span class="muted">Progress</span><br>${jobProgressHtml(j)}</div>
          <div><span class="muted">ETA</span><br>${escapeHtml(formatEta(j.eta_seconds))}</div>
          <div><span class="muted">Last completed date</span><br>${formatDateTime(j.last_completed_date)}</div>
        </div>
        ${j.error_message ? `<p class="error" style="margin-top:0.75rem">${jobErrorHtml(j.error_message, j.error_message_friendly)}</p>` : ""}
      </div>
      <div class="panel" style="margin-top:1.25rem">
        <h2>Parameters this job was submitted with</h2>
        ${jobFiltersHtml(j.filters_json)}
      </div>
      <div class="panel" style="margin-top:1.25rem">
        <h2>Job log
          <span class="panel-head-actions">
            <label class="muted" style="font-weight:normal">
              <input type="checkbox" id="jobLogShowDeleted"> Show deleted runs
            </label>
          </span>
        </h2>
        <p class="panel-caption">
          The collection runs this job produced - one per day for a chunked scheduled job,
          one for the whole range for an ad-hoc pull. Deleting a run here only removes it from
          this log (via the Delete action on each row) - it's a separate, recoverable action
          from deleting the job itself (see the Jobs/Recovery tabs for that).
        </p>
        <div id="jobDetailRuns">${skeleton(140)}</div>
      </div>`;

    document.getElementById("jobLogShowDeleted").addEventListener("change", (e) => {
      loadJobDetailRuns(jobId, e.target.checked);
    });
    await loadJobDetailRuns(jobId);
  }

  // ---- Coverage (Phase D: SM19 audit-configuration visibility) ------------
  //
  // SM19's own vocabulary ($DYN$, CLASS_TCD, MANDT/UNAME filters) is
  // meaningful to a Basis admin but opaque to a security analyst, who is
  // this page's actual audience - the labels/legend below translate it
  // without hiding the raw SAP terms (kept in parens/tooltips) for anyone
  // who does need to cross-reference SM19 directly.

  // Canonical class descriptions, kept in sync with sal/rules/_coverage.py's
  // own CLASS_* comments (the source of truth for what each class actually
  // captures - see that module's docstring for how confident each mapping is).
  const CLASS_LABELS = {
    CLASS_LOGIN: "Dialog logon - interactive SAP GUI sign-in/sign-off",
    CLASS_RFC_LOGIN: "RFC/CPIC logon - sign-in via RFC or CPIC (e.g. from another system)",
    CLASS_TCD: "Transaction start - a user starting a transaction code (tcode)",
    CLASS_REP: "Report start - a user directly executing an ABAP report/program",
    CLASS_USER: "User master record change - creating, changing, locking or deleting a user account",
    CLASS_SYST: "System events - audit log / other system-level administrative events",
    CLASS_RFC: "RFC function calls - remote function module calls",
    CLASS_OTHER: "Other events - everything else (e.g. generic table access, data exports)",
  };

  function friendlyProfileLabel(profile) {
    // RSAU_API_GET_AUDIT_CONFIG always reports the live configuration under
    // the fixed name "$DYN$" (see sal/audit_config.py's module docstring) -
    // it's not a name anyone chose, it just means "the dynamic profile
    // that's active right now." Anything else here would be an actual
    // named static profile, shown as-is rather than relabeled.
    return profile === "$DYN$" ? "Active configuration" : profile;
  }

  function friendlyFilterValue(value) {
    return !value || value === "*" ? "All" : value;
  }

  function classLegend() {
    const rows = Object.entries(CLASS_LABELS)
      .map(([code, label]) => `
        <tr>
          <td><span class="badge badge-low">${escapeHtml(code.replace("CLASS_", ""))}</span></td>
          <td class="muted">${escapeHtml(label)}</td>
        </tr>`)
      .join("");
    return `
      <p class="panel-caption" style="margin-top:1rem">
        <strong>Active classes</strong> - which kinds of events SAP is set up to write to the audit
        log. A class appearing here doesn't mean every such event is a concern, only that SAP is
        capturing that kind of event at all (see the coverage table below for what each detection
        rule actually needs).
      </p>
      <table class="result">
        <tbody>${rows}</tbody>
      </table>
      <p class="panel-caption" style="margin-top:1rem">
        <strong>Applies to (client / user)</strong> - each row above is one logging rule ("slot").
        "Client" limits it to one SAP client (e.g. <code>066</code>); "User" limits it to usernames
        matching a pattern (SAP wildcards: <code>*</code> matches anything, so <code>SAP#*</code>
        matches any username starting with "SAP#" - a common convention for system/background
        accounts). <strong>All</strong> means no restriction - that slot applies to every client or
        every user.
      </p>`;
  }

  function renderSlotsTable(slots) {
    if (!slots.length) return '<p class="muted">No active audit-log slots.</p>';
    const rows = slots.map((s) => {
      const profileLabel = friendlyProfileLabel(s.profile);
      const rawSuffix = s.profile && profileLabel !== s.profile
        ? ` <span class="mono muted" style="font-size:0.8em">(${escapeHtml(s.profile)})</span>`
        : "";
      const profileCell = s.profile
        ? `${escapeHtml(profileLabel)}${rawSuffix}`
        : '<span class="muted">unknown</span>';
      return `
      <tr>
        <td>${profileCell}</td>
        <td><span class="badge badge-${s.status === "X" ? "success" : "low"}">${s.status === "X" ? "active" : "inactive"}</span></td>
        <td>${s.active_classes.map((c) => `<span class="badge badge-low" title="${escapeHtml(CLASS_LABELS[c] || c)}">${escapeHtml(c.replace("CLASS_", ""))}</span>`).join(" ") || "<span class=\"muted\">none</span>"}</td>
        <td class="muted">Client: ${escapeHtml(friendlyFilterValue(s.client_filter))} &middot; User: ${escapeHtml(friendlyFilterValue(s.user_filter))}</td>
      </tr>`;
    }).join("");
    return `
      <table class="result">
        <thead><tr><th>Profile</th><th>Status</th><th>Active classes</th><th>Applies to (client / user)</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      ${classLegend()}`;
  }

  function renderGapsTable(gaps) {
    if (!gaps.length) {
      return '<p class="ok">No coverage gaps - every rule\'s required event class is currently active.</p>';
    }
    const rows = gaps.map((g) => `
      <tr>
        <td class="mono">${escapeHtml(g.rule_key)}</td>
        <td>${g.required_classes.map((c) => `<span class="badge badge-low" title="${escapeHtml(CLASS_LABELS[c] || c)}">${escapeHtml(c.replace("CLASS_", ""))}</span>`).join(" ")}</td>
        <td>${g.unverified
          ? '<span class="badge badge-medium">unverified - no successful check yet</span>'
          : g.missing_classes.map((c) => `<span class="badge badge-high" title="${escapeHtml(CLASS_LABELS[c] || c)}">${escapeHtml(c.replace("CLASS_", ""))} missing</span>`).join(" ")}</td>
        <td class="muted">${escapeHtml(g.confidence)}</td>
      </tr>`).join("");
    return `
      <table class="result">
        <thead><tr><th>Rule</th><th>Required class(es)</th><th>Gap</th><th>Mapping confidence</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  async function loadCoverage() {
    const params = scopeParams();
    const data = await api(`/api/audit-config?${params}`);
    const snapshot = data.snapshot;
    const body = document.getElementById("coverageBody");

    const statusHtml = !snapshot
      ? '<p class="muted">No check has been run yet for this system - click "Check now".</p>'
      : snapshot.status === "success"
        ? `<p>${snapshot.enabled ? '<span class="ok">Audit log enabled</span>' : '<span class="error">Audit log disabled</span>'}
             &middot; checked ${escapeHtml(relativeTime(snapshot.captured_at))}</p>
           ${renderSlotsTable(snapshot.parsed_slots)}`
        : `<p class="error">Last check failed: ${escapeHtml(snapshot.error_message || "unknown error")}
             (${escapeHtml(relativeTime(snapshot.captured_at))})</p>`;

    body.innerHTML = `
      <div class="panel">
        <h2>Active SM19 configuration</h2>
        ${statusHtml}
      </div>
      <div class="panel" style="margin-top:1.25rem">
        <h2>Detection coverage vs. rule requirements</h2>
        <p class="panel-caption">Checked at the SM19 event-class level (Login, Transaction, User master, etc.) -
          message-code-level precision isn't attempted, since that bit-level detail isn't
          documented reliably enough to trust (see sal/rules/_coverage.py).</p>
        ${renderGapsTable(data.gaps)}
      </div>`;
  }

  // ---- Role context (Phase F: PFCG role/tcode authorization data) ---------

  function renderRoleContextHistoryTable(history) {
    if (!history.length) {
      return '<p class="muted">No role-context refreshes recorded yet.</p>';
    }
    const badgeFor = { success: "success", success_truncated: "medium", error: "high" };
    const rows = history.map((r) => `
      <tr>
        <td>${formatDateTime(r.run_at)}</td>
        <td class="mono">${escapeHtml(r.actor)}</td>
        <td><span class="badge badge-${badgeFor[r.status] || "high"}">${escapeHtml(r.status)}</span></td>
        <td>${r.status !== "error" ? `${r.user_role_rows} / ${r.role_tcode_rows}` : '<span class="muted">-</span>'}</td>
        <td>${r.error_message ? `<span class="error">${escapeHtml(r.error_message)}</span>` : '<span class="muted">-</span>'}</td>
      </tr>`).join("");
    return `
      <div class="table-scroll">
        <table class="findings">
          <thead><tr><th>Run at</th><th>Actor</th><th>Status</th><th>Role rows / tcode rows</th><th>Error</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  // Full/unrestricted SAP access profiles - present on every SAP system by
  // default, not something specific to this customer's Z-namespace, so
  // matching by exact name (case-insensitively) is safe and won't need
  // updating per-customer the way a Z-profile allowlist would.
  const HIGH_RISK_PROFILES = new Set(["SAP_ALL", "SAP_NEW"]);

  function renderUserAccessLookup(data) {
    const rolesHtml = data.roles.length
      ? data.roles.map((r) => `<span class="badge badge-low">${escapeHtml(r)}</span>`).join(" ")
      : '<span class="muted">none</span>';
    const tcodeSummary = data.has_role_data
      ? `${data.tcodes_via_roles.length} tcode(s) authorized via ${data.roles.length} role(s) above`
      : "no PFCG role data on record for this user";

    let profilesHtml;
    if (data.profiles_error) {
      profilesHtml = `<p class="error">Could not fetch directly-assigned profiles: ${escapeHtml(data.profiles_error)}</p>`;
    } else if (!data.profiles.length) {
      profilesHtml = '<p class="muted">No profiles directly assigned to this user\'s master record.</p>';
    } else {
      profilesHtml = `<p>${data.profiles
        .map((p) => {
          const highRisk = HIGH_RISK_PROFILES.has(p.toUpperCase());
          const title = highRisk
            ? "Full/unrestricted SAP access - grants every transaction and authorization object"
            : "Assigned directly to this user's master record, independent of any PFCG role";
          return `<span class="badge badge-${highRisk ? "high" : "low"}" title="${escapeHtml(title)}">${escapeHtml(p)}</span>`;
        })
        .join(" ")}</p>`;
    }

    return `
      <div class="panel" style="margin-top:1rem">
        <h3 style="margin-top:0">Access for <span class="mono">${escapeHtml(data.user_id)}</span></h3>
        <p class="panel-caption" style="margin-top:0">
          <strong>PFCG roles</strong> &middot; ${escapeHtml(tcodeSummary)}
        </p>
        <p>${rolesHtml}</p>
        <p class="panel-caption" style="margin-top:1rem">
          <strong>Directly-assigned profiles</strong> - granted straight to this user's master
          record (SU01's own Profiles tab), independent of any role. A user can be authorized
          this way with no matching role or role-menu tcode at all - fetched live from SAP, not
          from the role/tcode data above.
        </p>
        ${profilesHtml}
      </div>`;
  }

  async function loadRoleContext() {
    const params = scopeParams();
    const data = await api(`/api/role-context?${params}`);
    const body = document.getElementById("roleContextBody");
    if (!body) return; // navigated away

    const latest = data.latest_refresh;
    const nextRun = data.next_scheduled_run ? formatDateTime(data.next_scheduled_run) : "not scheduled";
    const statusHtml = !latest
      ? '<p class="muted">No role-context refresh has run yet for this system - click "Refresh role context".</p>'
      : latest.status === "success"
        ? `<p><span class="ok">Last refresh succeeded</span> &middot; ${escapeHtml(relativeTime(latest.run_at))}</p>`
        : latest.status === "success_truncated"
          ? `<p><span class="badge badge-medium">succeeded, but truncated</span> &middot;
               hit a safety cap while reading SAP - some roles/tcodes may be missing
               &middot; ${escapeHtml(relativeTime(latest.run_at))}</p>`
          : `<p class="error">Last refresh failed: ${escapeHtml(latest.error_message || "unknown error")}
               (${escapeHtml(relativeTime(latest.run_at))})</p>`;

    body.innerHTML = `
      <div class="panel" style="margin-top:1.25rem">
        <h2>Role context (PFCG roles &amp; authorized transactions)</h2>
        <p class="panel-caption">Powers the out-of-context-transaction rules - reflects roles as
          currently assigned, not a historical record of access at the time a transaction ran
          (see sal/role_context.py).</p>
        <div class="tiles">
          ${tile("Users with roles on record", data.counts.users, "tile-neutral")}
          ${tile("Distinct roles", data.counts.roles, "tile-neutral")}
          ${tile("Authorized tcodes", data.counts.tcodes, "tile-neutral")}
        </div>
        ${statusHtml}
        <p class="panel-caption">Next scheduled refresh: ${nextRun}</p>
        ${renderRoleContextHistoryTable(data.history)}
        <div style="margin-top:1.25rem; border-top:1px solid var(--border); padding-top:1rem;">
          <p class="panel-caption" style="margin-top:0">
            <strong>Look up one user's access</strong> - combines the role/tcode data above with a
            live lookup of any profiles assigned directly to that user (e.g. SAP_ALL), which role
            data alone can't show.
          </p>
          <form id="userAccessForm" class="catalogue-add-form">
            <input type="text" name="user_id" placeholder="e.g. TRAIN_13_S23" required>
            <button type="submit" class="btn-secondary">Look up</button>
          </form>
          <div id="userAccessResult"></div>
        </div>
      </div>`;

    const userAccessForm = document.getElementById("userAccessForm");
    userAccessForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const userId = userAccessForm.user_id.value.trim();
      if (!userId) return;
      const out = document.getElementById("userAccessResult");
      out.innerHTML = '<p class="muted">Looking up access&hellip;</p>';
      try {
        const result = await api(`/api/role-context/user?${scopeParams({ user_id: userId })}`);
        out.innerHTML = renderUserAccessLookup(result);
      } catch (err) {
        out.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
      }
    });
  }

  async function renderCoverage() {
    $app.innerHTML = `
      <div class="page-head">
        <h1>Coverage</h1>
        <button type="button" class="btn-primary" id="coverageCheckBtn">Check now</button>
        <div id="coverageResult"></div>
        <button type="button" class="btn-secondary" id="roleContextRefreshBtn">Refresh role context</button>
        <div id="roleContextResult"></div>
      </div>
      <div id="coverageBody">${skeleton(240)}</div>
      <div id="roleContextBody">${skeleton(200)}</div>`;

    document.getElementById("coverageCheckBtn").addEventListener("click", async () => {
      const btn = document.getElementById("coverageCheckBtn");
      const out = document.getElementById("coverageResult");
      btn.disabled = true;
      out.innerHTML = '<p class="muted">Checking live SAP configuration&hellip;</p>';
      try {
        const result = await apiWrite(`/api/audit-config/check?${scopeParams()}`, "POST");
        out.innerHTML = result.status === "success"
          ? '<p class="ok">Check complete.</p>'
          : `<p class="error">${escapeHtml(result.error || "Check failed.")}</p>`;
        await loadCoverage();
      } catch (err) {
        out.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("roleContextRefreshBtn").addEventListener("click", async () => {
      const btn = document.getElementById("roleContextRefreshBtn");
      const out = document.getElementById("roleContextResult");
      btn.disabled = true;
      out.innerHTML = '<p class="muted">Refreshing role context from live SAP&hellip;</p>';
      try {
        const result = await apiWrite(`/api/role-context/refresh?${scopeParams()}`, "POST");
        out.innerHTML = result.status === "success"
          ? `<p class="ok">Refresh complete: ${result.user_role_rows} role rows, ${result.role_tcode_rows} tcode rows.</p>`
          : result.status === "success_truncated"
            ? `<p class="badge badge-medium">Refresh completed but hit a safety cap: ${result.user_role_rows} role rows, ${result.role_tcode_rows} tcode rows - some data may be missing.</p>`
            : `<p class="error">${escapeHtml(result.error || "Refresh failed.")}</p>`;
        await loadRoleContext();
      } catch (err) {
        out.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
      } finally {
        btn.disabled = false;
      }
    });

    await Promise.all([loadCoverage(), loadRoleContext()]);
  }

  // ---- Retention (data retention purge) ------------------------------------

  function renderRetentionHistoryTable(history) {
    if (!history.length) {
      return '<p class="muted">No purge runs recorded yet.</p>';
    }
    const rows = history.map((r) => `
      <tr>
        <td>${formatDateTime(r.run_at)}</td>
        <td class="mono">${escapeHtml(r.actor)}</td>
        <td>${r.events_deleted} <span class="muted">(cutoff ${formatDateTime(r.events_cutoff)})</span></td>
        <td>${r.findings_deleted} <span class="muted">(cutoff ${formatDateTime(r.findings_cutoff)})</span></td>
      </tr>`).join("");
    return `
      <div class="table-scroll">
        <table class="findings">
          <thead><tr><th>Run at</th><th>Actor</th><th>Events deleted</th><th>Findings deleted</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  async function loadRetention() {
    const data = await api("/api/retention");
    const body = document.getElementById("retentionBody");
    if (!body) return; // navigated away
    const p = data.policy;
    const nextRun = data.next_scheduled_run ? formatDateTime(data.next_scheduled_run) : "not scheduled";

    body.innerHTML = `
      <div class="panel">
        <h2>Retention policy</h2>
        <p class="panel-caption">Owner-decided, SOX-driven policy (see Docs/Memory.md). A purge
          runs automatically once a day; you can also trigger one immediately below.</p>
        <div class="tiles">
          ${tile(`Events retention (cutoff ${formatDateTime(p.events_cutoff)})`, `${p.events_retention_days} days`, "tile-neutral")}
          ${tile(`Findings retention (cutoff ${formatDateTime(p.findings_cutoff)})`, `${p.findings_retention_days} days`, "tile-neutral")}
          ${tile("Events currently eligible for purge", p.events_eligible, "tile-medium")}
          ${tile("Findings currently eligible for purge", p.findings_eligible, "tile-medium")}
        </div>
        <p class="panel-caption" style="margin-top:1rem">Next scheduled run: ${nextRun}</p>
      </div>
      <div class="panel" style="margin-top:1.25rem">
        <h2>Purge history</h2>
        <p class="panel-caption">One row per run, even an empty one - what was purged, and
          when, is always answerable here, not just previewable beforehand.</p>
        ${renderRetentionHistoryTable(data.history)}
      </div>`;
  }

  async function renderRetention() {
    $app.innerHTML = `
      <div class="page-head">
        <h1>Retention</h1>
        <button type="button" class="btn-primary" id="retentionPurgeBtn">Run purge now</button>
        <div id="retentionResult"></div>
      </div>
      <div id="retentionBody">${skeleton(280)}</div>`;

    document.getElementById("retentionPurgeBtn").addEventListener("click", async () => {
      const btn = document.getElementById("retentionPurgeBtn");
      const out = document.getElementById("retentionResult");
      const confirmed = await confirmModal(
        "Run retention purge",
        "Run the retention purge now? This permanently deletes events and findings past their retention window. This cannot be undone.",
        { confirmLabel: "Run purge", danger: true },
      );
      if (!confirmed) return;
      btn.disabled = true;
      out.innerHTML = '<p class="muted">Running purge&hellip;</p>';
      try {
        const { result } = await apiWrite("/api/retention/purge-now", "POST");
        out.innerHTML = `<p class="ok">Purge complete: ${result.events_deleted} events, ${result.findings_deleted} findings deleted.</p>`;
        await loadRetention();
      } catch (err) {
        out.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
      } finally {
        btn.disabled = false;
      }
    });

    await loadRetention();
  }

  // ---- Router / shell wiring ------------------------------------------------

  function currentRoute() {
    return (location.hash.replace("#", "").split("?")[0]) || "";
  }

  // Home is the gate in front of every other page: with no system chosen yet
  // this browser (see state.systemChosen), any route other than /home renders
  // Home instead - a bookmarked/typed deep link to e.g. #/findings doesn't
  // error out or half-render, it just asks you to pick a system first. Once
  // chosen (from Home, or the shellbar quick-switch), every other page is
  // reachable directly again, including back-forward through browser history.
  //
  // route() coalesces overlapping calls rather than running one full render
  // per call. First attempt at this (a per-call token that re-ran route()
  // from every stale completion) was itself a real, reproduced bug: 15-20
  // rapid clicks on the same nav link each started their OWN independent
  // render (nothing stopped a second call from starting while the first
  // was still awaiting its own data), and then - because almost none of
  // them could be the single "latest" one - nearly every one of those
  // found itself superseded and reran itself too, cascading into dozens of
  // concurrent /api/systems fetches and re-renders that never visibly
  // settled (the page appeared permanently stuck on the loading skeleton).
  // The correct fix is to never let more than one render run at a time in
  // the first place: a call that arrives while one is already in flight
  // just flags that a newer navigation happened, and the in-flight call -
  // once it finishes - checks that flag and, if set, loops around for
  // exactly one more render of whatever the route is by then, however
  // many calls arrived while it was busy. At most one extra render ever
  // happens per busy period, no matter how many clicks caused it.
  let routeInFlight = false;
  let routePending = false;

  async function route() {
    if (routeInFlight) {
      routePending = true;
      return;
    }
    routeInFlight = true;
    try {
      do {
        routePending = false;
        // Defensively normalizes the visible address bar back to a plain
        // "/" + hash on every navigation, in case it ever ends up showing
        // a real path/query string instead (reported directly, from a
        // screenshot - the router itself only ever reads location.hash,
        // so this never affected what actually rendered, but a URL like
        // "/findings?job_name=&mode=...#/home" is confusing to look at).
        // replaceState only rewrites the bar - no reload, no history
        // entry, no hashchange/popstate event.
        if (location.pathname !== "/" || location.search) {
          history.replaceState(null, "", "/" + location.hash);
        }
        let r = currentRoute();
        if (!r) r = state.systemChosen ? "/dashboard" : "/home";
        // /credentials is exempt from the systemChosen gate the same way
        // /home is - managing the central credential store (which system
        // gets which password) is itself part of getting set up, same
        // reasoning as Home itself, not a page that presumes a system is
        // already selected.
        if (r !== "/home" && r !== "/credentials" && !state.systemChosen) r = "/home";

        document.body.classList.toggle("route-home", r === "/home");
        setActiveNav(r);
        try {
          if (r.startsWith("/home")) await renderHome();
          else if (r.startsWith("/credentials")) await renderCredentials();
          else if (r.startsWith("/findings")) await renderFindings();
          else if (r.startsWith("/connection")) await renderConnection();
          else if (r.startsWith("/collect")) await renderCollect();
          else if (/^\/jobs\/\d+$/.test(r)) await renderJobDetail(Number(r.split("/")[2]));
          else if (r.startsWith("/jobs")) await renderJobs();
          else if (r.startsWith("/recovery")) await renderRecovery();
          else if (r.startsWith("/coverage")) await renderCoverage();
          else if (r.startsWith("/retention")) await renderRetention();
          else if (r.startsWith("/activity")) await renderActivity();
          else await renderDashboard();
        } catch (err) {
          $app.innerHTML = `<p class="error">Failed to load this view: ${escapeHtml(err.message)}</p>`;
        }
        // Page-enter transition (see main#app.page-enter/.page-transition
        // in style.css). Content above is already swapped in synchronously,
        // so this fades/slides the *new* page into place rather than
        // fading the old one out. The instant jump to invisible must
        // happen BEFORE the transition class is added - added together,
        // the jump itself would also animate (a visible flicker, found in
        // UAT testing - GEN-03).
        $app.classList.remove("page-transition");
        $app.classList.add("page-enter");
        void $app.offsetWidth; // commit the invisible state before enabling the transition
        $app.classList.add("page-transition");
        requestAnimationFrame(() => $app.classList.remove("page-enter"));
      } while (routePending);
    } finally {
      routeInFlight = false;
    }
  }

  // Grouped by environment via <optgroup> (Development/Quality/Production/
  // Sandbox, in that order) since /api/systems now returns environment-aware
  // records. Rebuilds markup only - the change listener is attached once in
  // init(), because this function is now also called every time the systems
  // registry changes (add/edit/remove on the Home page), and re-adding a
  // listener on every call would stack duplicate handlers. Hidden via CSS
  // (body.route-home) while Home itself is showing, since its own cards are
  // the primary picker there - this is just the quick-switch for once you're
  // inside a system's pages.
  function renderSystemSelector() {
    const byEnv = new Map();
    state.systems.forEach((s) => {
      const env = SYSTEM_ENVIRONMENTS.includes(s.environment) ? s.environment : "Sandbox";
      if (!byEnv.has(env)) byEnv.set(env, []);
      byEnv.get(env).push(s);
    });
    $systemSelect.innerHTML = SYSTEM_ENVIRONMENTS
      .filter((env) => byEnv.has(env))
      .map((env) => {
        const options = byEnv.get(env)
          .map((s) => {
            const credNote = s.has_credentials ? "" : " - credentials missing";
            return `<option value="${escapeHtml(s.system_id)}|${escapeHtml(s.client)}">
              ${escapeHtml(s.description || s.system_id)} (${escapeHtml(s.system_id)} / ${escapeHtml(s.client)})${escapeHtml(credNote)}
            </option>`;
          })
          .join("");
        return `<optgroup label="${escapeHtml(env)}">${options}</optgroup>`;
      })
      .join("");
    if (state.systemId) {
      $systemSelect.value = `${state.systemId}|${state.client}`;
    }
  }

  // Shared by init() and every Home-page mutation (add/edit/remove) - keeps
  // state.systems and the shell dropdown consistent with whatever the API
  // just returned. Deliberately does NOT default state.systemId to "the
  // first system" the way it once did: an empty systemId with
  // systemChosen=false is what tells route() to show Home rather than
  // silently guessing which system the caller meant. It only reconciles a
  // *previously* selected system disappearing (removed elsewhere) - falling
  // back to another one if any remain, or back to "no selection" (and thus
  // Home) if none do.
  function syncSystemsState(items) {
    state.systems = items || [];
    const stillSelected = state.systems.find((s) => s.system_id === state.systemId);
    if (stillSelected) {
      state.client = stillSelected.client;
    } else if (state.systemId) {
      if (state.systems.length) {
        selectSystem(state.systems[0].system_id, state.systems[0].client);
        return; // selectSystem() already calls renderSystemSelector()
      }
      state.systemId = "";
      state.client = "";
      state.systemChosen = false;
      clearPersistedSystemChoice();
    }
    renderSystemSelector();
  }

  async function init() {
    try {
      const data = await api("/api/systems");
      const persisted = storedSystemChoice();
      if (persisted && (data.systems || []).some((s) => s.system_id === persisted.systemId)) {
        state.systemId = persisted.systemId;
        state.client = persisted.client;
        state.systemChosen = true;
      }
      syncSystemsState(data.systems || []);
    } catch (err) {
      console.error("Failed to load configured systems", err);
    }
    await ensureIdentity();
    $systemSelect.addEventListener("change", () => {
      const [sid, client] = $systemSelect.value.split("|");
      selectSystem(sid, client);
      route();
    });
    await route();
    window.addEventListener("hashchange", route);

    // The "Skip to main content" link (shell.html) used href="#app" -
    // clicking/activating it set location.hash to "#app", and
    // currentRoute() (which just strips the leading "#") turned that into
    // the bare string "app" - matching none of route()'s `r.startsWith(
    // "/...")` branches, so it silently fell through to the dashboard
    // fallback. Found from a real UAT report ("sometimes automatically
    // shows dashboard instead of the findings page"). Fixed by never
    // letting the skip link touch the hash at all - main#app already has
    // tabindex="-1" (shell.html), so it's programmatically focusable
    // without a hash-anchor jump.
    const skipLink = document.querySelector(".skip-link");
    if (skipLink) {
      skipLink.addEventListener("click", (e) => {
        e.preventDefault();
        $app.focus();
      });
    }

    // Clicking a nav link (sidenav item or the brand logo) to the hash
    // you're already on never fires "hashchange" (the browser only fires
    // it when the hash string actually changes) - route() then silently
    // does nothing, which read as "clicking the SAL icon sometimes doesn't
    // navigate" (a real UAT report) when the user was already on that
    // route. Re-run route() directly in that one case so the click always
    // does something.
    document.querySelectorAll(".sidenav a[data-route], .shellbar-brand").forEach((a) => {
      a.addEventListener("click", () => {
        if (location.hash === a.getAttribute("href")) route();
      });
    });

    setupExportToasts();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
