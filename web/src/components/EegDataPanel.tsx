"use client";

/*
 * @license GPL-3.0-or-later
 * Copyright (C) 2026 EEG Paradox Solutions LLM contributors
 *
 * This file is part of Paradox Solutions LLM. See LICENSE in the repository root.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  type EegJob,
  type EegJobDetail,
  type EegProcessOptions,
  deleteEegJob,
  eegJobFileUrl,
  getEegJob,
  listEegJobs,
  openWorkspace,
  processEeg,
} from "@/lib/api";

type FileFilter = "all" | "html" | "interactive" | "image" | "json";

function fmtSize(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

function fmtDate(s: string): string {
  try {
    return new Date(s).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return s; }
}

const INTERACTIVE_PATTERNS = [
  "3d", "interactive", "scalp_3d", "microstate",
  "_session", "fft_spectra",
];

function isInteractiveHtml(name: string): boolean {
  const lower = name.toLowerCase();
  return (lower.endsWith(".html") || lower.endsWith(".htm")) && INTERACTIVE_PATTERNS.some((p) => lower.includes(p));
}

function fileType(name: string): string {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (["html", "htm"].includes(ext)) return "html";
  if (["png", "jpg", "jpeg", "svg"].includes(ext)) return "image";
  if (ext === "json") return "json";
  if (["fif", "edf", "bdf"].includes(ext)) return "data";
  return "other";
}

/** Group output files for compact sidebar navigation */
type OutputCategory =
  | "3d_scalp"
  | "topomap_html"
  | "html_other"
  | "image"
  | "json"
  | "data"
  | "other";

const OUTPUT_CATEGORY_ORDER: OutputCategory[] = [
  "3d_scalp",
  "topomap_html",
  "html_other",
  "image",
  "json",
  "data",
  "other",
];

const OUTPUT_CATEGORY_LABEL: Record<OutputCategory, string> = {
  "3d_scalp": "3D scalp",
  topomap_html: "Topomap & spectral (HTML)",
  html_other: "Other HTML",
  image: "Images",
  json: "JSON",
  data: "Data (FIF / raw)",
  other: "Other",
};

function outputCategory(filename: string): OutputCategory {
  const lower = filename.toLowerCase();
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";

  if (lower.includes("3d_scalp")) return "3d_scalp";

  if (["html", "htm"].includes(ext)) {
    if (lower.startsWith("topomap_") || lower.includes("fft_spectra_grid")) {
      return "topomap_html";
    }
    return "html_other";
  }
  if (["png", "jpg", "jpeg", "svg"].includes(ext)) return "image";
  if (ext === "json") return "json";
  if (["fif", "edf", "bdf"].includes(ext)) return "data";
  return "other";
}

