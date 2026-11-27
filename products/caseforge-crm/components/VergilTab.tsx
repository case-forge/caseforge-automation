"use client";

import Markdown from "react-markdown";
import { useEffect, useRef, useState } from "react";
import type { ClientMatch } from "@/lib/types";
import { verbFor } from "@/lib/toolVerbs";
import { clientContextSummary } from "@/lib/vergilContext";
import type { VergilConversation, VergilMessage, VergilSources } from "@/lib/vergilHistory";
import {
  conversationAsText,
  latestVergilConversation,
  loadVergilHistory,
  saveVergilConversation,
  setVergilConversationTitle,
  sourcesSummary,
} from "@/lib/vergilHistory";
import { VergilHistoryTab } from "./VergilHistoryTab";
import {
  IconAlert,
  IconArrowUp,
  IconCheck,
  IconChevronLeft,
  IconClock,
  IconCopy,
  IconPlus,
  IconRegenerate,
  IconStop,
  IconThumbDown,
  IconThumbUp,
} from "./icons";

function parseSseFrames(buffer: string): { events: { event: string; data: unknown }[]; rest: string } {
  const events: { event: string; data: unknown }[] = [];
  const frames = buffer.split("\n\n");
  const rest = frames.pop() ?? "";
  for (const frame of frames) {
    const eventLine = frame.split("\n").find((line) => line.startsWith("event: "));
    const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
    if (!eventLine || !dataLine) continue;
    const event = eventLine.slice("event: ".length).trim();
    try {
      events.push({ event, data: JSON.parse(dataLine.slice("data: ".length)) });
    } catch {

    }
  }
  return { events, rest };
}

