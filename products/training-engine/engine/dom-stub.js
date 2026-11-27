
const CAPTURED = ["value", "checked", "disabled", "hidden"];

function styleText(style) {
  return Object.entries(style)
    .filter(([, v]) => v !== "" && v != null)
    .map(([k, v]) => `${k.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase())}:${v}`)
    .join(";");
}

export function createStubEnv(savedStorage, seeds = {}) {
  const env = {
    downloads: [],
    promptNext: null,
    focusId: null,
    lastSent: new Map(),
  };

  const elements = new Map();

  function makeElement(tag = "div", id = "") {
    const classes = new Set();
    const el = {
      tagName: String(tag).toUpperCase(),
      id,
      children: [],
      dataset: {},
      attrs: {},
      style: null,
      download: "",
      href: "",
      _dirty: false,
      _text: "",
      _html: "",
      _lastWrite: null,
      _classes: classes,
      _props: { value: "", checked: false, disabled: false, hidden: false },
      get textContent() { return this._text; },
      set textContent(v) { this._text = String(v); this._html = ""; this._lastWrite = "text"; this._dirty = true; },
      get innerHTML() { return this._html; },
      set innerHTML(v) { this._html = String(v); this._text = ""; this._lastWrite = "html"; this._dirty = true; },
      get className() { return [...classes].join(" "); },
      set className(v) {
        classes.clear();
        String(v).split(/\s+/).filter(Boolean).forEach((c) => classes.add(c));
        this._dirty = true;
      },
      classList: {
        add: (...cs) => { cs.forEach((c) => classes.add(c)); el._dirty = true; },
        remove: (...cs) => { cs.forEach((c) => classes.delete(c)); el._dirty = true; },
        toggle: (c, force) => {
          const on = force === undefined ? !classes.has(c) : Boolean(force);
          if (on) classes.add(c); else classes.delete(c);
          el._dirty = true;
          return on;
        },
        contains: (c) => classes.has(c),
      },
      scrollTop: 0,
      addEventListener() {},
      removeEventListener() {},
      appendChild(c) { this.children.push(c); return c; },
      removeChild(c) { this.children = this.children.filter((x) => x !== c); },
      remove() {},
      insertBefore(c) { this.children.push(c); return c; },
      setAttribute(k, v) { this.attrs[k] = String(v); this._dirty = true; },
      getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
      removeAttribute(k) { delete this.attrs[k]; this._dirty = true; },
      focus() { if (this.id) env.focusId = this.id; },
      blur() {},
      click() {
        if (this.tagName === "A" && this.href.startsWith("blob:")) {
          const blob = blobs.get(this.href);
          if (blob) env.downloads.push({ name: this.download || "download", type: blob.type, bytes: blob.bytes() });
        }
      },
      closest: () => null,
      querySelector: () => makeElement(),
      querySelectorAll: () => [],
      getBoundingClientRect: () => ({ top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0 }),
      scrollIntoView() {},
      showModal() {},
      close() {},
      contains: () => false,
    };
    for (const key of CAPTURED) {
      Object.defineProperty(el, key, {
        get() { return this._props[key]; },
        set(v) { this._props[key] = v; this._dirty = true; },
      });
    }

    el.style = new Proxy({}, {
      set(target, prop, value) {
        target[prop] = value;
        el._dirty = true;
        return true;
      },
    });
    return el;
  }

  function elementById(id) {
    if (!elements.has(id)) {
      const seed = seeds[id];
      const el = makeElement(seed ? seed.tag : "div", id);
      if (seed && seed.cls) {

        String(seed.cls).split(/\s+/).filter(Boolean).forEach((c) => el._classes.add(c));
      }
      elements.set(id, el);
    }
    return elements.get(id);
  }

  const body = makeElement("body", "__body__");
  elements.set("__body__", body);

  const documentStub = {
    getElementById: elementById,
    createElement: (tag) => makeElement(tag),
    createTextNode: (t) => ({ textContent: t }),
    querySelector: () => makeElement(),
    querySelectorAll: (sel) => {
      const m = /^\.([\w-]+)$/.exec(String(sel));
      if (!m) return [];
      return [...elements.values()].filter((el) => el._classes.has(m[1]));
    },
    addEventListener() {},
    removeEventListener() {},
    body,
    documentElement: makeElement("html", "__html__"),
    activeElement: null,
    hidden: false,
  };

  const storage = new Map(savedStorage instanceof Map ? savedStorage : Object.entries(savedStorage || {}));
  const localStorageStub = {
    getItem: (k) => (storage.has(k) ? storage.get(k) : null),
    setItem: (k, v) => storage.set(k, String(v)),
    removeItem: (k) => storage.delete(k),
    clear: () => storage.clear(),
  };

  const blobs = new Map();
  let blobCounter = 0;
  class BlobStub {
    constructor(parts = [], opts = {}) {
      this.parts = parts;
      this.type = opts.type || "";
    }
    bytes() {
      const chunks = this.parts.map((p) => {
        if (p instanceof Uint8Array) return p;
        if (p instanceof ArrayBuffer) return new Uint8Array(p);
        return new TextEncoder().encode(String(p));
      });
      const total = chunks.reduce((n, c) => n + c.length, 0);
      const out = new Uint8Array(total);
      let off = 0;
      for (const c of chunks) { out.set(c, off); off += c.length; }
      return out;
    }
  }
  const URLStub = {
    createObjectURL(blob) {
      const key = `blob:stub-${blobCounter++}`;
      blobs.set(key, blob);
      return key;
    },
    revokeObjectURL(key) { blobs.delete(key); },
  };

  const windowStub = {
    document: documentStub,
    localStorage: localStorageStub,
    location: { href: "https://train.caseforge.uk/", search: "" },
    matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
    addEventListener() {},
    removeEventListener() {},
    requestAnimationFrame: () => 0,
    cancelAnimationFrame() {},
    setInterval: () => 0,
    clearInterval() {},
    setTimeout: () => 0,
    clearTimeout() {},
    prompt: () => {
      const v = env.promptNext;
      env.promptNext = null;
      return v ?? "";
    },
    alert() {},
    confirm: () => true,
    scrollTo() {},
    getComputedStyle: () => ({ getPropertyValue: () => "" }),
    navigator: { userAgent: "caseforge-training-server", clipboard: { writeText: async () => {} } },
    URL: URLStub,
    Blob: BlobStub,
    innerWidth: 1400,
    innerHeight: 900,
  };

  env.document = documentStub;
  env.window = windowStub;
  env.localStorage = localStorageStub;
  env.Blob = BlobStub;
  env.URL = URLStub;
  env.storage = storage;

  env.storageObject = () => Object.fromEntries(storage.entries());

  env.takeDownloads = () => env.downloads.splice(0);

  env.takeFocus = () => { const f = env.focusId; env.focusId = null; return f; };

  function snapshotElement(el) {
    const snap = { cls: el.className };
    if (el._lastWrite === "html") snap.html = el._html;
    else if (el._lastWrite === "text") snap.text = el._text;
    for (const key of CAPTURED) snap[key] = el._props[key];
    if (Object.keys(el.attrs).length) snap.attrs = { ...el.attrs };

    snap.style = styleText(el.style);
    return snap;
  }

  env.takePatches = (force = false) => {
    const patches = {};
    for (const [id, el] of elements) {
      if (!el._dirty) continue;
      const snap = snapshotElement(el);
      const json = JSON.stringify(snap);
      if (force || env.lastSent.get(id) !== json) {
        env.lastSent.set(id, json);
        patches[id] = snap;
      }
    }
    return patches;
  };

  return env;
}
