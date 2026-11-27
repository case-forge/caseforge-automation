"use client";

import { IconExternalLink } from "@/components/icons";
import { safeOutlookLink, splitBody, type QcItem } from "@/lib/mailReview";

export function MailEmailCard({ item }: { item: Pick<QcItem, "from" | "to" | "cc" | "date" | "subject" | "attachments" | "text" | "weblink"> }) {
  const body = splitBody(item.text);
  const link = safeOutlookLink(item.weblink);
  return (
    <article className="review-mail-card">
      <dl className="review-mail-meta">
        <dt>From</dt><dd>{item.from}</dd>
        <dt>To</dt><dd>{item.to}</dd>
        {item.cc && (<><dt>Cc</dt><dd>{item.cc}</dd></>)}
        <dt>Date</dt><dd>{item.date}</dd>
        <dt>Subject</dt><dd>{item.subject}</dd>
        <dt>Attachments</dt><dd>{item.attachments.join(", ") || "none"}</dd>
      </dl>
      {link ? (
        <a href={link} target="_blank" rel="noopener noreferrer">Open in Outlook <IconExternalLink aria-hidden="true" /></a>
      ) : (
        <p className="review-mail-muted">(no Outlook link: message no longer in the mailbox)</p>
      )}
      <pre className="review-mail-body">{body.head}</pre>
      {body.rest && (
        <details>
          <summary>Show the rest</summary>
          <pre className="review-mail-body">{body.rest}</pre>
        </details>
      )}
    </article>
  );
}