export function VergilTab({
  match,
  resume,
  startFresh = false,
  onNewChat,
  onResumeConversation,
}: {
  match: ClientMatch;

  resume?: VergilConversation;

  startFresh?: boolean;
  onNewChat?: () => void;

  onResumeConversation?: (conversation: VergilConversation) => void;
}) {
  const matterId = match.matter_id != null ? String(match.matter_id) : "";
  const [showHistory, setShowHistory] = useState(false);

  const [hasHistory, setHasHistory] = useState(() => (matterId ? loadVergilHistory(matterId).length > 0 : false));
  const [initial] = useState<VergilConversation | undefined>(
    () => resume ?? (startFresh ? undefined : latestVergilConversation(matterId)),
  );
  const [messages, setMessages] = useState<VergilMessage[]>(
    initial?.messages ?? [{ role: "context", text: clientContextSummary(match) }],
  );
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [toolLabel, setToolLabel] = useState("");
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [copiedAll, setCopiedAll] = useState(false);
  const sessionIdRef = useRef<string>(initial?.sessionId ?? "");
  const startedAtRef = useRef<string>(initial?.startedAt ?? new Date().toISOString());
  const firstQuestionRef = useRef<string>(initial?.firstQuestion ?? "");
  const [title, setTitle] = useState<string>(initial?.title ?? "");
  const titleRequestedRef = useRef<boolean>(Boolean(initial?.title));
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  async function ask(question: string, options: { replay?: boolean } = {}) {
    if (!question.trim() || streaming || !matterId) return;
    if (!firstQuestionRef.current) firstQuestionRef.current = question;
    if (!options.replay) setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setStreaming(true);
    setToolLabel("");

    const controller = new AbortController();
    abortRef.current = controller;
    let vergilText = "";
    let vergilSources: VergilSources | undefined;

    try {
      const res = await fetch("/api/vergil/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, matter_id: matterId, session_id: sessionIdRef.current }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => ({}) as { error?: string });
        throw new Error(body.error || "Vergil is unavailable right now.");
      }

      setMessages((prev) => [...prev, { role: "vergil", text: "" }]);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { events, rest } = parseSseFrames(buffer);
        buffer = rest;
        for (const { event, data } of events) {
          if (event === "session") {
            sessionIdRef.current = (data as { session_id?: string }).session_id ?? sessionIdRef.current;
          } else if (event === "sources") {
            const d = data as Partial<VergilSources>;
            vergilSources = {
              sources_checked: Array.isArray(d.sources_checked) ? d.sources_checked.map(String) : [],
              gaps: Array.isArray(d.gaps) ? d.gaps.map(String) : [],
            };
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = { ...next[next.length - 1], sources: vergilSources };
              return next;
            });
          } else if (event === "tool_call") {
            setToolLabel(verbFor((data as { tool?: string }).tool ?? ""));
          } else if (event === "tool_result" || event === "tool_error") {
            setToolLabel("");
          } else if (event === "delta") {
            setToolLabel("");
            vergilText += (data as { text?: string }).text ?? "";
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = { role: "vergil", text: vergilText, sources: vergilSources };
              return next;
            });
          } else if (event === "error") {
            throw new Error((data as { message?: string }).message || "Vergil hit an error.");
          }
        }
      }
      if (!titleRequestedRef.current && question === firstQuestionRef.current && vergilText.trim()) {
        titleRequestedRef.current = true;
        void requestTitle(question, vergilText, sessionIdRef.current);
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setMessages((prev) => [...prev, { role: "error", text: err instanceof Error ? err.message : "Something went wrong." }]);
    } finally {
      setStreaming(false);
      setToolLabel("");
    }
  }

  async function requestTitle(question: string, answer: string, sessionId: string) {
    try {
      const res = await fetch("/api/vergil/title", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, answer }),
      });
      if (!res.ok) return;
      const data = (await res.json()) as { title?: string | null };
      if (!data.title) return;
      setVergilConversationTitle(matterId, sessionId, data.title);
      setTitle(data.title);
    } catch {

    }
  }

  function regenerate() {
    let lastQuestion = "";
    let cut = messages.length;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        lastQuestion = messages[i].text;
        cut = i + 1;
        break;
      }
    }
    if (!lastQuestion) return;
    setMessages(messages.slice(0, cut));
    void ask(lastQuestion, { replay: true });
  }

  async function copyConversation() {
    try {
      await navigator.clipboard.writeText(conversationAsText(messages));
      setCopiedAll(true);
      setTimeout(() => setCopiedAll(false), 1500);
    } catch {

    }
  }

  async function copyAnswer(index: number, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex((current) => (current === index ? null : current)), 1500);
    } catch {

    }
  }

  function rate(index: number, verdict: "up" | "down") {
    setMessages((prev) => prev.map((m, i) => (i === index ? { ...m, feedback: verdict } : m)));
    const turn = messages.slice(0, index + 1).filter((m) => m.role === "vergil").length;
    void fetch("/api/vergil/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: `goose:${sessionIdRef.current}:${turn}`, verdict, comment: `matter:${matterId}` }),
    }).catch(() => undefined);
  }

  function stop() {
    abortRef.current?.abort();
  }

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [input]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, toolLabel]);

  useEffect(() => {
    if (streaming || !sessionIdRef.current || !matterId) return;
    saveVergilConversation({
      sessionId: sessionIdRef.current,
      matterId,
      startedAt: startedAtRef.current,
      updatedAt: new Date().toISOString(),
      firstQuestion: firstQuestionRef.current,
      ...(title ? { title } : {}),
      messages,
    });
    setHasHistory(loadVergilHistory(matterId).length > 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streaming, messages, matterId, title]);

  const lastVergilIndex = messages.reduce((found, m, i) => (m.role === "vergil" ? i : found), -1);

  const typingDots = (
    <div className="typing-indicator" role="status">
      <span className="typing-dot" aria-hidden="true" />
      <span className="typing-dot" aria-hidden="true" />
      <span className="typing-dot" aria-hidden="true" />
      <span className="sr-only">Vergil is answering</span>
    </div>
  );

  return (
    <div className="vergil-tab">
      {showHistory ? (
        <div className="vergil-tab-toolbar">
          <button
            type="button"
            className="cf-btn cf-btn--neutral"
            onClick={() => {
              setHasHistory(loadVergilHistory(matterId).length > 0);
              setShowHistory(false);
            }}
          >
            <IconChevronLeft />
            <span>Back to chat</span>
          </button>
        </div>
      ) : (
        (onNewChat || matterId) && (
          <div className="vergil-tab-toolbar">
            {onNewChat && (
              <button
                type="button"
                className="cf-btn cf-btn--neutral"
                onClick={onNewChat}
                disabled={streaming || !messages.some((m) => m.role === "user")}
              >
                <IconPlus />
                <span>New chat</span>
              </button>
            )}
            <button
              type="button"
              className="cf-btn cf-btn--neutral"
              onClick={() => void copyConversation()}
              disabled={!messages.some((m) => m.role === "user")}
            >
              {copiedAll ? <IconCheck /> : <IconCopy />}
              <span>{copiedAll ? "Copied" : "Copy chat"}</span>
            </button>
            <button
              type="button"
              className="cf-btn cf-btn--neutral"
              onClick={() => setShowHistory(true)}
              disabled={!hasHistory}
              title={hasHistory ? undefined : "No previous conversations for this client yet"}
            >
              <IconClock />
              <span>Previous chats</span>
            </button>
          </div>
        )
      )}
      {showHistory ? (
        <VergilHistoryTab
          matterId={matterId}
          onResume={(conversation) => {
            onResumeConversation?.(conversation);
            setShowHistory(false);
          }}
        />
      ) : (
        <>
      <div className="vergil-tab-messages">
        {messages.map((message, i) => {
          const isLast = i === messages.length - 1;
          const pending = streaming && isLast && message.role === "vergil";
          if (message.role === "context") {
            return (
              <details key={i} className="vergil-context-primer">
                <summary>Context given to Vergil</summary>
                <pre>{message.text}</pre>
              </details>
            );
          }
          if (message.role === "user") {
            return (
              <div key={i} className="message message-user">
                <div className="message-bubble">{message.text}</div>
              </div>
            );
          }
          if (message.role === "error") {
            return (
              <div key={i} className="message-error" role="alert">
                <IconAlert />
                <span>{message.text}</span>
              </div>
            );
          }
          return (
            <div key={i} className="message message-assistant">
              {pending && !message.text && !toolLabel ? typingDots : null}
              {message.text ? (
                <div className="message-bubble">
                  <div className="markdown">
                    <Markdown
                      components={{
                        a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
                      }}
                    >
                      {message.text}
                    </Markdown>
                  </div>
                  {pending && !toolLabel && <span className="streaming-cursor" aria-hidden="true" />}
                </div>
              ) : null}
              {!pending && message.text && message.sources && sourcesSummary(message.sources) ? (
                <details className="vergil-sources">
                  <summary>{sourcesSummary(message.sources)}</summary>
                  <ul>
                    {message.sources.sources_checked.map((label) => (
                      <li key={label}>{label}</li>
                    ))}
                  </ul>
                  {message.sources.gaps.length > 0 ? (
                    <>
                      <p className="vergil-sources-gaps-title">Not found</p>
                      <ul>
                        {message.sources.gaps.map((gap) => (
                          <li key={gap}>{gap}</li>
                        ))}
                      </ul>
                    </>
                  ) : null}
                </details>
              ) : null}
              {pending && toolLabel ? (
                <div className="tool-call-indicator" role="status">
                  <span className="tool-call-dot" aria-hidden="true" />
                  <span>{toolLabel}…</span>
                </div>
              ) : null}
              {!pending && message.text ? (
                <div className="action-bar">
                  <button type="button" className="cf-btn cf-btn--flush cf-btn--small" onClick={() => void copyAnswer(i, message.text)}>
                    {copiedIndex === i ? <IconCheck /> : <IconCopy />}
                    <span>{copiedIndex === i ? "Copied" : "Copy"}</span>
                  </button>
                  {i === lastVergilIndex && !streaming && (
                    <button type="button" className="cf-btn cf-btn--flush cf-btn--small" onClick={regenerate}>
                      <IconRegenerate />
                      <span>Regenerate</span>
                    </button>
                  )}
                  <button
                    type="button"
                    className="cf-btn cf-btn--icon"
                    title="Good answer"
                    aria-pressed={message.feedback === "up"}
                    data-submitted={message.feedback === "up"}
                    onClick={() => rate(i, "up")}
                  >
                    <IconThumbUp />
                    <span className="sr-only">Thumbs up</span>
                  </button>
                  <button
                    type="button"
                    className="cf-btn cf-btn--icon"
                    title="Poor answer"
                    aria-pressed={message.feedback === "down"}
                    data-submitted={message.feedback === "down"}
                    onClick={() => rate(i, "down")}
                  >
                    <IconThumbDown />
                    <span className="sr-only">Thumbs down</span>
                  </button>
                </div>
              ) : null}
            </div>
          );
        })}
        {streaming && messages[messages.length - 1]?.role === "user" && (
          <div className="message message-assistant">{typingDots}</div>
        )}
        <div ref={endRef} className="vergil-tab-end" />
      </div>
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(input);
        }}
      >
        <textarea
          ref={inputRef}
          className="composer-input"
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask(input);
            }
          }}
          placeholder="Ask Vergil about this client..."
          aria-label="Message Vergil"
        />
        {streaming ? (
          <button type="button" className="cf-btn cf-btn--icon composer-stop" aria-label="Stop generating" onClick={stop}>
            <IconStop />
          </button>
        ) : (
          <button type="submit" className="cf-btn cf-btn--icon composer-send" aria-label="Send" disabled={!input.trim()}>
            <IconArrowUp />
          </button>
        )}
      </form>
        </>
      )}
    </div>
  );
}
