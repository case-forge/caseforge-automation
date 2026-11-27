import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { LoadingBar } from "@/components/LoadingBar";
import { GlobalHearings } from "@/components/GlobalHearings";
import { WidgetLayer } from "@/components/WidgetLayer";
import { headers } from "next/headers";
import { FaviconColour } from "@/components/FaviconColour";
import { ScheduledRefresh } from "@/components/ScheduledRefresh";
import { isStubMode } from "@/lib/hubProxy";
import { tabTitle } from "@/lib/tabTitle";
import "./globals.css";
import "./buttons.css";
import "./glyphs.css";
import "./calendar.css";
import "./attention.css";
import "./robot.css";
import "./todo.css";
import "./caseflow.css";
import "./board.css";
import "./scans.css";
import "./assignmentboard.css";
import "./folderlocks.css";
import "./newclient.css";
import "./reviewmail.css";
import "./systemhealth.css";
import "./storage.css";
import "./outagemap.css";
import "./audittrail.css";
import "./modelsettings.css";
import "./emailclassifier.css";
import "./today.css";
import "./teasers.css";
import "./whatsnew.css";
import "./windows.css";
import "./nearest.css";
import "./vscan.css";
import "./switcher.css";
import "./statusboard.css";
import "./widgets.css";
import "./billingchart.css";
import "./firmpage.css";
import "./boxes.css";

const DESCRIPTION = "Client and matter CRM over the caseforge-chat hub API. Tailnet-only.";

export async function generateMetadata(): Promise<Metadata> {
  return {
    title: tabTitle(isStubMode(), (await headers()).get("host")),
    description: DESCRIPTION,
    icons: { icon: [{ url: "/brand-favicon.ico" }, { url: "/brand-icon.svg", type: "image/svg+xml" }] },
  };
}

const THEME_BOOTSTRAP = `
try {
  var t = localStorage.getItem('caseforge-client-viewer:theme');
  if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
} catch (e) {}
`;

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en-GB" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
        { }
        {process.env.NEXT_PUBLIC_UMAMI_URL && process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID ? (
          <script
            defer
            src={`${process.env.NEXT_PUBLIC_UMAMI_URL.replace(/\/+$/, "")}/script.js`}
            data-website-id={process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID}
            data-exclude-search="true"
            data-do-not-track="true"
          />
        ) : null}
      </head>
      <body>
        <LoadingBar />
        <FaviconColour />
        <ScheduledRefresh />
        {children}
        <GlobalHearings />
        <WidgetLayer />
      </body>
    </html>
  );
}