function groupFilesByCategory(files: string[]): Map<OutputCategory, string[]> {
  const map = new Map<OutputCategory, string[]>();
  for (const c of OUTPUT_CATEGORY_ORDER) map.set(c, []);
  for (const f of files) {
    const cat = outputCategory(f);
    map.get(cat)!.push(f);
  }
  for (const c of OUTPUT_CATEGORY_ORDER) {
    map.set(c, [...map.get(c)!].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" })));
  }
  return map;
}

const TYPE_COLORS: Record<string, string> = {
  html: "text-emerald-400 border-emerald-700/40",
  image: "text-violet-400 border-violet-700/40",
  json: "text-amber-400 border-amber-700/40",
  data: "text-cyan-400 border-cyan-700/40",
  other: "text-gray-400 border-gray-700/40",
};

const STATUS_STYLES: Record<string, string> = {
  complete: "bg-emerald-950/50 text-emerald-400",
  complete_with_warnings: "bg-amber-950/50 text-amber-400",
  error: "bg-red-950/50 text-red-400",
  running: "bg-cyan-950/50 text-cyan-400 animate-pulse",
  queued: "bg-cyan-950/50 text-cyan-500",
};

function MetricsSummary({ metrics }: { metrics: Record<string, unknown> }) {
  const q = metrics?.quality as Record<string, unknown> | undefined;
  if (!q) return null;
  const steps = metrics?.step_status as Record<string, string> | undefined;
  const okCount = steps ? Object.values(steps).filter((v) => v === "OK").length : 0;
  const totalSteps = steps ? Object.keys(steps).length : 0;
  const bpm = (typeof q.band_power_mean === "object" && q.band_power_mean !== null)
    ? (q.band_power_mean as Record<string, number>)
    : null;

  const val = (k: string) => {
    const v = q[k];
    return typeof v === "number" ? v : null;
  };

  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 rounded border border-cyan-900/40 bg-black/30 p-3 text-[0.5625rem]">
      <div className="col-span-2 mb-1 text-[0.625rem] font-semibold uppercase tracking-widest text-cyan-500">
        Pipeline Summary
      </div>
      <div className="text-cyan-600">Channels</div>
      <div className="text-cyan-200">{val("n_channels_original") ?? "?"} ({val("n_channels_clean") ?? "?"} clean)</div>
      <div className="text-cyan-600">Sample Rate</div>
      <div className="text-cyan-200">{val("sfreq") ?? "?"} Hz</div>
      <div className="text-cyan-600">Duration</div>
      <div className="text-cyan-200">{val("duration_sec") !== null ? `${val("duration_sec")!.toFixed(1)}s` : "?"}</div>
      <div className="text-cyan-600">Epochs</div>
      <div className="text-cyan-200">{val("epochs_kept") ?? "?"} / {val("epochs_total") ?? "?"} kept</div>
      <div className="text-cyan-600">Rejected</div>
      <div className="text-cyan-200">{val("epochs_rejected_pct") !== null ? `${val("epochs_rejected_pct")!.toFixed(1)}%` : "?"}</div>
      <div className="text-cyan-600">Bad Channels</div>
      <div className="text-cyan-200">{Array.isArray(q.bad_channels) ? (q.bad_channels.length > 0 ? (q.bad_channels as string[]).join(", ") : "None") : "?"}</div>
      <div className="text-cyan-600">ICA Components</div>
      <div className="text-cyan-200">{val("ica_n_components") ?? "?"} fitted, {val("ica_excluded") ?? 0} excluded</div>
      <div className="text-cyan-600">Steps</div>
      <div className="text-cyan-200">{okCount} / {totalSteps} OK</div>
      {bpm !== null && (
        <>
          <div className="col-span-2 mt-1 text-[0.625rem] font-semibold uppercase tracking-widest text-cyan-500">Band Power</div>
          {Object.entries(bpm).map(([b, v]) => (
            <div key={b} className="contents">
              <div className="text-cyan-600 capitalize">{b}</div>
              <div className="text-cyan-200">{typeof v === "number" ? v.toExponential(2) : String(v)}</div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

export default function EegDataPanel() {
  const [jobs, setJobs] = useState<EegJob[]>([]);
  const [activeJob, setActiveJob] = useState<EegJobDetail | null>(null);
  const [filter, setFilter] = useState<FileFilter>("all");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [jsonContent, setJsonContent] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [showMetrics, setShowMetrics] = useState(false);
  const [condition, setCondition] = useState("EC");
  const [outputMode, setOutputMode] = useState("standard");
  const [remontageRef, setRemontageRef] = useState("");
  const [fullscreen, setFullscreen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshJobs = useCallback(async () => {
    try {
      const r = await listEegJobs();
      setJobs(r.jobs);
    } catch { /* not ready */ }
  }, []);

  useEffect(() => {
    void refreshJobs();
    const id = setInterval(() => void refreshJobs(), 10000);
    return () => clearInterval(id);
  }, [refreshJobs]);

  const selectJob = useCallback(async (jobId: string) => {
    try {
      const detail = await getEegJob(jobId);
      setActiveJob(detail);
      setSelectedFile(null);
      setShowMetrics(false);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!activeJob) return;
    if (["complete", "complete_with_warnings", "error"].includes(activeJob.status)) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      return;
    }
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const detail = await getEegJob(activeJob.id);
        setActiveJob(detail);
        if (["complete", "complete_with_warnings", "error"].includes(detail.status)) {
          if (pollRef.current) clearInterval(pollRef.current);
          void refreshJobs();
        }
      } catch { /* ignore */ }
    }, 1500);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [activeJob?.id, activeJob?.status, refreshJobs]);

  useEffect(() => {
    if (!activeJob || !selectedFile) return;
    if (fileType(selectedFile) === "json") {
      fetch(eegJobFileUrl(activeJob.id, selectedFile))
        .then((r) => r.text())
        .then((t) => {
          try { setJsonContent(JSON.stringify(JSON.parse(t), null, 2)); }
          catch { setJsonContent(t); }
        })
        .catch(() => setJsonContent("Failed to load"));
    }
  }, [activeJob?.id, selectedFile]);

  async function handleUpload(fileList: FileList | File[]) {
    setUploadError("");
    const files = Array.from(fileList);
    const edf = files.find((f) =>
      [".edf", ".bdf", ".set", ".fif", ".vhdr", ".cnt"].some((e) =>
        f.name.toLowerCase().endsWith(e)
      )
    );
    if (!edf) {
      setUploadError("No valid EEG file found (EDF, BDF, SET, FIF, VHDR, CNT)");
      return;
    }
    setUploading(true);
    try {
      const res = await processEeg(edf, { condition, output_mode: outputMode, remontage_ref: remontageRef });
      void refreshJobs();
      void selectJob(res.job_id);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleDeleteJob(jobId: string) {
    try {
      await deleteEegJob(jobId);
      if (activeJob?.id === jobId) { setActiveJob(null); setSelectedFile(null); }
      void refreshJobs();
    } catch { /* ignore */ }
  }

  const outputFiles = activeJob?.output_files ?? [];
  const filteredFiles = outputFiles.filter((f) => {
    if (filter === "all") return true;
    if (filter === "interactive") return isInteractiveHtml(f);
    return fileType(f) === filter;
  });

  const counts = outputFiles.reduce<Record<string, number>>((acc, f) => {
    const t = fileType(f);
    acc[t] = (acc[t] || 0) + 1;
    if (isInteractiveHtml(f)) acc["interactive"] = (acc["interactive"] || 0) + 1;
    return acc;
  }, {});

  const groupedFiltered = useMemo(
    () => groupFilesByCategory(filteredFiles),
    [filteredFiles],
  );

  const isProcessing = activeJob && (activeJob.status === "queued" || activeJob.status === "running");
  const isDone = activeJob && ["complete", "complete_with_warnings"].includes(activeJob.status);

  function renderFileRow(f: string) {
    const ft = fileType(f);
    return (
      <button
        key={f}
        type="button"
        onClick={() => { setSelectedFile(f); setShowMetrics(false); }}
        className={`flex w-full items-center gap-1.5 rounded px-2 py-1 text-left transition-colors ${
          selectedFile === f && !showMetrics ? "bg-cyan-950/40 border border-cyan-500/50" : "hover:bg-cyan-950/20 border border-transparent"
        }`}
      >
        <span className={`shrink-0 rounded border px-1 py-0.5 text-[0.4375rem] uppercase ${TYPE_COLORS[ft] || "text-gray-400 border-gray-700/40"}`}>{ft}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-[0.5625rem] text-cyan-200">{f}</span>
      </button>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col gap-3 overflow-hidden lg:flex-row lg:items-stretch">
      {/* Left panel: jobs + upload */}
      <div className="flex w-full min-h-0 max-h-[min(38vh,22rem)] flex-shrink-0 flex-col overflow-hidden rounded-lg border border-cyan-900/40 bg-[var(--bg-tertiary)] lg:max-h-none lg:h-full lg:w-72 xl:w-80">
        {/* Upload zone */}
        <div className="border-b border-cyan-900/40 p-3">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); if (e.dataTransfer.files.length) void handleUpload(e.dataTransfer.files); }}
            onClick={() => inputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center rounded border-2 border-dashed px-3 py-4 text-center transition-colors ${
              dragOver ? "border-cyan-400 bg-cyan-950/40" : "border-cyan-800/50 bg-black/20 hover:border-cyan-600/60"
            }`}
          >
            {uploading ? (
              <span className="text-[0.625rem] text-cyan-400 animate-pulse">Uploading & processing...</span>
            ) : (
              <>
                <span className="text-[0.6875rem] font-semibold text-cyan-400">Drop EDF to Process</span>
                <span className="mt-0.5 text-[0.5625rem] text-cyan-700">
                  Auto-runs 24-step pipeline + Clinical Q + Band Power
                </span>
              </>
            )}
            <input
              ref={inputRef}
              type="file"
              className="hidden"
              accept=".edf,.bdf,.set,.fif,.vhdr,.cnt"
              onChange={(e) => { if (e.target.files) void handleUpload(e.target.files); e.target.value = ""; }}
            />
          </div>
          {uploadError && (
            <p className="mt-1.5 rounded border border-red-900/40 bg-red-950/30 px-2 py-1 text-[0.5625rem] text-red-400">
              {uploadError}
            </p>
          )}
          {/* Scan settings */}
          <div className="mt-2 grid grid-cols-3 gap-1.5">
            <div>
              <label className="block text-[0.5rem] uppercase tracking-widest text-cyan-700 mb-0.5">Condition</label>
              <select value={condition} onChange={(e) => setCondition(e.target.value)} className="w-full rounded border border-cyan-800/50 bg-black/40 px-1.5 py-1 text-[0.5625rem] text-cyan-200 focus:border-cyan-500 focus:outline-none">
                <option value="EC">Eyes Closed</option>
                <option value="EO">Eyes Open</option>
                <option value="task">Task</option>
                <option value="resting">Resting</option>
              </select>
            </div>
            <div>
              <label className="block text-[0.5rem] uppercase tracking-widest text-cyan-700 mb-0.5">Mode</label>
              <select value={outputMode} onChange={(e) => setOutputMode(e.target.value)} className="w-full rounded border border-cyan-800/50 bg-black/40 px-1.5 py-1 text-[0.5625rem] text-cyan-200 focus:border-cyan-500 focus:outline-none">
                <option value="standard">Standard</option>
                <option value="clinical">Clinical</option>
                <option value="exploratory">Exploratory</option>
              </select>
            </div>
            <div>
              <label className="block text-[0.5rem] uppercase tracking-widest text-cyan-700 mb-0.5">Reference</label>
              <select value={remontageRef} onChange={(e) => setRemontageRef(e.target.value)} className="w-full rounded border border-cyan-800/50 bg-black/40 px-1.5 py-1 text-[0.5625rem] text-cyan-200 focus:border-cyan-500 focus:outline-none">
                <option value="">Keep Original</option>
                <option value="average">Average</option>
                <option value="linked_ears">Linked Ears</option>
                <option value="cz">Cz</option>
              </select>
            </div>
          </div>
        </div>

        {/* Job list */}
        <div className="flex items-center justify-between border-b border-cyan-900/40 px-3 py-2">
          <span className="text-[0.625rem] uppercase tracking-widest text-cyan-600">Processing Jobs</span>
          <div className="flex gap-1">
            <button type="button" onClick={() => void refreshJobs()} className="rounded border border-cyan-800/50 px-1.5 py-0.5 text-[0.5625rem] text-cyan-500 hover:bg-cyan-950/40" title="Refresh">↻</button>
            <button type="button" onClick={() => void openWorkspace().catch(() => {})} className="rounded border border-cyan-800/50 px-1.5 py-0.5 text-[0.5625rem] text-cyan-500 hover:bg-cyan-950/40" title="Open folder">📂</button>
          </div>
        </div>

        <div className="styled-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain p-2 space-y-1">
          {jobs.length === 0 && (
            <p className="py-6 text-center text-[0.625rem] text-cyan-700">No jobs yet — drop an EDF above</p>
          )}
          {jobs.map((j) => (
            <div key={j.id} className={`group relative rounded border transition-colors ${
              activeJob?.id === j.id
                ? "border-cyan-500/60 bg-cyan-950/40"
                : "border-cyan-900/40 bg-black/20 hover:border-cyan-700/50"
            }`}>
              <button
                type="button"
                onClick={() => void selectJob(j.id)}
                className="w-full p-2 text-left"
              >
                <div className="flex items-center justify-between">
                  <span className="truncate font-mono text-[0.625rem] text-cyan-200">{j.filename}</span>
                  <span className={`ml-1 shrink-0 rounded px-1.5 py-0.5 text-[0.5rem] uppercase font-semibold ${STATUS_STYLES[j.status] || "bg-cyan-950/50 text-cyan-500"}`}>
                    {j.status.replace(/_/g, " ")}
                  </span>
                </div>
                {(j.status === "running" || j.status === "queued") && (
                  <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-cyan-900/40">
                    <div className="h-full rounded-full bg-cyan-500 transition-all duration-500" style={{ width: `${j.progress}%` }} />
                  </div>
                )}
                <div className="mt-1 flex justify-between text-[0.5rem] text-cyan-700">
                  <span>{fmtDate(j.started)}</span>
                  <span className="flex gap-1">
                    {j.condition && <span className="rounded bg-cyan-950/50 px-1 text-[0.4375rem] text-cyan-500">{j.condition}</span>}
                    {j.output_mode && j.output_mode !== "standard" && <span className="rounded bg-violet-950/50 px-1 text-[0.4375rem] text-violet-400">{j.output_mode}</span>}
                    {j.output_count ? <span>{j.output_count} files</span> : null}
                  </span>
                </div>
              </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); void handleDeleteJob(j.id); }}
                className="absolute right-1 top-1 hidden rounded border border-red-900/40 px-1 py-0.5 text-[0.5rem] text-red-500/70 hover:bg-red-950/40 group-hover:block"
                title="Delete job"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Middle: file browser (when job is done) */}
      {isDone && activeJob && (
        <div className="flex w-full min-h-0 max-h-[min(42vh,26rem)] flex-shrink-0 flex-col overflow-hidden rounded-lg border border-cyan-900/40 bg-[var(--bg-tertiary)] lg:max-h-none lg:h-full lg:w-56 xl:w-64">
          <div className="flex shrink-0 items-center justify-between border-b border-cyan-900/40 px-3 py-2">
            <span className="text-[0.625rem] uppercase tracking-widest text-cyan-600">Output Files</span>
            <button
              type="button"
              onClick={() => { setShowMetrics((p) => !p); setSelectedFile(null); }}
              className={`rounded border px-1.5 py-0.5 text-[0.5rem] uppercase tracking-wider ${
                showMetrics ? "border-cyan-500/50 text-cyan-300 bg-cyan-900/30" : "border-cyan-900/40 text-cyan-600 hover:bg-cyan-950/30"
              }`}
            >
              Summary
            </button>
          </div>
          <div className="flex shrink-0 flex-wrap gap-1 border-b border-cyan-900/40 px-2 py-1.5">
            {(["all", "image", "json", "html", "interactive"] as const).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => { setFilter(f); setShowMetrics(false); }}
                className={`rounded px-1.5 py-0.5 text-[0.5rem] uppercase tracking-wider ${
                  filter === f && !showMetrics
                    ? "bg-cyan-900/50 text-cyan-300 border border-cyan-500/50"
                    : "text-cyan-600 border border-cyan-900/40 hover:bg-cyan-950/30"
                }`}
              >
                {f}{f !== "all" && counts[f] ? ` ${counts[f]}` : ""}{f === "all" ? ` ${outputFiles.length}` : ""}
              </button>
            ))}
          </div>
          <div className="shrink-0 border-b border-cyan-900/40 px-2 py-1.5">
            <label htmlFor="eeg-quick-open" className="mb-1 block text-[0.5rem] uppercase tracking-widest text-cyan-700">
              Quick open
            </label>
            <select
              id="eeg-quick-open"
              value={selectedFile ?? ""}
              onChange={(e) => {
                const v = e.target.value;
                if (v) {
                  setSelectedFile(v);
                  setShowMetrics(false);
                }
              }}
              className="w-full max-w-full rounded border border-cyan-800/50 bg-black/50 px-1.5 py-1 font-mono text-[0.5rem] text-cyan-200 outline-none focus:border-cyan-500"
            >
              <option value="">— Choose file —</option>
              {OUTPUT_CATEGORY_ORDER.map((cat) => {
                const list = groupedFiltered.get(cat) ?? [];
                if (!list.length) return null;
                return (
                  <optgroup key={cat} label={`${OUTPUT_CATEGORY_LABEL[cat]} (${list.length})`}>
                    {list.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </optgroup>
                );
              })}
            </select>
          </div>
          <div className="styled-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain p-1.5">
            {OUTPUT_CATEGORY_ORDER.map((cat) => {
              const list = groupedFiltered.get(cat) ?? [];
              if (!list.length) return null;
              return (
                <details key={cat} className="mb-1 overflow-hidden rounded border border-cyan-900/35 bg-black/15">
                  <summary className="cursor-pointer select-none list-none px-2 py-1.5 text-[0.5625rem] font-semibold text-cyan-400 marker:content-none [&::-webkit-details-marker]:hidden hover:bg-cyan-950/25">
                    <span className="text-cyan-500">▸</span>{" "}
                    {OUTPUT_CATEGORY_LABEL[cat]}{" "}
                    <span className="font-mono font-normal text-cyan-600">({list.length})</span>
                  </summary>
                  <div className="space-y-0.5 border-t border-cyan-900/25 p-1">{list.map((f) => renderFileRow(f))}</div>
                </details>
              );
            })}
          </div>
        </div>
      )}

      {/* Right: viewer / progress / metrics */}
      <div className={`flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-cyan-900/40 bg-[var(--bg-tertiary)] ${fullscreen ? "fixed inset-0 z-50 rounded-none" : ""}`}>
        <div className="flex shrink-0 items-center justify-between border-b border-cyan-900/40 px-3 py-2">
          <span className="truncate text-[0.625rem] uppercase tracking-widest text-cyan-600">
            {showMetrics ? "Pipeline Metrics" : selectedFile || (isProcessing ? "Processing..." : "Viewer")}
            {selectedFile && isInteractiveHtml(selectedFile) && <span className="ml-1 text-[0.5rem] text-emerald-500">3D Interactive</span>}
          </span>
          <div className="flex shrink-0 gap-1">
            {selectedFile && activeJob && (
              <a href={eegJobFileUrl(activeJob.id, selectedFile)} target="_blank" rel="noopener noreferrer" className="rounded border border-cyan-800/50 px-2 py-0.5 text-[0.5625rem] text-cyan-500 hover:bg-cyan-950/40">Open ↗</a>
            )}
            {(selectedFile || showMetrics) && (
              <button type="button" onClick={() => setFullscreen((p) => !p)} className="rounded border border-cyan-800/50 px-2 py-0.5 text-[0.5625rem] text-cyan-500 hover:bg-cyan-950/40" title="Toggle fullscreen">
                {fullscreen ? "⊡" : "⊞"}
              </button>
            )}
            {(selectedFile || showMetrics) && (
              <button type="button" onClick={() => { setSelectedFile(null); setShowMetrics(false); setFullscreen(false); }} className="rounded border border-cyan-800/50 px-2 py-0.5 text-[0.5625rem] text-cyan-500 hover:bg-cyan-950/40">✕</button>
            )}
          </div>
        </div>

        <div className="relative min-h-0 flex-1 overflow-hidden">
          {/* Processing / progress */}
          {isProcessing && activeJob ? (
            <div className="absolute inset-0 flex min-h-0 flex-col items-center justify-center gap-4 overflow-auto p-6">
              <div className="text-3xl animate-pulse">⚡</div>
              <div className="w-full max-w-sm">
                <div className="mb-2 flex justify-between text-[0.625rem] text-cyan-500">
                  <span>{activeJob.status === "queued" ? "Queued" : "Processing"} {activeJob.filename}</span>
                  <span>{activeJob.progress}%</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-cyan-900/40">
                  <div className="h-full rounded-full bg-gradient-to-r from-cyan-600 to-cyan-400 transition-all duration-500" style={{ width: `${activeJob.progress}%` }} />
                </div>
              </div>
              <div className="styled-scrollbar w-full max-w-sm max-h-48 overflow-y-auto rounded border border-cyan-900/40 bg-black/30 p-2">
                {activeJob.messages.map((m, i) => (
                  <p key={i} className={`font-mono text-[0.5625rem] ${m.toLowerCase().includes("error") ? "text-red-400/80" : "text-cyan-600"}`}>{m}</p>
                ))}
              </div>
            </div>

          ) : activeJob?.status === "error" ? (
            <div className="absolute inset-0 flex min-h-0 flex-col items-center justify-center gap-2 overflow-auto p-6 text-center">
              <div className="text-3xl text-red-500/60">⚠</div>
              <p className="text-[0.6875rem] text-red-400">Processing failed</p>
              <p className="max-w-sm text-[0.5625rem] text-red-400/70 font-mono">{activeJob.error}</p>
              {activeJob.messages.length > 0 && (
                <div className="mt-1 w-full max-w-sm">
                  <p className="mb-1 text-[0.5rem] uppercase tracking-widest text-amber-600/90">
                    Partial log (job did not finish — lines below are not live progress)
                  </p>
                  <div className="styled-scrollbar max-h-32 overflow-y-auto rounded border border-amber-900/35 bg-black/30 p-2">
                    {activeJob.messages.map((m, i) => (
                      <p
                        key={i}
                        className={`font-mono text-[0.5625rem] ${
                          m.includes("— Job interrupted") ? "text-amber-400/90" : "text-cyan-700/80"
                        }`}
                      >
                        {m}
                      </p>
                    ))}
                  </div>
                </div>
              )}
            </div>

          ) : showMetrics && activeJob ? (
            <div className="styled-scrollbar absolute inset-0 overflow-auto p-4">
              <MetricsSummary metrics={activeJob.metrics} />
              {activeJob.status === "complete_with_warnings" && activeJob.error && (
                <div className="mt-3 rounded border border-amber-900/40 bg-amber-950/20 p-2 text-[0.5625rem] text-amber-400">
                  <span className="font-semibold">Warning:</span> {activeJob.error}
                </div>
              )}
            </div>

          ) : selectedFile && activeJob ? (
            fileType(selectedFile) === "html" ? (
              <div className="absolute inset-0 min-h-0">
                <iframe
                  src={eegJobFileUrl(activeJob.id, selectedFile)}
                  className="h-full w-full border-0"
                  title={selectedFile}
                  sandbox="allow-scripts allow-same-origin allow-popups allow-downloads"
                />
              </div>
            ) : fileType(selectedFile) === "image" ? (
              <div className="absolute inset-0 flex min-h-0 items-center justify-center overflow-auto bg-black/20 p-4">
                <img src={eegJobFileUrl(activeJob.id, selectedFile)} alt={selectedFile} className="max-h-full max-w-full rounded object-contain" />
              </div>
            ) : fileType(selectedFile) === "json" ? (
              <pre className="styled-scrollbar absolute inset-0 overflow-auto p-4 font-mono text-[0.6875rem] text-cyan-200/90 bg-black/20">{jsonContent || "Loading..."}</pre>
            ) : (
              <div className="absolute inset-0 flex min-h-0 flex-col items-center justify-center gap-2 text-center">
                <p className="text-[0.6875rem] text-cyan-700">Preview not available for this file type</p>
                <a href={eegJobFileUrl(activeJob.id, selectedFile)} download className="rounded border border-cyan-800/50 px-3 py-1 text-[0.625rem] text-cyan-500 hover:bg-cyan-950/40">Download</a>
              </div>
            )

          ) : (
            <div className="absolute inset-0 flex min-h-0 flex-col items-center justify-center gap-2 overflow-auto p-6 text-center">
              <div className="text-3xl text-cyan-900/60">📊</div>
              <p className="text-[0.6875rem] text-cyan-700">
                {activeJob ? "Select a file or view the Summary" : "Drop an EDF file to begin analysis"}
              </p>
              <p className="max-w-xs text-[0.5625rem] text-cyan-800">
                Upload an EDF/BDF and the system auto-runs the full pipeline, Clinical Q assessment, band power analysis, and interactive 3D visualizations (topomaps, PSD, microstate explorer). Use the Interactive filter for 3D views and the Session tab for LLM interpretation.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

