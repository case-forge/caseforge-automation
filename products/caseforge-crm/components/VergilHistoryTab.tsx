"use client";

import { useEffect, useState } from "react";
import type { VergilConversation } from "@/lib/vergilHistory";
import {
  VERGIL_RECENCY_BUCKET_ORDER,
  conversationAsText,
  deleteVergilConversation,
  loadVergilHistory,
  vergilRecencyBucket,
} from "@/lib/vergilHistory";
import { IconCheck, IconCopy } from "./icons";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

export function VergilHistoryTab({
  matterId,
  onResume,
}: {
  matterId: string;
  onResume: (conversation: VergilConversation) => void;
}) {
  const [conversations, setConversations] = useState<VergilConversation[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    setConversations(loadVergilHistory(matterId));
  }, [matterId]);

  function remove(sessionId: string) {
    deleteVergilConversation(matterId, sessionId);
    setConversations(loadVergilHistory(matterId));
  }

  async function copy(conversation: VergilConversation) {
    try {
      await navigator.clipboard.writeText(conversationAsText(conversation.messages));
      setCopiedId(conversation.sessionId);
      setTimeout(() => setCopiedId((current) => (current === conversation.sessionId ? null : current)), 1500);
    } catch {

    }
  }

  if (conversations.length === 0) {

    return (
      <div className="detail-field">
        <p className="detail-field-value detail-field-value--empty">No previous conversations yet.</p>
      </div>
    );
  }

  const now = new Date();
  return (
    <div className="vergil-history">
      {VERGIL_RECENCY_BUCKET_ORDER.map((bucket) => {
        const inBucket = conversations.filter((c) => vergilRecencyBucket(c.updatedAt, now) === bucket);
        if (inBucket.length === 0) return null;
        return (
          <section key={bucket} className="vergil-history-group">
            <h3 className="vergil-history-group-heading">{bucket}</h3>
            <div className="vergil-history-grid">
              {inBucket.map((conversation) => (
                <div className="vergil-history-item" key={conversation.sessionId}>
                  <button type="button" className="vergil-history-item-main" onClick={() => onResume(conversation)}>
                    <p className="vergil-history-item-question">{conversation.title || conversation.firstQuestion || "(untitled conversation)"}</p>
                    <p className="vergil-history-item-meta">
                      {formatTime(conversation.updatedAt)} &middot; {conversation.messages.filter((m) => m.role === "user").length} question
                      {conversation.messages.filter((m) => m.role === "user").length === 1 ? "" : "s"}
                    </p>
                  </button>
                  <div className="vergil-history-item-actions">
                    <button type="button" className="cf-btn cf-btn--flush cf-btn--small" onClick={() => void copy(conversation)}>
                      {copiedId === conversation.sessionId ? <IconCheck /> : <IconCopy />}
                      <span>{copiedId === conversation.sessionId ? "Copied" : "Copy"}</span>
                    </button>
                    <button
                      type="button"
                      className="cf-btn cf-btn--flush cf-btn--small cf-btn--danger"
                      onClick={() => remove(conversation.sessionId)}
                      aria-label="Delete this conversation from history"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
