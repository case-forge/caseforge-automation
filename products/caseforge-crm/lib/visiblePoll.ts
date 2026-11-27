import { runInBackground } from "./loadingBar";

export function startVisiblePoll(
  tick: () => void,
  intervalMs: number,
  options: { immediate?: boolean } = {},
): () => void {
  const immediate = options.immediate ?? true;
  let timer: number | undefined;
  let lastRun = immediate ? 0 : Date.now();

  function run() {
    lastRun = Date.now();
    runInBackground(tick);
  }
  function start() {
    if (timer !== undefined) return;
    timer = window.setInterval(run, intervalMs);
  }
  function stop() {
    if (timer === undefined) return;
    window.clearInterval(timer);
    timer = undefined;
  }
  function onVisibility() {
    if (document.visibilityState === "hidden") {
      stop();
      return;
    }
    if (Date.now() - lastRun >= intervalMs) run();
    start();
  }

  if (immediate) run();
  if (document.visibilityState !== "hidden") start();
  document.addEventListener("visibilitychange", onVisibility);
  return () => {
    stop();
    document.removeEventListener("visibilitychange", onVisibility);
  };
}
