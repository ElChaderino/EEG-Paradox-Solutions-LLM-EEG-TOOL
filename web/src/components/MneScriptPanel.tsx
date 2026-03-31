"use client";

/*
 * @license GPL-3.0-or-later
 * Copyright (C) 2026 EEG Paradox Solutions LLM contributors
 *
 * This file is part of Paradox Solutions LLM. See LICENSE in the repository root.
 */

import { useCallback, useEffect, useState } from "react";
import {
  type ScriptWorkspace,
  getEegScriptTemplate,
  getEegScriptTemplates,
  openWorkspace,
  postEegRunPython,
  type EegScriptTemplateRow,
} from "@/lib/api";

const LS_CODE = "paradox_script_workspace_code";
const LS_LINKS = "paradox_script_workspace_links";

function mergeLinks(existing: string, incoming: string[]): string {
  const lines = existing
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
  const set = new Set(lines);
  for (const u of incoming) {
    if (u && !set.has(u)) {
      set.add(u);
      lines.push(u);
    }
  }
  return lines.join("\n");
}

type Props = {
  /** Filled from last `/agent` response; consumed when applied to the editor */
  incomingWorkspace: ScriptWorkspace | null;
  onConsumedIncoming: () => void;
};

export default function MneScriptPanel({ incomingWorkspace, onConsumedIncoming }: Props) {
  const [code, setCode] = useState("");
  const [linksText, setLinksText] = useState("");
  const [output, setOutput] = useState("");
  const [running, setRunning] = useState(false);
  const [templates, setTemplates] = useState<EegScriptTemplateRow[]>([]);
  const [templatePick, setTemplatePick] = useState("");

  useEffect(() => {
    try {
      setCode(localStorage.getItem(LS_CODE) || "");
      setLinksText(localStorage.getItem(LS_LINKS) || "");
    } catch {
      /* private mode */
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(LS_CODE, code);
    } catch {
      /* ignore */
    }
  }, [code]);

  useEffect(() => {
    try {
      localStorage.setItem(LS_LINKS, linksText);
    } catch {
      /* ignore */
    }
  }, [linksText]);

  useEffect(() => {
    if (!incomingWorkspace) return;
    if (incomingWorkspace.python?.trim()) {
      setCode(incomingWorkspace.python);
    }
    if (incomingWorkspace.reference_links?.length) {
      setLinksText((prev) => mergeLinks(prev, incomingWorkspace.reference_links));
    }
    setOutput((o) =>
      o +
      (o ? "\n\n" : "") +
      `[Script tab] Updated from assistant (${incomingWorkspace.source || "reply"}).`,
    );
    onConsumedIncoming();
  }, [incomingWorkspace, onConsumedIncoming]);

  const refreshTemplates = useCallback(async () => {
    try {
      const r = await getEegScriptTemplates();
      setTemplates(r.templates);
    } catch {
      setTemplates([]);
    }
  }, []);

  useEffect(() => {
    void refreshTemplates();
  }, [refreshTemplates]);

  const loadTemplate = async () => {
    if (!templatePick) return;
    try {
      const r = await getEegScriptTemplate(templatePick);
      setCode(r.content);
      setOutput(`Loaded template: ${r.name}`);
    } catch (e) {
      setOutput(String(e));
    }
  };

  const runScript = async () => {
    const s = code.trim();
    if (!s || running) return;
    setRunning(true);
    setOutput("Running…");
    try {
      const r = await postEegRunPython(s);
      const parts: string[] = [];
      parts.push(r.ok ? "Exit OK" : `Exit ${r.exit_code}${r.error ? `: ${r.error}` : ""}`);
      if (r.stdout) parts.push("--- stdout ---\n" + r.stdout);
      if (r.stderr) parts.push("--- stderr ---\n" + r.stderr);
      if (r.new_files?.length)
        parts.push("--- new files in output/ ---\n" + r.new_files.join("\n"));
      setOutput(parts.join("\n\n"));
    } catch (e) {
      setOutput(String(e));
    } finally {
      setRunning(false);
    }
  };

  const linkLines = linksText
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => /^https?:\/\//i.test(l));

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-3 text-[var(--text-primary)]">
      <div className="rounded-lg border border-cyan-900/40 bg-[var(--bg-tertiary)] p-3">
        <h2 className="mb-2 text-[0.625rem] font-semibold uppercase tracking-widest text-cyan-600">
          MNE / Python workspace
        </h2>
        <p className="mb-3 text-[0.6875rem] leading-relaxed text-cyan-600/90">
          Scripts run with cwd <code className="text-cyan-500">data/eeg_workspace</code> (same as{" "}
          <code className="text-cyan-500">run_python_analysis</code>). Save figures under{" "}
          <code className="text-cyan-500">output/</code>. Ask the assistant for code — it appears here when it
          runs a tool or puts a <code className="text-cyan-500">```python</code> block in the answer.
        </p>
        <div className="mb-2 flex flex-wrap items-end gap-2">
          <div className="flex min-w-[200px] flex-1 flex-col gap-1">
            <label className="text-[0.5625rem] uppercase tracking-wider text-cyan-700">Load template</label>
            <select
              className="rounded border border-cyan-800/50 bg-black/50 px-2 py-1.5 font-mono text-[0.6875rem] text-cyan-100"
              value={templatePick}
              onChange={(e) => setTemplatePick(e.target.value)}
            >
              <option value="">— select —</option>
              {templates.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            disabled={!templatePick}
            onClick={() => void loadTemplate()}
            className="rounded border border-cyan-700/50 px-3 py-1.5 text-[0.625rem] font-semibold uppercase tracking-wider text-cyan-300 hover:bg-cyan-950/40 disabled:opacity-40"
          >
            Insert
          </button>
          <button
            type="button"
            onClick={() => void refreshTemplates()}
            className="rounded border border-cyan-800/40 px-3 py-1.5 text-[0.625rem] uppercase text-cyan-500 hover:bg-cyan-950/30"
          >
            Refresh list
          </button>
        </div>
        <label className="mb-1 block text-[0.5625rem] uppercase tracking-wider text-cyan-700">
          Python script
        </label>
        <textarea
          className="styled-scrollbar mb-3 h-[min(42vh,360px)] w-full resize-y rounded border border-cyan-800/50 bg-black/60 p-2 font-mono text-[0.75rem] leading-snug text-cyan-100 outline-none focus:border-cyan-500"
          spellCheck={false}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder='INPUT_FILE = "your_recording.edf"'
        />
        <label className="mb-1 block text-[0.5625rem] uppercase tracking-wider text-cyan-700">
          Reference links (one URL per line — docs, papers, mne.tools)
        </label>
        <textarea
          className="styled-scrollbar mb-3 h-20 w-full resize-y rounded border border-cyan-800/50 bg-black/50 p-2 font-mono text-[0.6875rem] text-cyan-200 outline-none focus:border-cyan-500"
          value={linksText}
          onChange={(e) => setLinksText(e.target.value)}
          placeholder="https://mne.tools/stable/index.html"
        />
        {linkLines.length > 0 && (
          <ul className="mb-3 space-y-1 text-[0.6875rem]">
            {linkLines.map((u) => (
              <li key={u}>
                <a
                  href={u}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-cyan-400 underline decoration-cyan-700 hover:text-cyan-300"
                >
                  {u}
                </a>
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={running || !code.trim()}
            onClick={() => void runScript()}
            className="rounded bg-cyan-900/50 px-4 py-2 text-xs font-semibold uppercase tracking-wider text-cyan-200 hover:bg-cyan-800/60 disabled:opacity-40"
          >
            {running ? "Running…" : "Run script"}
          </button>
          <button
            type="button"
            onClick={() => void openWorkspace().then((r) => setOutput((o) => o + `\nOpened: ${r.path}`)).catch((e) => setOutput(String(e)))}
            className="rounded border border-cyan-800/50 px-3 py-2 text-[0.625rem] uppercase tracking-wider text-cyan-400 hover:bg-cyan-950/40"
          >
            Open output folder
          </button>
          <span className="self-center text-[0.625rem] text-cyan-700">
            PNG/HTML land in <code className="text-cyan-500">output/</code>
          </span>
        </div>
      </div>
      <div className="min-h-0 flex-1 rounded-lg border border-cyan-900/40 bg-black/30 p-3">
        <div className="mb-1 text-[0.625rem] font-semibold uppercase tracking-widest text-cyan-600">
          Run output
        </div>
        <pre className="styled-scrollbar max-h-[min(35vh,280px)] overflow-auto whitespace-pre-wrap font-mono text-[0.6875rem] text-cyan-200/95">
          {output || "—"}
        </pre>
      </div>
    </div>
  );
}
