import { PORTAL_FLAG } from "./types";

export function portalAlertShows(flags: Record<string, boolean> | undefined, concluded: boolean): boolean {
  return !!flags?.[PORTAL_FLAG] && !concluded;
}
