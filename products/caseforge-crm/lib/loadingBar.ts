
export interface LoadingBarState {
  visible: boolean;

  waiting: string[];

  progress: number;
}

export const SHOW_DELAY_MS = 120;
export const TRICKLE_MS = 200;
export const FINISH_MS = 250;

export function nextProgress(progress: number): number {
  if (progress >= 90) return 90;
  return Math.min(90, progress + Math.max(1, (90 - progress) * 0.12));
}

type Listener = () => void;

export function createLoadingBar() {
  let pending = 0;
  let state: LoadingBarState = { visible: false, progress: 0, waiting: [] };
  const waitingOn: string[] = [];
  let showTimer: ReturnType<typeof setTimeout> | undefined;
  let trickleTimer: ReturnType<typeof setInterval> | undefined;
  let finishTimer: ReturnType<typeof setTimeout> | undefined;
  const listeners = new Set<Listener>();

  function set(next: LoadingBarState) {
    state = next;
    listeners.forEach((l) => l());
  }

  function show() {
    showTimer = undefined;
    if (pending === 0) return;
    if (finishTimer) {
      clearTimeout(finishTimer);
      finishTimer = undefined;
    }
    set({ visible: true, progress: 8, waiting: [...waitingOn] });
    trickleTimer = setInterval(() => set({ visible: true, progress: nextProgress(state.progress), waiting: [...waitingOn] }), TRICKLE_MS);
  }

  function begin(label = "") {
    pending += 1;
    waitingOn.push(label || "page");
    if (pending === 1 && !state.visible && showTimer === undefined) showTimer = setTimeout(show, SHOW_DELAY_MS);
  }

  function end(label = "") {
    if (pending === 0) return;
    pending -= 1;
    const at = waitingOn.indexOf(label || "page");
    if (at >= 0) waitingOn.splice(at, 1);
    if (pending > 0) return;
    if (showTimer !== undefined) {
      clearTimeout(showTimer);
      showTimer = undefined;
    }
    if (trickleTimer) {
      clearInterval(trickleTimer);
      trickleTimer = undefined;
    }
    if (state.visible) {
      set({ visible: true, progress: 100, waiting: [] });
      finishTimer = setTimeout(() => {
        finishTimer = undefined;
        if (pending === 0) set({ visible: false, progress: 0, waiting: [] });
      }, FINISH_MS);
    }
  }

  return {
    begin,
    end,
    pending: () => pending,
    getState: () => state,
    subscribe(listener: Listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

export const loadingBar = createLoadingBar();

let backgroundDepth = 0;
export function runInBackground<T>(fn: () => T): T {
  backgroundDepth += 1;
  try {
    return fn();
  } finally {
    backgroundDepth -= 1;
  }
}

const BACKGROUND_INITS = new WeakSet<object>();

export function backgroundFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const own: RequestInit = { ...(init ?? {}) };
  BACKGROUND_INITS.add(own);
  return fetch(input, own);
}

export function isMarkedBackground(init: unknown): boolean {
  return typeof init === "object" && init !== null && BACKGROUND_INITS.has(init);
}

export function inBackground(): boolean {
  return backgroundDepth > 0;
}

export function requestLabel(input: unknown): string {
  try {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : (input as Request)?.url ?? "";
    return new URL(raw, "http://local").pathname;
  } catch {
    return "request";
  }
}

export function countFetches(original: typeof fetch, bar = loadingBar): typeof fetch {
  return function counted(...args: Parameters<typeof fetch>) {
    if (inBackground() || isMarkedBackground(args[1])) return original(...args);
    const label = requestLabel(args[0]);
    bar.begin(label);
    let done = false;
    const finish = () => {
      if (!done) {
        done = true;
        bar.end(label);
      }
    };
    return original(...args).then(
      (response) => {
        finish();
        return response;
      },
      (error) => {
        finish();
        throw error;
      },
    );
  } as typeof fetch;
}
