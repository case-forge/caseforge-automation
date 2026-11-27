
export interface Header {
  key: string;
  value: string;
}

export function contentSecurityPolicy(env: { dev: boolean; analyticsUrl?: string }): string {

  let analytics = "";
  try {
    if (env.analyticsUrl) analytics = new URL(env.analyticsUrl).origin;
  } catch {
    analytics = "";
  }
  return [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline'${env.dev ? " 'unsafe-eval'" : ""}${analytics ? ` ${analytics}` : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src 'self'${analytics ? ` ${analytics}` : ""}`,
    "frame-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'self'",
  ].join("; ");
}

export const baseHeaders: Header[] = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "same-origin" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

export const PAGE_SOURCE = "/((?!api(?:/|$)|training(?:/|$)).*)";
export const ALL_SOURCE = "/:path*";
