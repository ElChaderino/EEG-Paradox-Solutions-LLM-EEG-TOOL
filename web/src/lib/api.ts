/*
 * @license GPL-3.0-or-later
 * Copyright (C) 2026 EEG Paradox Solutions LLM contributors
 *
 * This file is part of Paradox Solutions LLM. See LICENSE in the repository root.
 */

const base = () => {
  if (typeof window !== "undefined" && window.__TAURI_INTERNALS__) {
    return "http://127.0.0.1:8765";
  }
  const u =
    process.env.NEXT_PUBLIC_PARADOX_API ||
    process.env.NEXT_PUBLIC_HEX_API ||
    process.env.NEXT_PUBLIC_ANTON_API ||
    "http://127.0.0.1:8765";
  return u.replace(/\/$/, "");
};

export type ScriptWorkspace = {
  python: string | null;
  reference_links: string[];
  source: string | null;
};

export async function postAgent(message: string) {
  const r = await fetch(`${base()}/agent`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, interface: "desktop" }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{
    answer: string;
    confidence: number;
    steps: unknown[];
    trace_id: string;
    escalated_skye: boolean;
    script_workspace?: ScriptWorkspace;
  }>;
}

export interface Optimizations {
  flash_attention: boolean;
  kv_cache_type: string;
  kv_savings: string;
  embed_quantize: string;
}

export interface EegNormsAddonStatus {
  installed: boolean;
  root: string | null;
  cuban_databases: string | null;
  version: string | null;
  id: string | null;
}

export async function getHealth() {
  const r = await fetch(`${base()}/health`);
  if (!r.ok) throw new Error("health failed");
  return r.json() as Promise<{
    status: string;
    ollama: boolean;
    optimizations?: Optimizations;
    eeg_norms_addon?: EegNormsAddonStatus;
  }>;
}

/** Ask the API to run `ollama serve` if Ollama is not responding (browser / dev). */
export async function postEnsureOllama() {
  const r = await fetch(`${base()}/system/ensure-ollama`, { method: "POST" });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ ollama: boolean; base: string }>;
}

export async function getStats() {
  const r = await fetch(`${base()}/system/stats`);
  if (!r.ok) throw new Error("stats failed");
  return r.json() as Promise<{ stats: Record<string, unknown> }>;
}

export async function getFocus() {
  const r = await fetch(`${base()}/focus`);
  if (!r.ok) throw new Error("focus failed");
  return r.json() as Promise<{ current_focus: string }>;
}

export async function postMemoryQuery(query: string, collection?: string | null) {
  const r = await fetch(`${base()}/memory/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, collection: collection || null, top_k: 8 }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ hits: unknown[] }>;
}

// ── EEG outputs & workspace ──────────────────────────────────────────

export interface EegOutputFile {
  name: string;
  type: "html" | "image" | "json" | "data" | "other";
  size: number;
  modified: number;
}

export async function listEegOutputs() {
  const r = await fetch(`${base()}/eeg/outputs`);
  if (!r.ok) throw new Error("eeg outputs failed");
  return r.json() as Promise<{ files: EegOutputFile[] }>;
}

export function eegOutputUrl(filename: string): string {
  return `${base()}/eeg/outputs/${encodeURIComponent(filename)}`;
}

export async function openWorkspace() {
  const r = await fetch(`${base()}/workspace/open`, { method: "POST" });
  if (!r.ok) throw new Error("workspace open failed");
  return r.json() as Promise<{ status: string; path: string }>;
}

export async function postEegRunPython(script: string) {
  const r = await fetch(`${base()}/eeg/run-python`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ script }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{
    ok: boolean;
    exit_code: number;
    stdout: string;
    stderr: string;
    new_files: string[];
    message: string;
    error: string | null;
  }>;
}

export interface EegScriptTemplateRow {
  name: string;
  summary: string;
}

export async function getEegScriptTemplates() {
  const r = await fetch(`${base()}/eeg/script-templates`);
  if (!r.ok) throw new Error("script templates list failed");
  return r.json() as Promise<{ templates: EegScriptTemplateRow[] }>;
}

export async function getEegScriptTemplate(name: string) {
  const r = await fetch(`${base()}/eeg/script-templates/${encodeURIComponent(name)}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ name: string; content: string }>;
}

export interface EegJob {
  id: string;
  filename: string;
  status: "queued" | "running" | "complete" | "complete_with_warnings" | "error";
  progress: number;
  started: string;
  output_count?: number;
  error?: string | null;
  condition?: string;
  output_mode?: string;
  remontage_ref?: string;
}

export interface EegJobDetail extends EegJob {
  messages: string[];
  output_files: string[];
  metrics: Record<string, unknown>;
}

export interface EegProcessOptions {
  condition?: string;
  output_mode?: string;
  remontage_ref?: string;
}

export async function processEeg(file: File, opts: EegProcessOptions = {}) {
  const form = new FormData();
  form.append("file", file);
  if (opts.condition) form.append("condition", opts.condition);
  if (opts.output_mode) form.append("output_mode", opts.output_mode);
  if (opts.remontage_ref) form.append("remontage_ref", opts.remontage_ref);
  const r = await fetch(`${base()}/eeg/process`, { method: "POST", body: form });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ job_id: string; status: string; filename: string }>;
}

export async function listEegJobs() {
  const r = await fetch(`${base()}/eeg/jobs`);
  if (!r.ok) throw new Error("jobs list failed");
  return r.json() as Promise<{ jobs: EegJob[] }>;
}

export async function getEegJob(jobId: string) {
  const r = await fetch(`${base()}/eeg/jobs/${encodeURIComponent(jobId)}`);
  if (!r.ok) throw new Error("job status failed");
  return r.json() as Promise<EegJobDetail>;
}

export function eegJobFileUrl(jobId: string, filename: string): string {
  const encodedFilename = filename
    .split("/")
    .map(encodeURIComponent)
    .join("/");
  return `${base()}/eeg/jobs/${encodeURIComponent(jobId)}/files/${encodedFilename}`;
}

export async function deleteEegJob(jobId: string) {
  const r = await fetch(`${base()}/eeg/jobs/${encodeURIComponent(jobId)}/delete`, { method: "POST" });
  if (!r.ok) throw new Error("delete failed");
  return r.json() as Promise<{ status: string; id: string }>;
}

// ── File management ──────────────────────────────────────────────────

export interface UploadResult {
  filename: string;
  original_name: string;
  category: string;
  size: number;
  path: string;
  ok: boolean;
  error?: string;
  ingested_chunks?: number;
  ingest_error?: string;
}

export interface FileEntry {
  name: string;
  category: string;
  size: number;
  modified: number;
  path: string;
}

export async function uploadFiles(files: File[]) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const r = await fetch(`${base()}/files/upload`, { method: "POST", body: form });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ uploaded: UploadResult[] }>;
}

export async function listFiles(category = "all") {
  const r = await fetch(`${base()}/files?category=${encodeURIComponent(category)}`);
  if (!r.ok) throw new Error("file list failed");
  return r.json() as Promise<{ files: FileEntry[] }>;
}

export async function deleteFile(category: string, filename: string) {
  const r = await fetch(
    `${base()}/files/${encodeURIComponent(category)}/${encodeURIComponent(filename)}`,
    { method: "DELETE" },
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ status: string; filename: string }>;
}
