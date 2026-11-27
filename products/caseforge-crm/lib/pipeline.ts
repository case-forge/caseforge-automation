"use client";

import { startVisiblePoll } from "./visiblePoll";
import { useCallback, useEffect, useRef, useState } from "react";
import { effectiveMode } from "./matterMode";
import { stepRef } from "./pipelineTypes";
import type { ActivityViewer, MatterModeAnswer, MatterModeSetting, Pipeline, PipelineEvent, PipelineMode, PipelineRunResult } from "./pipelineTypes";
import type { StepFormRequest } from "./pipelineForms";
import { backgroundFetch } from "./loadingBar";
import { currentEditorName } from "./editorName";
import { gameClientEvents, gameClientPipeline, isGameClient, runGameStep, setGameFirmMode, setGameMatterMode } from "./demoBridge";

export { sendGameDraft } from "./demoBridge";

async function readError(res: Response, fallback: string): Promise<never> {
  const body = await res.json().catch(() => ({}));
  throw new Error(typeof body?.error === "string" && body.error ? body.error : fallback);
}

export async function fetchPipeline(matterId: string, background = false, fresh = false): Promise<Pipeline> {

  if (isGameClient(matterId)) return gameClientPipeline(matterId);
  const url = `/api/pipeline?matter_id=${encodeURIComponent(matterId)}${background ? "&poll=1" : ""}${fresh ? "&fresh=1" : ""}`;
  const res = background ? await backgroundFetch(url, { cache: "no-store" }) : await fetch(url, { cache: "no-store" });
  if (!res.ok) return readError(res, "Could not load the pipeline.");
  return res.json();
}

export async function fetchActivityLogWithViewers(matterId: string, background = false): Promise<{ events: PipelineEvent[]; viewers: ActivityViewer[] }> {
  if (isGameClient(matterId)) return { events: gameClientEvents(matterId), viewers: [] };
  const url = `/api/pipeline/events?matter_id=${encodeURIComponent(matterId)}`;
  const res = background ? await backgroundFetch(url, { cache: "no-store" }) : await fetch(url, { cache: "no-store" });
  if (!res.ok) return readError(res, "Could not load the activity log.");
  const body = await res.json();
  return { events: (body.events ?? []) as PipelineEvent[], viewers: (body.seen_by ?? []) as ActivityViewer[] };
}

export async function fetchActivityLog(matterId: string, background = false): Promise<PipelineEvent[]> {
  return (await fetchActivityLogWithViewers(matterId, background)).events;
}

export function useActivityLog(matterId: string): { events: PipelineEvent[] | null; viewers: ActivityViewer[]; error: string } {
  const [events, setEvents] = useState<PipelineEvent[] | null>(null);
  const [viewers, setViewers] = useState<ActivityViewer[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    function read(background: boolean) {
      fetchActivityLogWithViewers(matterId, background)
        .then(({ events: rows, viewers: seen }) => {
          if (cancelled) return;
          setEvents(rows);
          setViewers(seen);
          setError("");
        })
        .catch((err: unknown) => {
          if (!cancelled) setError(err instanceof Error ? err.message : "Could not load the activity log.");
        });
    }
    read(false);
    const stop = startVisiblePoll(() => read(true), 20_000, { immediate: false });
    const onGame = () => read(true);
    if (isGameClient(matterId)) window.addEventListener("caseforge-demo-changed", onGame);
    return () => {
      cancelled = true;
      stop();
      window.removeEventListener("caseforge-demo-changed", onGame);
    };
  }, [matterId]);

  return { events, viewers, error };
}

export async function runPipelineStep(matterId: string, step: string, variant?: string): Promise<PipelineRunResult> {
  if (isGameClient(matterId)) return runGameStep(matterId);
  const res = await fetch("/api/pipeline/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId, step, ...(variant ? { variant } : {}) }),
  });
  if (!res.ok) return readError(res, "The step did not run.");
  return res.json();
}

async function postAmend(body: Record<string, unknown>, fallback: string): Promise<unknown> {
  if (isGameClient(String(body.matter_id ?? ""))) throw new Error(`The demo's Case flow drafts changes to the statement at ${stepRef("email")}; this is not offered here.`);
  const res = await fetch("/api/pipeline/amend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) return readError(res, fallback);
  return res.json();
}

export async function prepareAmendRound(matterId: string, emailText: string): Promise<Pipeline> {
  return (await postAmend({ action: "prepare", matter_id: matterId, email_text: emailText }, "The amended statement was not prepared.")) as Pipeline;
}

export async function approveAmendRound(matterId: string, round: number, answers: string, keepOriginal: string[], clientQuestions?: string[], edits: Record<string, string> = {}): Promise<PipelineRunResult> {
  return (await postAmend(
    { action: "approve", matter_id: matterId, round, answers, keep_original: keepOriginal, edits, ...(clientQuestions ? { client_questions: clientQuestions } : {}) },
    "The round was not approved.",
  )) as PipelineRunResult;
}

export async function discardAmendRound(matterId: string, round: number): Promise<Pipeline> {
  return (await postAmend({ action: "discard", matter_id: matterId, round }, "The round was not discarded.")) as Pipeline;
}

export async function markPipelineStepDone(matterId: string, step: string, note?: string): Promise<Pipeline> {
  const res = await fetch("/api/pipeline/mark-done", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId, step, ...(note ? { note } : {}) }),
  });
  if (!res.ok) return readError(res, "Could not mark the step done.");
  return res.json();
}

