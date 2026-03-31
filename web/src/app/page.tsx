"use client";

/*
 * @license GPL-3.0-or-later
 * Copyright (C) 2026 EEG Paradox Solutions LLM contributors
 *
 * This file is part of Paradox Solutions LLM. See LICENSE in the repository root.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  getFocus,
  getHealth,
  postEnsureOllama,
  getStats,
  type EegNormsAddonStatus,
  type Optimizations,
  postAgent,
  postMemoryQuery,
  type ScriptWorkspace,
} from "@/lib/api";
import { FONT_SCALE_LABELS, useTheme } from "@/lib/ThemeContext";
import { isTauri } from "@/lib/tauri";
import FilePanel from "@/components/FilePanel";
import EegDataPanel from "@/components/EegDataPanel";
import MneScriptPanel from "@/components/MneScriptPanel";

type Msg = { role: "user" | "paradox"; text: string; meta?: string };
type AppTab = "session" | "eeg" | "scripts";

export default function Home() {
  const { cycleHudColor, hudColor, fontScale, cycleFontScale } = useTheme();
  const [appTab, setAppTab] = useState<AppTab>("session");
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<string>("…");
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [focus, setFocus] = useState<string>("");
  const [memQ, setMemQ] = useState("");
  const [memHits, setMemHits] = useState<string>("");
  const [healthFailCount, setHealthFailCount] = useState(0);
  const [optStatus, setOptStatus] = useState<Optimizations | null>(null);
  const [eegNorms, setEegNorms] = useState<EegNormsAddonStatus | null>(null);
  const [incomingScriptWs, setIncomingScriptWs] = useState<ScriptWorkspace | null>(null);
  const ollamaEnsureTried = useRef(false);

  const clearIncomingScriptWs = useCallback(() => setIncomingScriptWs(null), []);

  useEffect(() => {
    if (isTauri() && healthFailCount >= 2) {
      window.location.href = "/setup";
    }
  }, [healthFailCount]);

  const refreshSide = useCallback(async () => {
    try {
      let h = await getHealth();
      // Browser mode has no Tauri setup wizard; ask the API to spawn `ollama serve` once if needed.
      if (!h.ollama && !ollamaEnsureTried.current) {
        ollamaEnsureTried.current = true;
        try {
          await postEnsureOllama();
          h = await getHealth();
        } catch {
          /* keep first h */
        }
      }
      setHealth(h.ollama ? "ollama ok" : "degraded");
      setHealthFailCount(0);
      if (h.optimizations) setOptStatus(h.optimizations);
      setEegNorms(h.eeg_norms_addon ?? null);
    } catch {
      setHealth("offline");
      setHealthFailCount((c) => c + 1);
    }
    try {
      const s = await getStats();
      setStats(s.stats as Record<string, unknown>);
    } catch {
      setStats(null);
    }
    try {
      const f = await getFocus();
      setFocus(f.current_focus || "");
    } catch {
      setFocus("");
    }
  }, []);

  useEffect(() => {
    void refreshSide();
    let fast = true;
    let id = setInterval(() => {
      if (fast && health !== "offline") {
        clearInterval(id);
        fast = false;
        id = setInterval(() => void refreshSide(), 15000);
      }
      void refreshSide();
    }, 2000);
    return () => clearInterval(id);
  }, [refreshSide]); // eslint-disable-line react-hooks/exhaustive-deps

  async function send() {
    const t = input.trim();
    if (!t || busy) return;
    setInput("");
    setBusy(true);
    setMsgs((m) => [...m, { role: "user", text: t }]);
    try {
      const res = await postAgent(t);
      const meta = `conf=${res.confidence.toFixed(2)} trace=${res.trace_id}${res.escalated_skye ? " skye" : ""}`;
      setMsgs((m) => [...m, { role: "paradox", text: res.answer, meta }]);
      const sw = res.script_workspace;
      if (
        sw &&
        ((sw.python && sw.python.trim()) || (sw.reference_links && sw.reference_links.length > 0))
      ) {
        setIncomingScriptWs(sw);
      }
    } catch (e) {
      setMsgs((m) => [
        ...m,
        { role: "paradox", text: `Error: ${e instanceof Error ? e.message : String(e)}` },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function searchMem() {
    if (!memQ.trim()) return;
    setMemHits("…");
    try {
      const r = await postMemoryQuery(memQ);
      setMemHits(JSON.stringify(r.hits, null, 2));
    } catch (e) {
      setMemHits(String(e));
    }
  }

  return (
    <div
      className="flex min-h-screen flex-col text-[var(--text-primary)] hud-zone"
      data-hud={hudColor}
    >
      <header className="shrink-0 border-b border-cyan-900/50 bg-[var(--bg-secondary)]">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-4">
            <div>
              <h1 className="text-sm font-semibold tracking-[0.25em] text-cyan-400">
                PARADOX // SOLUTIONS LLM
              </h1>
              <p className="text-[0.625rem] uppercase tracking-widest text-cyan-600">
                Local AI Research Assistant · no cloud LLM
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded border border-cyan-800/60 px-2 py-1 font-mono text-[0.625rem] text-cyan-500/90">
              {health}
            </span>
            {optStatus?.flash_attention && (
              <span className="rounded border border-emerald-800/50 px-2 py-1 font-mono text-[0.625rem] text-emerald-400/90" title={`KV: ${optStatus.kv_cache_type} (${optStatus.kv_savings}) | Embed: ${optStatus.embed_quantize}`}>
                FA+{optStatus.kv_cache_type}
              </span>
            )}
            <span
              className="rounded border border-cyan-800/50 px-2 py-1 font-mono text-[0.625rem] uppercase tracking-wider text-cyan-500/90"
              title="This build has no product licensing"
            >
              local
            </span>
            <button
              type="button"
              onClick={() => cycleFontScale()}
              className="rounded border border-cyan-700/50 px-2 py-1 text-[0.625rem] font-mono uppercase tracking-wider text-cyan-400 hover:bg-cyan-950/40"
              title={`Text size: ${FONT_SCALE_LABELS[fontScale]} (click to cycle Small → XL)`}
            >
              {FONT_SCALE_LABELS[fontScale]}
            </button>
            <button
              type="button"
              onClick={() => cycleHudColor()}
              className="rounded border border-cyan-700/50 px-2 py-1 text-[0.625rem] uppercase tracking-wider text-cyan-400 hover:bg-cyan-950/40"
            >
              HUD
            </button>
          </div>
        </div>
        <div className="flex gap-0 px-4">
          {([
            { id: "session" as const, label: "Session" },
            { id: "eeg" as const, label: "EEG Data" },
            { id: "scripts" as const, label: "Script / code" },
          ]).map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setAppTab(tab.id)}
              className={`relative px-4 py-2 text-[0.625rem] font-semibold uppercase tracking-widest transition-colors ${
                appTab === tab.id
                  ? "text-cyan-300"
                  : "text-cyan-700 hover:text-cyan-500"
              }`}
            >
              {tab.label}
              {appTab === tab.id && (
                <span className="absolute bottom-0 left-0 right-0 h-[2px] bg-cyan-400" />
              )}
            </button>
          ))}
        </div>
      </header>

      {appTab === "eeg" ? (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-3">
          <EegDataPanel />
        </div>
      ) : appTab === "scripts" ? (
        <MneScriptPanel
          incomingWorkspace={incomingScriptWs}
          onConsumedIncoming={clearIncomingScriptWs}
        />
      ) : (
      <div className="grid gap-3 p-3 lg:grid-cols-[1fr_340px]">
        <section className="flex min-h-[70vh] flex-col rounded-lg border border-cyan-900/40 bg-[var(--bg-tertiary)]">
          <div className="border-b border-cyan-900/40 px-3 py-2 text-[0.625rem] uppercase tracking-widest text-cyan-600">
            Session
          </div>
          <div className="styled-scrollbar flex-1 space-y-3 overflow-y-auto p-3 font-mono text-sm">
            {msgs.length === 0 && (
              <p className="text-cyan-700/80">
                Ask anything. Tools: memory, system stats, optional SearXNG / Skye.
              </p>
            )}
            {msgs.map((m, i) => (
              <div
                key={i}
                className={
                  m.role === "user"
                    ? "ml-8 rounded border border-cyan-800/30 bg-cyan-950/20 p-2 text-cyan-100"
                    : "mr-8 rounded border border-cyan-700/40 bg-black/40 p-2 text-cyan-50"
                }
              >
                <div className="mb-1 text-[0.5625rem] uppercase tracking-wider text-cyan-600">
                  {m.role}
                </div>
                {m.role === "paradox" ? (
                  <div className="paradox-markdown font-sans text-[0.8125rem] leading-relaxed tracking-normal text-cyan-100/95">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        a: ({ href, children }) => (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-cyan-400 underline decoration-cyan-600/50 hover:text-cyan-300 hover:decoration-cyan-400 transition-colors"
                          >
                            {children}
                          </a>
                        ),
                        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                        ul: ({ children }) => <ul className="list-disc pl-5 mb-2 space-y-1">{children}</ul>,
                        ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 space-y-1">{children}</ol>,
                        h2: ({ children }) => <h2 className="text-sm font-semibold text-cyan-300 mt-3 mb-1">{children}</h2>,
                        h3: ({ children }) => <h3 className="text-[0.8125rem] font-semibold text-cyan-300/90 mt-2 mb-1">{children}</h3>,
                        strong: ({ children }) => <strong className="font-semibold text-cyan-200">{children}</strong>,
                        code: ({ children }) => (
                          <code className="bg-cyan-950/60 text-cyan-300 px-1 py-0.5 rounded text-[0.75rem] font-mono">{children}</code>
                        ),
                        pre: ({ children }) => (
                          <pre className="bg-black/60 border border-cyan-900/40 rounded p-2 my-2 overflow-x-auto text-[0.75rem] font-mono text-cyan-200">{children}</pre>
                        ),
                        table: ({ children }) => (
                          <div className="overflow-x-auto my-2">
                            <table className="min-w-full text-[0.75rem] border-collapse border border-cyan-800/40">{children}</table>
                          </div>
                        ),
                        th: ({ children }) => <th className="border border-cyan-800/40 px-2 py-1 text-left bg-cyan-950/40 text-cyan-300 font-semibold">{children}</th>,
                        td: ({ children }) => <td className="border border-cyan-800/40 px-2 py-1 text-cyan-100/90">{children}</td>,
                        blockquote: ({ children }) => (
                          <blockquote className="border-l-2 border-cyan-600/50 pl-3 my-2 text-cyan-200/80 italic">{children}</blockquote>
                        ),
                      }}
                    >
                      {m.text}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <div className="whitespace-pre-wrap">{m.text}</div>
                )}
                {m.meta && (
                  <div className="mt-1 text-[0.625rem] text-cyan-700">{m.meta}</div>
                )}
              </div>
            ))}
          </div>
          <div className="flex gap-2 border-t border-cyan-900/40 p-2">
            <input
              className="flex-1 rounded border border-cyan-800/50 bg-black/50 px-3 py-2 text-sm text-cyan-100 outline-none focus:border-cyan-500"
              placeholder="Message Paradox…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && void send()}
            />
            <button
              type="button"
              disabled={busy}
              onClick={() => void send()}
              className="rounded bg-cyan-900/50 px-4 py-2 text-xs font-semibold uppercase tracking-wider text-cyan-200 hover:bg-cyan-800/60 disabled:opacity-40"
            >
              Send
            </button>
          </div>
        </section>

        <aside className="space-y-3">
          <div className="rounded-lg border border-cyan-900/40 bg-[var(--bg-tertiary)] p-3">
            <h2 className="mb-2 text-[0.625rem] font-semibold uppercase tracking-widest text-cyan-600">
              Operating focus
            </h2>
            <pre className="styled-scrollbar max-h-32 overflow-auto whitespace-pre-wrap font-mono text-[0.6875rem] text-cyan-200/90">
              {focus || "(empty — run reflection)"}
            </pre>
          </div>

          <div className="rounded-lg border border-cyan-900/40 bg-[var(--bg-tertiary)] p-3">
            <h2 className="mb-2 text-[0.625rem] font-semibold uppercase tracking-widest text-cyan-600">
              System
            </h2>
            {eegNorms && (
              <div className="mb-2 space-y-0.5 border-b border-cyan-900/30 pb-2">
                <p className="text-[0.5625rem] uppercase tracking-wider text-cyan-600">EEG norms add-on</p>
                <p className="text-[0.5625rem] text-cyan-500/90">
                  {eegNorms.installed
                    ? `Installed${eegNorms.version ? ` v${eegNorms.version}` : ""}`
                    : "Not installed (Cuban z-scores use built-in tables only)"}
                </p>
              </div>
            )}
            {optStatus && (
              <div className="mb-2 space-y-0.5 border-b border-cyan-900/30 pb-2">
                <p className="text-[0.5625rem] uppercase tracking-wider text-cyan-600">GPU Optimizations</p>
                <div className="flex flex-wrap gap-1">
                  <span className={`rounded px-1.5 py-0.5 text-[0.5625rem] font-mono ${optStatus.flash_attention ? "bg-emerald-950/50 text-emerald-400" : "bg-red-950/30 text-red-400"}`}>
                    Flash Attn {optStatus.flash_attention ? "ON" : "OFF"}
                  </span>
                  <span className="rounded bg-cyan-950/50 px-1.5 py-0.5 text-[0.5625rem] font-mono text-cyan-300">
                    KV: {optStatus.kv_cache_type} ({optStatus.kv_savings})
                  </span>
                  <span className="rounded bg-cyan-950/50 px-1.5 py-0.5 text-[0.5625rem] font-mono text-cyan-300">
                    Embed: {optStatus.embed_quantize}
                  </span>
                </div>
              </div>
            )}
            <pre className="styled-scrollbar max-h-48 overflow-auto font-mono text-[0.625rem] text-cyan-300/90">
              {stats ? JSON.stringify(stats, null, 2) : "—"}
            </pre>
            <button
              type="button"
              onClick={() => void refreshSide()}
              className="mt-2 w-full rounded border border-cyan-800/50 py-1 text-[0.625rem] uppercase tracking-wider text-cyan-500 hover:bg-cyan-950/40"
            >
              Refresh
            </button>
          </div>

          <div className="rounded-lg border border-cyan-900/40 bg-[var(--bg-tertiary)] p-3">
            <h2 className="mb-2 text-[0.625rem] font-semibold uppercase tracking-widest text-cyan-600">
              Memory search
            </h2>
            <div className="flex gap-1">
              <input
                className="flex-1 rounded border border-cyan-800/50 bg-black/50 px-2 py-1 font-mono text-[0.6875rem] text-cyan-100"
                value={memQ}
                onChange={(e) => setMemQ(e.target.value)}
                placeholder="semantic query…"
              />
              <button
                type="button"
                onClick={() => void searchMem()}
                className="rounded bg-cyan-900/40 px-2 text-[0.625rem] uppercase text-cyan-300"
              >
                Go
              </button>
            </div>
            <pre className="styled-scrollbar mt-2 max-h-40 overflow-auto font-mono text-[0.5625rem] text-cyan-400/90">
              {memHits}
            </pre>
          </div>

          <FilePanel />
        </aside>
      </div>
      )}
    </div>
  );
}
