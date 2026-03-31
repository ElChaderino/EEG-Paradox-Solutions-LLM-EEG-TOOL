"use client";

/*
 * @license GPL-3.0-or-later
 * Copyright (C) 2026 EEG Paradox Solutions LLM contributors
 *
 * This file is part of Paradox Solutions LLM. See LICENSE in the repository root.
 */

import { useCallback, useEffect, useState } from "react";
import { isTauri, tauriInvoke, tauriListen } from "@/lib/tauri";

type Stage = "checking" | "download-ollama" | "start-ollama" | "optimize" | "pull-models" | "start-api" | "ready" | "error";

const REQUIRED_MODELS = ["qwen3:8b", "nomic-embed-text"];

interface ProgressEvent {
  stage: string;
  detail: string;
  done: boolean;
}

export default function SetupPage() {
  const [stage, setStage] = useState<Stage>("checking");
  const [detail, setDetail] = useState("Checking system...");
  const [error, setError] = useState("");

  const runSetup = useCallback(async () => {
    if (!isTauri()) {
      setStage("error");
      setError(
        "First-run setup (download/start Ollama) runs in the desktop app.\n\n" +
          "In the browser: run python run_server.py — the API will try to start Ollama if it is installed. " +
          "Ensure Ollama is on PATH or in the default Windows install folder."
      );
      return;
    }

    try {
      setStage("checking");
      setDetail("Checking for Ollama...");

      const hasOllama = await tauriInvoke<boolean>("check_ollama");
      if (!hasOllama) {
        setStage("download-ollama");
        setDetail("Downloading Ollama (this may take a minute)...");
        await tauriInvoke("download_ollama");
      }

      setStage("start-ollama");
      setDetail("Starting Ollama with GPU optimizations...");
      await tauriInvoke("ensure_ollama_serving");

      setStage("optimize");
      setDetail("Flash Attention + KV Cache quantization enabled");
      await new Promise((r) => setTimeout(r, 1200));

      setStage("pull-models");
      const existing = await tauriInvoke<string[]>("get_ollama_models");
      const missing = REQUIRED_MODELS.filter(
        (m) => !existing.some((e) => e.startsWith(m.split(":")[0]))
      );

      for (const model of missing) {
        setDetail(`Pulling ${model}...`);
        await tauriInvoke("pull_model", { model });
      }

      setStage("start-api");
      setDetail("Starting Paradox API...");
      await tauriInvoke("start_api_sidecar");

      setStage("ready");
      setDetail("Ready!");
      setTimeout(() => {
        window.location.href = "/";
      }, 1000);
    } catch (e) {
      setStage("error");
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    runSetup();
  }, [runSetup]);

  useEffect(() => {
    if (!isTauri()) return;
    let cleanup: (() => void) | undefined;
    tauriListen("setup-progress", (payload) => {
      const p = payload as ProgressEvent;
      if (p.detail) setDetail(p.detail);
    }).then((fn) => {
      cleanup = fn;
    });
    return () => cleanup?.();
  }, []);

  const stages = ["checking", "download-ollama", "start-ollama", "optimize", "pull-models", "start-api", "ready"];
  const stageIndex = stages.indexOf(stage);
  const progress = stage === "error" ? 0 : Math.max(0, ((stageIndex + 1) / stages.length) * 100);

  return (
    <div className="min-h-screen bg-black flex items-center justify-center">
      <div className="w-full max-w-md p-8">
        <h1 className="text-sm font-semibold tracking-[0.25em] text-cyan-400 text-center mb-1">
          PARADOX // SOLUTIONS LLM
        </h1>
        <p className="text-[0.625rem] uppercase tracking-widest text-cyan-600 text-center mb-8">
          First-run setup
        </p>

        <div className="mb-6">
          <div className="h-1 w-full bg-cyan-950 rounded-full overflow-hidden">
            <div
              className="h-full bg-cyan-500 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        <div className="text-center">
          {stage === "error" ? (
            <>
              <p className="text-red-400 text-sm mb-4 whitespace-pre-wrap break-words max-h-40 overflow-y-auto">{error}</p>
              <button
                onClick={() => runSetup()}
                className="rounded bg-cyan-900/50 px-4 py-2 text-xs font-semibold uppercase tracking-wider text-cyan-200 hover:bg-cyan-800/60"
              >
                Retry
              </button>
            </>
          ) : (
            <p className={`text-cyan-300 text-sm font-mono ${stage === "pull-models" ? "" : "animate-pulse"}`}>{detail}</p>
          )}
        </div>
      </div>
    </div>
  );
}
