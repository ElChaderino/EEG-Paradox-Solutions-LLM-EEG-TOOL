/*
 * @license GPL-3.0-or-later
 * Copyright (C) 2026 EEG Paradox Solutions LLM contributors
 *
 * This file is part of Paradox Solutions LLM. See LICENSE in the repository root.
 */

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

export const isTauri = (): boolean =>
  typeof window !== "undefined" && !!window.__TAURI_INTERNALS__;

type InvokeArgs = Record<string, unknown>;

export async function tauriInvoke<T>(cmd: string, args?: InvokeArgs): Promise<T> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<T>(cmd, args);
}

export async function tauriListen(
  event: string,
  handler: (payload: unknown) => void
): Promise<() => void> {
  const { listen } = await import("@tauri-apps/api/event");
  const unlisten = await listen(event, (e) => handler(e.payload));
  return unlisten;
}
