"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import type { Hearing } from "@/lib/hearings";
import { consumeRequest, useOpenRequests } from "@/lib/cornerPrompts";
import { hearingHref, hearingsHost, useHearingDrawers, useHearingsVersion } from "@/lib/hearingsHost";
import type { DrawerEntry } from "@/lib/hearingsHost";
import { useRailOpen } from "@/lib/useHearings";
import { HearingDrawer, NewHearingDrawer, hearingWindowTitle } from "./HearingDrawer";
import { UpcomingRail } from "./UpcomingRail";
import { AddHearingBox } from "./AddHearingBox";
import { HearingSlideOut, HearingToaster } from "./HearingSlideOut";

const drawerTitle = (d: DrawerEntry): string => (d.kind === "edit" ? hearingWindowTitle(d.hearing) : d.spec.clientName ? `Add a Hearing: ${d.spec.clientName}` : "Add a Hearing");

function GlobalHearingsInner() {
  const router = useRouter();
  const [railOpen, setRailOpen] = useRailOpen();
  const version = useHearingsVersion();
  const asked = useOpenRequests("hearings");
  const drawers = useHearingDrawers();

  useEffect(() => {
    if (consumeRequest("hearings")) setRailOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asked]);

  const openClient = (h: Hearing) => {
    if (!hearingsHost.openInWorkspace(h)) router.push(hearingHref(h));
  };

  return (
    <>
      <UpcomingRail
        open={railOpen}
        onOpenChange={setRailOpen}
        refreshKey={version}
        onReviewCount={hearingsHost.setReviewCount}
        onUpcomingCount={hearingsHost.setUpcomingCount}
        onSelect={(h) => hearingsHost.openEdit(h)}
      />
      <AddHearingBox />
      <HearingToaster />
      {drawers.length > 0 && (
      <HearingSlideOut>
      {drawers.slice(0, 1).map((drawer) =>
        drawer.kind === "edit" ? (
          <HearingDrawer
            key={drawer.key}
            hearing={drawer.hearing}
            startEditing={drawer.startEditing}
            onClose={() => hearingsHost.closeDrawer(drawer.key)}
            onChanged={(h) => {
              if (h.review_state === "dismissed") hearingsHost.closeDrawer(drawer.key);
              else hearingsHost.updateEdit(h);
              hearingsHost.bump();
            }}
            onOpenClient={openClient}
          />
        ) : null,
      )}
      </HearingSlideOut>
      )}
    </>
  );
}

export function GlobalHearings() {
  return <GlobalHearingsInner />;
}
