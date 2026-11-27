
(() => {
  const $ = (id) => document.getElementById(id);

  const EMBED = !!window.__TRAINING_EMBED__;
  const BASE = window.__TRAINING_BASE__ || "";
  const lifecycle = new AbortController();

  const overlayRoot = () => (EMBED && document.getElementById("demoGameOverlays")) || document.body;

  let meta = {};

  let currentHintTarget = null;
  let previousNextStep = null;

  let spotlightEl = null, spotlightHoleEl = null, spotlightCaptionEl = null;
  function ensureSpotlight() {
    if (spotlightEl) return;
    spotlightEl = document.createElement("div");
    spotlightEl.className = "hint-spotlight";
    spotlightHoleEl = document.createElement("div");
    spotlightHoleEl.className = "hint-spotlight-hole";
    spotlightCaptionEl = document.createElement("div");
    spotlightCaptionEl.className = "hint-spotlight-caption";
    spotlightEl.appendChild(spotlightHoleEl);
    spotlightEl.appendChild(spotlightCaptionEl);
    overlayRoot().appendChild(spotlightEl);
  }

  function positionSpotlight(el, caption) {
    ensureSpotlight();
    const r = el.getBoundingClientRect();
    const pad = 6;
    spotlightHoleEl.style.top = (r.top - pad) + "px";
    spotlightHoleEl.style.left = (r.left - pad) + "px";
    spotlightHoleEl.style.width = (r.width + pad * 2) + "px";
    spotlightHoleEl.style.height = (r.height + pad * 2) + "px";
    spotlightCaptionEl.textContent = caption || "";
    spotlightCaptionEl.hidden = !caption;

    const headerEl = document.querySelector("header");
    const minTop = headerEl ? headerEl.getBoundingClientRect().bottom + 8 : 8;
    const captionTop = r.bottom + pad + 10;
    const fitsBelow = captionTop + 60 < window.innerHeight;
    spotlightCaptionEl.style.top = (fitsBelow ? captionTop : Math.max(minTop, r.top - pad - 70)) + "px";
    spotlightCaptionEl.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 328)) + "px";
    spotlightEl.classList.add("visible");
  }

  function hideSpotlight() {
    if (spotlightEl) spotlightEl.classList.remove("visible");
  }

  window.addEventListener("resize", () => {
    if (currentHintTarget && spotlightEl && spotlightEl.classList.contains("visible")) {

      const el = document.querySelector(currentHintTarget);
      if (el) positionSpotlight(el, spotlightCaptionEl.textContent);
    }
  }, { signal: lifecycle.signal });

  function dismissHint() {
    if (!currentHintTarget) return;
    clearHintHighlight();
    tutorialActive = false;
  }

  document.addEventListener("click", (event) => {
    if (!currentHintTarget) return;
    const target = document.querySelector(currentHintTarget);

    if (target && (target === event.target || target.contains(event.target))) return;

    if (event.target.closest && event.target.closest(".modal-backdrop")) return;
    dismissHint();
  }, { capture: true, signal: lifecycle.signal });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && currentHintTarget) dismissHint();
  }, { signal: lifecycle.signal });

  function clearHintHighlight() {
    if (!currentHintTarget) return;
    currentHintTarget = null;
    hideSpotlight();
  }

  function showHint() {
    const cards = (meta.board && meta.board.cards) || [];
    const card = cards.find((c) => c.active);
    let selector = "#stepCard";
    let caption = "Caseflow is working on this case. Watch what the system does.";
    if (card && card.closedAs) {
      return;
    }
    if (card && card.waiting) {
      selector = "#clientDraftSendBtn";
      caption = "Your turn: read the draft, then press Send.";
    } else if (card && card.column === "concluded") {
      return;
    }
    const el = document.querySelector(selector);
    if (!el || !el.offsetParent) return;
    clearHintHighlight();
    currentHintTarget = selector;
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    setTimeout(() => positionSpotlight(el, caption), 260);
  }

  let tutorialActive = true;

  function maybeShowTutorialHint() {
    if (tutorialActive && !playing) showHint();
  }

  let queue = Promise.resolve();
  function send(action) {
    queue = queue.then(() => post(action)).catch(() => {});
    return queue;
  }
  async function post(action) {
    let res;
    try {
      res = await fetch(BASE + "api/action", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(action),
      });
    } catch {

      markSessionStale();
      return;
    }
    if (res.status === 401 || res.status === 403) {
      markSessionStale();
      return;
    }
    if (!(res.headers.get("content-type") || "").includes("application/json")) {

      markSessionStale();
      return;
    }
    if (!res.ok) {
      $("statusText").textContent = "The server rejected that action (" + res.status + ").";
      return;
    }
    apply(await res.json());
    return true;
  }

  const BANNER_POLL_MS = 30000;
  const BANNER_WARN_BEFORE_MS = 5 * 60000;

  function compareBuildId(baseline, buildId) {
    if (!buildId) return { baseline, changed: false };
    if (baseline === null) return { baseline: buildId, changed: false };
    return { baseline, changed: buildId !== baseline };
  }

  function nextBannerState(current, signal) {

    if (current === "session-stale") return current;
    if (signal.kind === "stale") return "session-stale";
    let next = current;
    if (signal.versionChanged && next === "none") next = "new-version";
    if (typeof signal.sessionExpiresAt === "number") {
      const remaining = signal.sessionExpiresAt - signal.now;
      if (remaining <= 0) return "session-stale";
      if (remaining <= BANNER_WARN_BEFORE_MS && (next === "none" || next === "session-expiring-soon")) {
        next = "session-expiring-soon";
      }
    }
    return next;
  }

  let bannerState = "none";
  let bannerBaselineBuildId = null;
  let bannerExpiresAt = null;

  function formatClock(ms) {
    return new Date(ms).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  }

  function renderBanner() {

    if (EMBED) return;
    const update = $("updateBanner");
    const stale = $("sessionStaleBanner");
    if (!update || !stale) return;
    const showStale = bannerState === "session-stale";
    const showUpdate = bannerState === "new-version" || bannerState === "session-expiring-soon";
    const layoutChanged = update.hidden === showUpdate || stale.hidden === showStale;
    update.hidden = !showUpdate;
    stale.hidden = !showStale;
    if (showUpdate) {
      update.querySelector(".refresh-banner-text").textContent = bannerState === "new-version"
        ? "A new version of the Training Guide is available."
        : "Your session expires around " + (bannerExpiresAt ? formatClock(bannerExpiresAt) : "soon") + ". Refresh to stay logged in.";
    }

    if (layoutChanged) window.dispatchEvent(new Event("resize"));
  }

  function applyBannerSignal(signal) {
    const next = nextBannerState(bannerState, signal);
    if (next !== bannerState) {
      bannerState = next;
      document.querySelectorAll(".refresh-banner-note").forEach((n) => { n.hidden = true; });
    }
    renderBanner();
  }

  function markSessionStale() {
    applyBannerSignal({ kind: "stale" });
  }

  async function pollVersion() {
    if (bannerState === "session-stale") return;
    try {
      const res = await fetch(BASE + "api/version", { cache: "no-store" });
      if (res.status === 401 || res.status === 403) { markSessionStale(); return; }
      if (!(res.headers.get("content-type") || "").includes("application/json")) {
        markSessionStale();
        return;
      }
      const body = await res.json();
      const compared = compareBuildId(bannerBaselineBuildId, body.buildId);
      bannerBaselineBuildId = compared.baseline;
      if (typeof body.sessionExpiresAt === "number") bannerExpiresAt = body.sessionExpiresAt;
      applyBannerSignal({
        kind: "poll",
        versionChanged: compared.changed,
        sessionExpiresAt: typeof body.sessionExpiresAt === "number" ? body.sessionExpiresAt : null,
        now: Date.now(),
      });
    } catch {

      markSessionStale();
    }
  }

  function refreshFromBanner() {
    location.reload();
  }

  document.querySelectorAll(".refresh-banner button").forEach((b) => b.addEventListener("click", refreshFromBanner));
  pollVersion();
  const pollTimer = setInterval(pollVersion, BANNER_POLL_MS);

  if (EMBED) {
    window.__TRAINING_DESTROY__ = () => {
      lifecycle.abort();
      clearInterval(pollTimer);
      delete window.__TRAINING_DESTROY__;
    };
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) pollVersion();
  }, { signal: lifecycle.signal });

  const CRM_MAP_KEY = "crmClients";
  const CRM = EMBED ? location.origin : "";
  function crmMap() {
    try { return JSON.parse(sessionStorage.getItem(CRM_MAP_KEY) || "{}"); } catch { return {}; }
  }
  function crmSave(map) {
    try { sessionStorage.setItem(CRM_MAP_KEY, JSON.stringify(map)); } catch {   }
  }
  const crmPending = new Set();
  async function crmPost(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error(String(res.status));
    return res.json();
  }

  function crmTellPage() {
    window.dispatchEvent(new Event("caseforge:assignment-changed"));
  }

  async function crmFind(email) {
    try {
      const res = await fetch("/api/clients/search?q=" + encodeURIComponent(email));
      if (!res.ok) return null;
      const body = await res.json();
      const hit = (body.results || []).find((r) => String(r.email_primary || "").toLowerCase() === email.toLowerCase());
      return hit ? String(hit.matter_id) : null;
    } catch { return null; }
  }

  function crmSync(board) {
    if (!CRM) return;
    const cards = (board && board.cards) || [];
    const map = crmMap();
    for (const card of cards) {
      if (map[card.id] || crmPending.has(card.id) || !card.email) continue;
      const d = card.details || {};
      crmPending.add(card.id);
      crmFind(card.email).then((found) => found ? { matter_id: found } : crmPost("/api/new-client", {
        first_name: d.first, last_name: d.last, email: card.email,
        category: "nmo_cao", by: "Training game", stub_details: card.details || undefined
      })).then((made) => {
        const next = crmMap();
        next[card.id] = String(made.matter_id);
        crmSave(next);
        crmTellPage();
      }).catch(() => {}).finally(() => crmPending.delete(card.id));
    }
    const live = new Set(cards.map((c) => c.id));
    for (const [cardId, matterId] of Object.entries(map)) {
      if (live.has(cardId)) continue;
      const next = crmMap();
      delete next[cardId];
      crmSave(next);
      crmPost("/api/clients/removed", {
        action: "remove", matter_id: matterId, by: "Training game",
        typed_name: "training game", reason: "case removed in the training game"
      }).then(crmTellPage).catch(() => {});
    }
  }
  if (EMBED) {

    const inboxHeading = document.querySelector('[data-window="inbox"] .panel-title');
    const plus = $("newMatterBtn");
    if (inboxHeading && plus) inboxHeading.appendChild(plus);
  }

  function openCrmBeside() {
    const w = Math.floor(screen.availWidth / 2);
    const features = `left=${screen.availLeft + w},top=${screen.availTop},width=${w},height=${screen.availHeight}`;
    window.open(CRM + "/", "caseforge-demo-crm", features);
  }
  const openCrmBtn = $("openCrmBtn");

  if (openCrmBtn && CRM && !EMBED) {
    openCrmBtn.hidden = false;
    openCrmBtn.addEventListener("click", openCrmBeside);
  }

  function apply(payload) {
    const patches = payload.patches || {};
    for (const [id, p] of Object.entries(patches)) {
      if (EMBED && (id === "__body__" || id === "__html__")) continue;
      const el = id === "__body__" ? document.body
        : id === "__html__" ? document.documentElement
        : $(id);
      if (!el) continue;
      if ("html" in p) el.innerHTML = p.html;
      else if ("text" in p) el.textContent = p.text;
      el.className = p.cls;
      if (p.attrs) for (const [k, v] of Object.entries(p.attrs)) el.setAttribute(k, v);
      if (p.style !== undefined) el.style.cssText = p.style;
      if ("value" in p && el.value !== p.value && el !== document.activeElement) el.value = p.value;
      if ("checked" in p) el.checked = p.checked;
      if ("disabled" in p) el.disabled = p.disabled;
      if ("hidden" in p) el.hidden = p.hidden;
    }
    meta = payload.meta || meta;
    if (meta.focus) { const f = $(meta.focus); if (f) f.focus(); }
    (meta.downloads || []).forEach(download);

    if (meta.buildSha) {
      const badge = $("buildBadge");
      if (badge) badge.textContent = "Build " + meta.buildSha.slice(0, 7);
    }
    if (meta.nextStep !== previousNextStep) {
      clearHintHighlight();
      previousNextStep = meta.nextStep;
      maybeShowTutorialHint();
    }
    renderBoard(meta.board);
    pruneCaseEvents(meta.board);
    crmSync(meta.board);
    updateControls();
    if (!meta.caseflow) showNextCard();
    if (EMBED) window.dispatchEvent(new CustomEvent("caseforge-demo-changed"));
  }

  window.trainingApi = {

    act: (action) => send(action),

    state: () => fetch(BASE + "api/state").then((r) => r.json()),
  };

  function escHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  function download(d) {
    const bin = atob(d.b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const url = URL.createObjectURL(new Blob([bytes], { type: d.type || "application/octet-stream" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = d.name || "download";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }

  function on(id, type, fn) { const el = $(id); if (el) el.addEventListener(type, fn); }

  function selectRow(row) {
    send({ type: "select-email", id: row.dataset.emailId });
  }

  on("emailRows", "click", (event) => {
    const del = event.target.closest("[data-delete-email]");
    if (del) { send({ type: "delete-email", id: del.dataset.deleteEmail }); return; }
    const row = event.target.closest("[data-email-id]");
    if (row) selectRow(row);
  });
  on("emailRows", "keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const row = event.target.closest("[data-email-id]");
    if (!row) return;
    event.preventDefault();
    selectRow(row);
  });

  on("message", "click", (event) => {
    const preview = event.target.closest("[data-preview-name]");
    if (preview) send({ type: "preview-name", name: preview.dataset.previewName });
  });

  on("explorerTree", "click", (event) => {
    const extract = event.target.closest("[data-extract-zip]");
    if (extract) { send({ type: "extract-zip", id: extract.dataset.extractZip }); return; }
    const preview = event.target.closest("[data-preview-node]");
    if (preview) { send({ type: "preview-node", id: preview.dataset.previewNode }); return; }
    const toggle = event.target.closest("[data-toggle-folder]");
    if (toggle) { send({ type: "toggle-folder", id: toggle.dataset.toggleFolder }); return; }
    const folderLine = event.target.closest("[data-drop-folder]");
    if (folderLine) { send({ type: "select-folder", id: folderLine.dataset.dropFolder }); return; }
    const caseLine = event.target.closest("[data-case-email]");
    if (caseLine) send({ type: "select-email", id: caseLine.dataset.caseEmail });
  });
  on("explorerTree", "keydown", (event) => {
    const folderLine = event.target.closest("[data-drop-folder]");
    if (!folderLine) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      send({ type: "select-folder", id: folderLine.dataset.dropFolder });
    } else if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      send({ type: "toggle-folder", id: folderLine.dataset.dropFolder });
    }
  });

  on("newMatterBtn", "click", () => send({ type: "new-matter" }).then((applied) => { if (applied) resumeCaseflow(); }));
  on("hintToggleBtn", "click", () => {
    tutorialActive = true;
    showHint();
  });
  on("stageJumpSelect", "change", (event) => {
    send({ type: "stage-jump", value: event.target.value });
    event.target.value = "";
  });
  on("sortFoldersBtn", "click", () => send({ type: "sort-folders" }));
  on("resetAllBtn", "click", () => {
    if (confirm("Reset all training data? This clears every matter on this device and cannot be undone.")) {
      send({ type: "reset-all" });
    }
  });

  on("clientDraftSendBtn", "click", () => {

    const btn = $("clientDraftSendBtn");
    if (btn) btn.disabled = true;
    send({ type: "draft-send" }).then((applied) => {
      if (!applied && btn) btn.disabled = false;
      else resumeCaseflow();
    });
  });

  on("modalCloseBtn", "click", () => send({ type: "modal-close" }));
  on("modalBackdrop", "click", (event) => {
    if (event.target === $("modalBackdrop")) send({ type: "modal-close" });
  });
  on("modalBody", "click", (event) => {
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if ($("modalBackdrop").classList.contains("visible")) { send({ type: "modal-close" }); return; }
  }, { signal: lifecycle.signal });

  const THEME_KEY = "caseforge-training-theme-v1";

  function setFavicon(mode) {
    const link = document.querySelector('link[rel="icon"][type="image/svg+xml"]');
    if (!link || !link.dataset) return;
    const next = mode === "dark" ? link.dataset.dark : link.dataset.light;
    if (next && link.href.indexOf(next) === -1) link.href = next;
  }

  function storedThemePref() {
    try {
      return localStorage.getItem(THEME_KEY) || "auto";
    } catch (err) {
      return "auto";
    }
  }

  function applyTheme(pref) {
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const mode = pref === "auto" ? (systemDark ? "dark" : "light") : pref;
    document.documentElement.setAttribute("data-theme", mode);
    document.documentElement.dataset.themePref = pref;
    setFavicon(mode);
    document.querySelectorAll(".theme-btn").forEach((b) => {
      const active = b.dataset.t === pref;
      b.classList.toggle("active", active);
      b.setAttribute("aria-pressed", String(active));
    });
  }

  if (EMBED) {

    document.querySelectorAll(".theme-group").forEach((g) => { g.hidden = true; });
  } else applyTheme(storedThemePref());

  if (!EMBED) document.querySelectorAll(".theme-btn").forEach((b) => {
    b.addEventListener("click", () => {
      const pref = b.dataset.t;
      try {
        localStorage.setItem(THEME_KEY, pref);
      } catch (err) {

      }
      applyTheme(pref);
    });
  });

  if (!EMBED) window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (storedThemePref() === "auto") applyTheme("auto");
  });

  const boardEl = $("caseBoardColumns");
  const card = {
    root: $("stepCard"), title: $("stepCardTitle"), label: $("stepCardLabel"), why: $("stepCardWhy"), real: $("stepCardReal"), close: $("stepCardClose")
  };
  let cardHidden = false;
  const CARD_TITLES = { auto: "What the system just did", human: "Your turn", closed: "Closed", done: "Finished", stuck: "Caseflow stopped", none: "Nothing open" };
  let playing = false;
  let busy = false;

  function renderBoard(board) {
    if (!boardEl || !board) return;
    const before = new Map();
    boardEl.querySelectorAll("[data-chip]").forEach((el) => before.set(el.dataset.chip, el.getBoundingClientRect()));
    const byColumn = {};
    board.cards.forEach((card) => { (byColumn[card.column] = byColumn[card.column] || []).push(card); });
    boardEl.innerHTML = board.columns.map((col, i) => {
      const cards = byColumn[col.key] || [];
      const chips = cards.map((c) => {
        const tip = escHtml(c.name) + (c.waiting ? ", waiting for you" : "");
        return `<button type="button" class="board-chip" data-chip="${escHtml(c.id)}" data-waiting="${c.waiting}" data-active="${c.active}" data-closed="${c.closedAs ? "true" : "false"}" title="${tip}" aria-label="${tip}">${escHtml(c.name.charAt(0))}</button>`;
      }).join("");
      return `<div class="board-col" data-col="${escHtml(col.key)}" data-empty="${cards.length ? "false" : "true"}">
        <div class="board-col-head"><span class="board-col-number">${i + 1}</span><span class="board-col-label">${escHtml(col.label)}</span>${cards.length ? `<span class="board-col-count">${cards.length}</span>` : ""}</div>
        <div class="board-col-body">${chips}</div>
      </div>`;
    }).join("");
    boardEl.querySelectorAll("[data-chip]").forEach((el) => {
      el.addEventListener("click", () => send({ type: "select-email", id: el.dataset.chip }));
      const was = before.get(el.dataset.chip);
      if (!was || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      const now = el.getBoundingClientRect();
      const dx = was.left - now.left;
      const dy = was.top - now.top;
      if (dx || dy) {
        el.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }], { duration: 650, easing: "ease-in-out" });
      }
    });
  }

  const CURSOR_SVG = '<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true"><path d="M5 3l14 8-6 1.8L10.5 19z" fill="#fff" stroke="#1b1d22" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  function flyOne(label, toId, duration) {

    if (document.hidden) return Promise.resolve();
    const dest = document.querySelector('[data-node-id="' + toId + '"]');
    const source = document.querySelector("[data-incoming-attachment-id], #zipAttachment") || $("message");
    if (!dest || !source) return Promise.resolve();
    dest.scrollIntoView({ block: "nearest" });
    return flyPath(label, source.getBoundingClientRect(), dest, duration);
  }

  function flyPath(label, from, dest, duration) {
    const to = dest.getBoundingClientRect();
    const x0 = from.left + 24, y0 = from.top + 18;
    const x1 = to.left + Math.min(40, to.width / 2), y1 = to.top + to.height / 2;
    const dx = x1 - x0, dy = y1 - y0;
    const flyer = document.createElement("div");
    flyer.className = "flyer";
    flyer.textContent = label;
    flyer.style.left = x0 + 14 + "px";
    flyer.style.top = y0 + 10 + "px";
    const pointer = document.createElement("div");
    pointer.className = "demo-pointer";
    pointer.innerHTML = CURSOR_SVG;
    pointer.style.left = x0 + "px";
    pointer.style.top = y0 + "px";
    const root = overlayRoot();
    root.appendChild(flyer);
    root.appendChild(pointer);
    flyer.style.opacity = "0";
    dest.classList.add("drop-target");
    const ease = "cubic-bezier(.45,.05,.25,1)";
    const grab = 260, drop = 320;
    const total = grab + duration + drop;
    const keep = { fill: "forwards", easing: ease };

    const pointerMotion = pointer.animate([
      { transform: "translate(-36px, 30px) scale(1)", opacity: 0, offset: 0 },
      { transform: "translate(0, 0) scale(1)", opacity: 1, offset: grab * 0.6 / total },
      { transform: "translate(0, 0) scale(0.82)", opacity: 1, offset: grab / total },
      { transform: `translate(${dx}px, ${dy}px) scale(0.82)`, opacity: 1, offset: (grab + duration) / total },
      { transform: `translate(${dx}px, ${dy}px) scale(1)`, opacity: 1, offset: (grab + duration + drop * 0.5) / total },
      { transform: `translate(${dx + 30}px, ${dy + 24}px) scale(1)`, opacity: 0, offset: 1 }
    ], { duration: total, ...keep });

    flyer.animate([
      { transform: "translate(0, 0) scale(1)", opacity: 0, offset: 0 },
      { transform: "translate(0, 0) scale(1)", opacity: 0, offset: grab * 0.6 / total },
      { transform: "translate(0, 0) scale(1.04)", opacity: 1, offset: grab / total },
      { transform: `translate(${dx}px, ${dy}px) scale(1.04)`, opacity: 1, offset: (grab + duration) / total },
      { transform: `translate(${dx}px, ${dy}px) scale(0.6)`, opacity: 0, offset: (grab + duration + drop * 0.6) / total },
      { transform: `translate(${dx}px, ${dy}px) scale(0.6)`, opacity: 0, offset: 1 }
    ], { duration: total, ...keep });
    const ripple = document.createElement("div");
    ripple.className = "demo-ripple";
    ripple.style.left = x1 + "px";
    ripple.style.top = y1 + "px";
    const rippleTimer = setTimeout(() => {
      root.appendChild(ripple);
      dest.classList.add("flash");
      ripple.animate([{ transform: "translate(-50%, -50%) scale(0.2)", opacity: 0.7 }, { transform: "translate(-50%, -50%) scale(2.4)", opacity: 0 }], { duration: 520, easing: "ease-out" });
    }, grab + duration);
    const done = () => {
      clearTimeout(rippleTimer);
      flyer.remove();
      pointer.remove();
      setTimeout(() => { ripple.remove(); dest.classList.remove("flash", "drop-target"); }, 300);
    };

    const timeout = new Promise((resolve) => setTimeout(resolve, total + 400));
    return Promise.race([pointerMotion.finished, timeout]).then(done, done);
  }

  async function flyChip(event) {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (event.moves && event.moves.length) {
      const duration = event.moves.length > 1 ? 650 : 1000;
      for (const move of event.moves) await flyOne(move.file, move.toId, duration);
      return;
    }
    if (event.toId) await flyOne((event.files && event.files[0]) || "Document", event.toId, 1000);
  }

  function showCard(event) {
    if (!card.root || cardHidden) return;
    card.root.hidden = false;
    card.root.dataset.kind = event.kind;
    card.title.textContent = event.title || CARD_TITLES[event.kind] || "";
    card.label.textContent = event.label || "";
    card.why.textContent = event.explain || "";
    card.why.hidden = !event.explain;
    if (card.real) { card.real.textContent = event.real || ""; card.real.hidden = !event.real; }
  }

  function showNextCard() {
    const info = meta.stepInfo;
    if (!info) { if (card.root) card.root.hidden = true; return; }
    if (info.closed) return showCard({ kind: "closed", label: "This case is closed.", explain: info.explain });
    if (info.done) return showCard({ kind: "done", label: "The case is concluded.", explain: info.explain });
    showCard({ kind: info.human ? "human" : "auto", title: info.human ? "Your turn" : "Next", label: info.label, explain: info.explain, real: info.real });
  }

  async function runUnit() {
    cardHidden = false;
    const cards = (meta.board && meta.board.cards) || [];
    if (cards.length && !cards.some((c) => c.active)) await send({ type: "select-email", id: cards[0].id });
    clearHintHighlight();
    const ok = await send({ type: "caseflow-next" });
    const event = meta.caseflow;
    if (!ok || !event) { showCard({ kind: "stuck", label: "Could not reach the server.", explain: "" }); return null; }
    showCard(event);
    const active = activeCard();
    if (active && event.kind === "auto") recordEvent(active.id, event.step, "auto", event.label);
    if (event.kind === "auto") await flyChip(event);

    if (event.kind === "auto" || event.kind === "human") {
      const sent = await autoSendIfSafe();
      if (sent) {
        const done = { ...event, kind: "auto", title: "What the system just did", label: event.kind === "auto" ? `${event.label.replace(/\s*Nothing has been sent\.?$/i, "")} ${sent.label}` : sent.label, explain: "This email is on the send gate's safelist, so it is sent automatically, whether Case flow is Auto or Manual. Every other email waits for a person to press Send." };
        showCard(done);
        return done;
      }
    }
    if (event.kind === "human") showHint();
    return event;
  }

  const AUTO_SEND_DRAFT_KINDS = ["client", "docusign", "revision"];

  const AUTO_READ_PAUSE_MS = 2500;
  async function autoSendIfSafe() {
    const c = activeCard();
    if (!c || !c.waiting || !c.draft) return null;
    const safelist = AUTO_SEND_DRAFT_KINDS.includes(String(c.draft.type).replace(/-\d+$/, ""));
    if (!safelist && !autoRun) return null;
    if (!safelist) {
      await new Promise((resolve) => setTimeout(resolve, AUTO_READ_PAUSE_MS));

      const still = activeCard();
      if (!autoRun || !still || still.id !== c.id || !still.waiting || !still.draft) return null;
    }
    const label = safelist ? `Sent automatically: ${c.draft.subject}.` : `Sent by Case flow (Auto): ${c.draft.subject}.`;
    const ok = await send({ type: "draft-send" });
    if (!ok) return null;
    recordEvent(c.id, c.step, "auto", label);
    return { label };
  }

  function resumeCaseflow() {
    const c = activeCard();
    if (autoRun && c && !c.closedAs && !c.waiting) play();
  }

  let autoRun = true;

  const modePill = document.createElement("button");
  modePill.type = "button";
  modePill.className = "mode-pill";
  modePill.setAttribute("role", "switch");
  modePill.innerHTML = '<span data-side="auto" aria-hidden="true">Auto</span><span data-side="manual" aria-hidden="true">Manual</span>';
  modePill.addEventListener("click", () => {
    autoRun = !autoRun;
    if (!autoRun) playing = false;
    paintModePill();
    window.dispatchEvent(new CustomEvent("training-demo-mode", { detail: { auto: autoRun } }));
    if (autoRun) resumeCaseflow();
  });
  function paintModePill() {
    modePill.setAttribute("aria-checked", String(autoRun));
    modePill.setAttribute("aria-label", `Case flow mode: ${autoRun ? "Auto" : "Manual"}`);
    modePill.title = `${autoRun ? "Auto: Case flow runs by itself" : "Manual: nothing runs until you press a button"}. Click to switch to ${autoRun ? "Manual" : "Auto"}.`;
  }
  if (EMBED) {
    const heading = document.querySelector('[data-window="inbox"] .panel-title');
    if (heading) heading.appendChild(modePill);
    paintModePill();
  }
  const caseEvents = {};
  function recordEvent(cardId, step, kind, label) {
    const list = (caseEvents[cardId] = caseEvents[cardId] || []);
    list.push({ at: new Date().toISOString(), step: step || "", kind, label: label || "" });
    if (list.length > 200) list.shift();
    try { sessionStorage.setItem("crmCaseEvents", JSON.stringify(caseEvents)); } catch (err) {   }
  }
  try { Object.assign(caseEvents, JSON.parse(sessionStorage.getItem("crmCaseEvents") || "{}")); } catch (err) {   }

  function pruneCaseEvents(board) {
    if (!board) return;
    const live = new Set(board.cards.map((c) => c.id));
    let changed = false;
    Object.keys(caseEvents).forEach((id) => { if (!live.has(id)) { delete caseEvents[id]; changed = true; } });
    if (changed) { try { sessionStorage.setItem("crmCaseEvents", JSON.stringify(caseEvents)); } catch (err) {   } }
  }

  async function selectCase(cardId) {
    const active = activeCard();
    if (!active || active.id !== cardId) await send({ type: "select-email", id: cardId });
  }

  if (EMBED) {
    window.__trainingDemo = {
      cards() {
        const map = crmMap();
        return ((meta.board && meta.board.cards) || []).map((c) => ({ ...c, matterId: map[c.id] || undefined }));
      },
      cardForMatter(matterId) {
        return this.cards().find((c) => c.matterId === String(matterId)) || null;
      },
      events(cardId) { return (caseEvents[cardId] || []).slice(); },
      async run(cardId) {
        if (busy) return null;
        busy = true;
        try {
          await selectCase(cardId);
          const event = await runUnit();
          return event ? { kind: event.kind, label: event.label || "" } : null;
        } finally {
          busy = false;
        }
      },
      async send(cardId) {
        await selectCase(cardId);
        const card = activeCard();
        const label = card && card.draft ? card.draft.subject : "the email";
        const ok = await send({ type: "draft-send" });
        if (ok) {
          recordEvent(cardId, card ? card.step : "", "human", `Sent: ${label}.`);
          resumeCaseflow();
        }
        return Boolean(ok);
      },
      setAuto(on) {
        autoRun = Boolean(on);
        if (!autoRun) playing = false;
        paintModePill();
      },
      auto() { return autoRun; }
    };
  }

  async function play() {
    if (busy) return;
    busy = true;
    playing = true;
    try {
      while (playing) {
        const event = await runUnit();
        if (!event || event.kind !== "auto") break;
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
    } finally {
      playing = false;
      busy = false;
    }
  }

  const intake = { closeSelect: $("closeSelect") };
  let closeOptionsFor = null;
  const CLOSE_OPTIONS = { concluded: "Concluded", transferred: "Transferred", "dropped-out": "Dropped out" };

  function activeCard() {
    return ((meta.board && meta.board.cards) || []).find((c) => c.active) || null;
  }

  function updateControls() {
    if (!intake.closeSelect) return;
    const c = activeCard();
    const optionsKey = c ? (c.closedAs ? "closed:" + c.closedAs : "open") : "none";
    if (optionsKey !== closeOptionsFor) {
      closeOptionsFor = optionsKey;
      intake.closeSelect.innerHTML = c && c.closedAs
        ? `<option value="">Closed: ${escHtml(CLOSE_OPTIONS[c.closedAs])}</option><option value="open">Reopen case</option>`
        : '<option value="">Close case&hellip;</option>' + Object.entries(CLOSE_OPTIONS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
    }
    intake.closeSelect.disabled = !c;
  }

  on("closeSelect", "change", async () => {
    const kind = intake.closeSelect.value;
    if (!kind) return;
    await send({ type: "close-case", kind });
  });

  if (EMBED && card.root) {
    const head = card.root.querySelector(".step-card-head");
    const POS_KEY = "stepCardPos";
    const place = (x, y) => {
      const maxX = window.innerWidth - 60;
      const maxY = window.innerHeight - 40;
      card.root.style.left = Math.min(Math.max(x, 0), maxX) + "px";
      card.root.style.top = Math.min(Math.max(y, 0), maxY) + "px";
      card.root.style.right = "auto";
      card.root.style.bottom = "auto";
    };
    try {
      const saved = JSON.parse(sessionStorage.getItem(POS_KEY) || "null");
      if (saved) place(saved.x, saved.y);
    } catch {   }
    if (head) {
      head.style.cursor = "grab";
      head.style.touchAction = "none";
      let from = null;
      head.addEventListener("pointerdown", (event) => {
        if (event.target.closest("button")) return;
        const r = card.root.getBoundingClientRect();
        from = { px: event.clientX, py: event.clientY, x: r.left, y: r.top };
        head.setPointerCapture(event.pointerId);
      });
      head.addEventListener("pointermove", (event) => {
        if (from) place(from.x + event.clientX - from.px, from.y + event.clientY - from.py);
      });
      const drop = () => {
        if (!from) return;
        from = null;
        try {
          const r = card.root.getBoundingClientRect();
          sessionStorage.setItem(POS_KEY, JSON.stringify({ x: r.left, y: r.top }));
        } catch {   }
      };
      head.addEventListener("pointerup", drop);
      head.addEventListener("pointercancel", drop);
    }
  }
  on("stepCardClose", "click", () => {
    cardHidden = true;
    if (card.root) card.root.hidden = true;
  });

  fetch(BASE + "api/state")
    .then((res) => res.json())
    .then(apply)
    .then(() => resumeCaseflow())
    .catch(() => { $("statusText").textContent = "Could not reach the training server."; });
})();
