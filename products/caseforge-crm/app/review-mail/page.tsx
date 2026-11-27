"use client";

import { BackToHome } from "@/components/BackToHome";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { MailControlTab } from "@/components/MailControlTab";
import { MailReviewTab } from "@/components/MailReviewTab";
import { tabFromParam, type ReviewTab } from "@/lib/mailReview";

const TABS: { id: ReviewTab; label: string }[] = [
  { id: "review", label: "Review" },
  { id: "control", label: "Control" },
];

export default function ReviewMailPage() {
  const [tab, setTab] = useState<ReviewTab>("review");
  const refs = useRef<Record<ReviewTab, HTMLButtonElement | null>>({ review: null, control: null });

  useEffect(() => {

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTab(tabFromParam(new URLSearchParams(window.location.search).get("tab")));
  }, []);

  function choose(next: ReviewTab) {
    setTab(next);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", next);
    window.history.replaceState(null, "", url);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight" && event.key !== "Home" && event.key !== "End") return;
    event.preventDefault();
    const index = TABS.findIndex((t) => t.id === tab);
    const next =
      event.key === "Home" ? 0 : event.key === "End" ? TABS.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + TABS.length) % TABS.length;
    choose(TABS[next].id);
    refs.current[TABS[next].id]?.focus();
  }

  return (
    <main className="review-mail">
      <p className="review-mail-back">
        <BackToHome />
      </p>
      <h1>Improve Mail Classifier</h1>
      <div className="review-mail-tabs" role="tablist" aria-label="Improve mail classifier" onKeyDown={onKeyDown}>
        {TABS.map((t) => (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el;
            }}
            type="button"
            role="tab"
            className="cf-btn cf-btn--flush"
            id={`review-tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`review-panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            onClick={() => choose(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`review-panel-${tab}`} aria-labelledby={`review-tab-${tab}`}>
        {tab === "review" ? <MailReviewTab /> : <MailControlTab />}
      </div>
    </main>
  );
}
