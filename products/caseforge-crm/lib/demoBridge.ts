"use client";

import { GAME_NOT_OPEN, gameEvents, gamePipeline, isGameClientId, lockedGamePipeline } from "./gameFlow";
import type { DemoCard, DemoEvent } from "./gameFlow";
import type { MatterModeAnswer, MatterModeSetting, Pipeline, PipelineEvent, PipelineMode, PipelineRunResult } from "./pipelineTypes";

export interface DemoBridge {
  cards(): DemoCard[];
  cardForMatter(matterId: string): DemoCard | null;
  events(cardId: string): DemoEvent[];
  run(cardId: string): Promise<{ kind: string; label: string } | null>;
  send(cardId: string): Promise<boolean>;
  setAuto(on: boolean): void;
  auto(): boolean;
}

declare global {
  interface Window {
    __trainingDemo?: DemoBridge;
  }
}

export function isGameClient(matterId: string): boolean {
  return process.env.NEXT_PUBLIC_CASEFORGE_DEMO === "1" && isGameClientId(matterId);
}

export function demoBridge(): DemoBridge | null {
  return typeof window !== "undefined" && window.__trainingDemo ? window.__trainingDemo : null;
}

let firmMode: PipelineMode | null = null;
const ownSettings = new Map<string, { setting: MatterModeSetting; by: string; at: string }>();

if (typeof window !== "undefined") {
  window.addEventListener("training-demo-mode", (event) => {
    firmMode = (event as CustomEvent<{ auto: boolean }>).detail?.auto ? "auto" : "manual";
    ownSettings.clear();
  });
}

function firm(bridge: DemoBridge | null): PipelineMode {
  if (firmMode === null) firmMode = bridge ? (bridge.auto() ? "auto" : "manual") : "auto";
  return firmMode;
}

function effectiveFor(matterId: string, bridge: DemoBridge | null): PipelineMode {
  const own = ownSettings.get(matterId)?.setting ?? "inherit";
  return own === "inherit" ? firm(bridge) : own;
}

export function gameClientPipeline(matterId: string): Pipeline {
  const bridge = demoBridge();
  const own = ownSettings.get(matterId);
  const setting = own?.setting ?? "inherit";
  if (!bridge) return lockedGamePipeline(matterId, "", GAME_NOT_OPEN, firm(null), setting);
  const card = bridge.cardForMatter(matterId);
  if (!card) return lockedGamePipeline(matterId, "", GAME_NOT_OPEN, firm(bridge), setting);
  const pipeline = gamePipeline({ card, events: bridge.events(card.id), mode: firm(bridge), setting, setBy: own?.by, setAt: own?.at });
  return { ...pipeline, matter_id: matterId };
}

export function gameClientEvents(matterId: string): PipelineEvent[] {
  const bridge = demoBridge();
  const card = bridge?.cardForMatter(matterId);
  if (!bridge || !card) return [];
  return gameEvents(card, bridge.events(card.id), effectiveFor(matterId, bridge));
}

export async function runGameStep(matterId: string): Promise<PipelineRunResult> {
  const bridge = demoBridge();
  const card = bridge?.cardForMatter(matterId);
  if (!bridge || !card) throw new Error(GAME_NOT_OPEN);
  const result = await bridge.run(card.id);
  return { ok: Boolean(result) && result?.kind !== "stuck", message: result?.label || "Nothing to run.", pipeline: gameClientPipeline(matterId) };
}

export async function sendGameDraft(matterId: string): Promise<void> {
  const bridge = demoBridge();
  const card = bridge?.cardForMatter(matterId);
  if (!bridge || !card) throw new Error(GAME_NOT_OPEN);
  if (!(await bridge.send(card.id))) throw new Error("There is no draft waiting to be sent.");
}

export function setGameFirmMode(mode: PipelineMode, matterId: string): void {
  firmMode = mode;
  demoBridge()?.setAuto(effectiveFor(matterId, demoBridge()) === "auto");
}

export function setGameMatterMode(matterId: string, setting: MatterModeSetting, by: string): MatterModeAnswer {
  const bridge = demoBridge();
  const at = new Date().toISOString();
  if (setting === "inherit") ownSettings.delete(matterId);
  else ownSettings.set(matterId, { setting, by, at });
  const mode = firm(bridge);
  const effective = effectiveFor(matterId, bridge);
  bridge?.setAuto(effective === "auto");
  return { matter_id: matterId, setting, by: setting === "inherit" ? "" : by, at: setting === "inherit" ? "" : at, mode, effective_mode: effective };
}
