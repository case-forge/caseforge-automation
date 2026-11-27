"use client";

import { BackToHome } from "@/components/BackToHome";
import { CourtPrepBody } from "@/components/CourtPrepBody";

export default function CourtPrepPage() {
  return (
    <main className="status-board">
      <BackToHome />
      <h1>Court Prep</h1>
      <p className="status-board-note">Every clean hearing in the next 14 days, one row each, and how far its preparation has got. A date is the day the email actually left, found in Sent Items; Papers Served is when referrer's statement of service came back; Counsel Booked is when counsel was recorded on the hearing. Hearings waiting for review are not shown.</p>
      <CourtPrepBody withFullLink={false} />
    </main>
  );
}
