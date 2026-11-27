
const BASE = "/training/";

export type GameParts = Map<string, HTMLElement>;

let loading: Promise<GameParts> | null = null;

export function loadGame(): Promise<GameParts> {
  if (!loading) loading = start().catch((error) => {
    loading = null;
    throw error;
  });
  return loading;
}

export function unloadGame(): void {
  const w = window as unknown as Record<string, unknown>;
  try {
    if (typeof w.__TRAINING_DESTROY__ === "function") (w.__TRAINING_DESTROY__ as () => void)();
  } catch {

  }
  for (const id of ["demo-game-css", "demoGameHolder", "demoGameOverlays"]) document.getElementById(id)?.remove();
  for (const script of Array.from(document.querySelectorAll<HTMLScriptElement>("script[src]"))) {
    if ((script.getAttribute("src") ?? "").endsWith("/training/app.js")) script.remove();
  }
  delete w.__TRAINING_EMBED__;
  delete w.__TRAINING_BASE__;
  loading = null;
}

async function start(): Promise<GameParts> {
  const [html, css] = await Promise.all([
    fetch(BASE).then((r) => (r.ok ? r.text() : Promise.reject(new Error(`game page ${r.status}`)))),
    fetch(`${BASE}embed.css`).then((r) => (r.ok ? r.text() : Promise.reject(new Error(`game styles ${r.status}`)))),
  ]);

  const style = document.createElement("style");
  style.id = "demo-game-css";
  style.textContent = css;
  document.head.appendChild(style);

  const doc = new DOMParser().parseFromString(html, "text/html");
  const app = document.importNode(doc.querySelector(".app")!, true) as HTMLElement;

  const parts: GameParts = new Map();
  const holder = document.createElement("div");
  holder.id = "demoGameHolder";
  holder.className = "demo-game";
  holder.hidden = true;
  for (const el of Array.from(app.querySelectorAll<HTMLElement>("[data-window]"))) {
    const name = el.dataset.window!;
    if (name === "tutorial") continue;
    parts.set(name, el);
    holder.appendChild(el);
  }

  const overlays = document.createElement("div");
  overlays.id = "demoGameOverlays";
  overlays.className = "demo-game demo-game-overlays";
  overlays.appendChild(app);

  for (const el of Array.from(doc.body.children)) {
    if (el.matches(".app") || el.tagName === "SCRIPT") continue;
    overlays.appendChild(document.importNode(el, true));
  }
  document.body.append(holder, overlays);

  const w = window as unknown as Record<string, unknown>;
  w.__TRAINING_EMBED__ = true;
  w.__TRAINING_BASE__ = BASE;
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `${BASE}app.js`;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("game script failed to load"));
    document.body.appendChild(script);
  });
  return parts;
}
