import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";
import { ALL_SOURCE, PAGE_SOURCE, baseHeaders, contentSecurityPolicy } from "./lib/securityHeaders";

export default function config(phase: string): NextConfig {
  const devWithoutHub =
    phase === PHASE_DEVELOPMENT_SERVER && !process.env.CASEFORGE_HUB_API_URL && process.env.CASEFORGE_HUB_API_STUB === undefined;
  const distDir = process.env.CASEFORGE_NEXT_DIST_DIR || ".next";
  const stub = devWithoutHub || process.env.CASEFORGE_HUB_API_STUB === "1";
  return {

    ...(distDir !== ".next" ? { distDir, typescript: { tsconfigPath: "tsconfig.demo.json" } } : {}),
    poweredByHeader: false,
    async headers() {
      const csp = contentSecurityPolicy({
        dev: phase === PHASE_DEVELOPMENT_SERVER,
        analyticsUrl: process.env.NEXT_PUBLIC_UMAMI_URL,
      });
      return [
        { source: ALL_SOURCE, headers: baseHeaders },
        { source: PAGE_SOURCE, headers: [{ key: "Content-Security-Policy", value: csp }] },
      ];
    },
    env: {
      ...(devWithoutHub ? { CASEFORGE_HUB_API_STUB: "1" } : {}),
      ...(stub ? { NEXT_PUBLIC_CASEFORGE_DEMO: "1" } : {}),

      CASEFORGE_BUILD_DIST_DIR: distDir,
    },
    ...(stub ? { skipTrailingSlashRedirect: true } : {}),
  };
}
