
export type FaviconColour = "black" | "white";

export const FAVICON_VERSION = 6;

export function faviconColour(theme: "light" | "dark"): FaviconColour {
  return theme === "dark" ? "white" : "black";
}

export function isPreviewHost(hostname: string): boolean {
  const host = hostname.trim().toLowerCase();
  if (!host || host === "localhost") return false;
  if (host.endsWith(".ts.net")) return true;
  const ip = /^(\d{1,3})\.(\d{1,3})\.\d{1,3}\.\d{1,3}$/.exec(host);
  if (ip) return Number(ip[1]) === 100 && Number(ip[2]) >= 64 && Number(ip[2]) <= 127;
  return !host.includes(".") && !host.includes(":");
}

export function faviconHref(colour: FaviconColour): string {
  return `/caseforge-favicon-${colour}.svg?v=${FAVICON_VERSION}`;
}

export const MARKED_COLOURS = { light: "#2563eb", dark: "#facc15" } as const;

export function isMarkedTab(hostname: string, demo: boolean): boolean {
  return demo || isPreviewHost(hostname);
}

export function recolourMark(svg: string, colour: string): string {
  return svg.replace(/fill="#000000"/gi, `fill="${colour}"`).replace(/fill="#000"/gi, `fill="${colour}"`);
}

export function svgDataHref(svg: string): string {
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}
