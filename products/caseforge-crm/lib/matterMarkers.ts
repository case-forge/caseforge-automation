import { parseUtc } from "./matterTasks";
import type { MatterMarker } from "./types";

export type MarkerState = "received" | "missing" | "pending" | "unsearchable" | "unknown" | "loading";

const LONDON_DATE = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  day: "numeric",
  month: "short",
  year: "numeric",
});

export function markerView(
  marker: MatterMarker | null | undefined,
  failed: boolean,
): { state: MarkerState; text: string; url: string } {
  if (failed) return { state: "unknown", text: "Couldn't check", url: "" };
  if (!marker) return { state: "loading", text: "Checking…", url: "" };
  if (marker.status === "received") {
    const ms = parseUtc(marker.date);
    const url = typeof marker.url === "string" && marker.url.startsWith("https://") ? marker.url : "";
    return { state: "received", text: Number.isNaN(ms) ? "Received" : `Received ${LONDON_DATE.format(new Date(ms))}`, url };
  }
  if (marker.status === "unsearchable") {
    return { state: "unsearchable", text: marker.reason === "folder_not_found" ? "Folder not found" : "No folder recorded", url: "" };
  }
  if (marker.status === "pending") return { state: "pending", text: "Not checked yet", url: "" };
  if (marker.status === "missing") return { state: "missing", text: "Not yet", url: "" };
  return { state: "unknown", text: "Couldn't check", url: "" };
}
