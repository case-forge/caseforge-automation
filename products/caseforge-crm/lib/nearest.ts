
export type NearestCourt = {
  name: string;
  distance_miles: number | null;
  address: string;
  family_emails: string[];
  url: string;
  service: string;
};

export type NearestChambers = {
  name: string;
  email: string;
  phone: string;
  branch: string;
  distance_miles: number | null;
  website: string;
};

export type NearestAnswer =
  | { ok: false; reason: string; message: string }
  | {
      ok: true;
      area: string;
      court: NearestCourt | null;
      court_error: string;
      chambers: NearestChambers[];
      chambers_measured_from: string;
      chambers_error: string;
    };

export function miles(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)} miles` : "";
}

export function httpsOnly(value: unknown): string | null {
  return typeof value === "string" && /^https:\/\//i.test(value) ? value : null;
}