export async function confirmPipelineCourt(matterId: string, court: string, email?: string): Promise<Pipeline> {
  const res = await fetch("/api/pipeline/confirm-court", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId, court, ...(email ? { email } : {}) }),
  });
  if (!res.ok) return readError(res, "Could not confirm the court.");
  return res.json();
}

export async function addServiceRecipient(matterId: string, kind: string, name: string, email: string): Promise<Pipeline> {
  const res = await fetch("/api/pipeline/service-recipient", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId, kind, name, email }),
  });
  if (!res.ok) return readError(res, "Could not add the recipient.");
  return res.json();
}

export async function requirePersonalService(matterId: string): Promise<Pipeline> {
  const res = await fetch("/api/pipeline/personal-service", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId }),
  });
  if (!res.ok) return readError(res, "Could not mark personal service as needed.");
  return res.json();
}

export async function setPipelineMode(mode: PipelineMode, matterId?: string): Promise<PipelineMode> {
  if (matterId && isGameClient(matterId)) {
    setGameFirmMode(mode, matterId);
    return mode;
  }
  const res = await fetch("/api/pipeline/mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, ...(matterId ? { matter_id: matterId } : {}) }),
  });
  if (!res.ok) return readError(res, "Could not change the mode.");
  return (await res.json()).mode;
}

export async function setMatterMode(matterId: string, setting: MatterModeSetting): Promise<MatterModeAnswer> {
  if (isGameClient(matterId)) return setGameMatterMode(matterId, setting, currentEditorName());
  const res = await fetch("/api/pipeline/matter-mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId, setting }),
  });
  if (!res.ok) return readError(res, "Could not change this client's setting.");
  return res.json();
}

export async function resetPipelineStep(matterId: string, step: string): Promise<Pipeline> {
  const res = await fetch("/api/pipeline/reset-step", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId, step }),
  });
  if (!res.ok) return readError(res, "Could not reset the step.");
  return res.json();
}

export function sendStepForm(matterId: string, step: string, request: StepFormRequest): Promise<Pipeline> {
  if (isGameClient(matterId)) return Promise.reject(new Error("The demo's Case flow runs the steps itself; this is not offered here."));
  if (request.kind === "mark-done") return markPipelineStepDone(matterId, step, request.note);
  if (request.kind === "confirm-court") return confirmPipelineCourt(matterId, request.court, request.email);
  if (request.kind === "add-recipient") return addServiceRecipient(matterId, request.recipientKind, request.name, request.email);
  if (request.kind === "require-service") return requirePersonalService(matterId);
  return resetPipelineStep(matterId, step);
}

export function usePipeline(matterId: string): {
  data: Pipeline | null;
  error: string;
  refresh: () => void;
  setData: (p: Pipeline) => void;
} {
  const [data, setData] = useState<Pipeline | null>(null);
  const [error, setError] = useState("");
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  const silentRef = useRef(false);
  const idRef = useRef(matterId);
  idRef.current = matterId;

  useEffect(() => {
    let cancelled = false;
    const silent = silentRef.current;
    silentRef.current = false;
    fetchPipeline(matterId, silent)
      .then((p) => {
        if (!cancelled) {
          setData(p);
          setError("");
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load the pipeline.");
      });
    return () => {
      cancelled = true;
    };
  }, [matterId, nonce]);

  useEffect(() => {
    setData(null);
  }, [matterId]);

  useEffect(() => {

    if (isGameClient(matterId)) window.addEventListener("caseforge-demo-changed", refresh);
    return () => {
      window.removeEventListener("caseforge-demo-changed", refresh);
    };
  }, [refresh, matterId]);

  const fast = data ? effectiveMode(data) === "auto" : false;
  useEffect(() => {
    return startVisiblePoll(
      () => {
        silentRef.current = true;
        refresh();
      },
      isGameClient(matterId) ? 3_000 : fast ? 5_000 : 20_000,
      { immediate: false },
    );
  }, [refresh, fast, matterId]);

  return { data, error, refresh, setData };
}
