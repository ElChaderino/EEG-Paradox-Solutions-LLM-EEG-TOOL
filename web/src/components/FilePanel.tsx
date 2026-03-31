"use client";

/*
 * @license GPL-3.0-or-later
 * Copyright (C) 2026 EEG Paradox Solutions LLM contributors
 *
 * This file is part of Paradox Solutions LLM. See LICENSE in the repository root.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  deleteFile,
  type FileEntry,
  listFiles,
  openWorkspace,
  type UploadResult,
  uploadFiles,
} from "@/lib/api";

const CATEGORY_LABELS: Record<string, string> = {
  eeg: "EEG Recordings",
  document: "Documents",
  general: "General",
};

const CATEGORY_COLORS: Record<string, string> = {
  eeg: "text-violet-400",
  document: "text-cyan-400",
  general: "text-amber-400",
};

function fmtSize(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

export default function FilePanel() {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadResults, setUploadResults] = useState<UploadResult[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await listFiles("all");
      setFiles(r.files);
    } catch {
      /* backend may not be ready */
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), 30000);
    return () => clearInterval(id);
  }, [refresh]);

  async function handleUpload(picked: FileList | File[]) {
    const arr = Array.from(picked);
    if (arr.length === 0) return;
    setUploading(true);
    setError("");
    setUploadResults([]);
    try {
      const res = await uploadFiles(arr);
      setUploadResults(res.uploaded);
      void refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) void handleUpload(e.dataTransfer.files);
  }

  async function handleDelete(cat: string, name: string) {
    try {
      await deleteFile(cat, name);
      void refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const grouped = files.reduce<Record<string, FileEntry[]>>((acc, f) => {
    (acc[f.category] ??= []).push(f);
    return acc;
  }, {});

  return (
    <div className="rounded-lg border border-cyan-900/40 bg-[var(--bg-tertiary)] p-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-[0.625rem] font-semibold uppercase tracking-widest text-cyan-600">
          Files
        </h2>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={() => void refresh()}
            className="rounded border border-cyan-800/50 px-1.5 py-0.5 text-[0.5625rem] text-cyan-500 hover:bg-cyan-950/40"
            title="Refresh"
          >
            ↻
          </button>
          <button
            type="button"
            onClick={() => void openWorkspace().catch(() => {})}
            className="rounded border border-cyan-800/50 px-1.5 py-0.5 text-[0.5625rem] text-cyan-500 hover:bg-cyan-950/40"
            title="Open workspace folder"
          >
            📂
          </button>
        </div>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`mb-2 flex cursor-pointer flex-col items-center justify-center rounded border-2 border-dashed px-3 py-4 text-center transition-colors ${
          dragOver
            ? "border-cyan-400 bg-cyan-950/40"
            : "border-cyan-800/50 bg-black/20 hover:border-cyan-600/60 hover:bg-cyan-950/20"
        }`}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="mb-1 h-5 w-5 text-cyan-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.338-2.32 3.75 3.75 0 013.572 5.345A3.75 3.75 0 0118 19.5H6.75z"
          />
        </svg>
        {uploading ? (
          <span className="text-[0.625rem] text-cyan-400 animate-pulse">
            Uploading...
          </span>
        ) : (
          <>
            <span className="text-[0.625rem] text-cyan-500">
              Drop files or click to browse
            </span>
            <span className="mt-0.5 text-[0.5625rem] text-cyan-700">
              EDF/BDF, PDF, TXT, MD, CSV, JSON
            </span>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          accept=".edf,.bdf,.set,.fif,.vhdr,.cnt,.pdf,.txt,.md,.markdown,.csv,.json,.yaml,.yml,.docx"
          onChange={(e) => {
            if (e.target.files) void handleUpload(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {/* Upload results */}
      {uploadResults.length > 0 && (
        <div className="mb-2 space-y-1">
          {uploadResults.map((r, i) => (
            <div
              key={i}
              className={`rounded px-2 py-1 text-[0.625rem] font-mono ${
                r.ok
                  ? "bg-emerald-950/30 text-emerald-400"
                  : "bg-red-950/30 text-red-400"
              }`}
            >
              {r.ok ? (
                <>
                  {r.original_name}{" "}
                  <span className="text-cyan-600">
                    [{r.category}]
                    {r.ingested_chunks != null && ` ${r.ingested_chunks} chunks`}
                  </span>
                </>
              ) : (
                <>
                  {r.filename}: {r.error}
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {error && (
        <p className="mb-2 text-[0.625rem] font-mono text-red-400">{error}</p>
      )}

      {/* File list */}
      <div className="styled-scrollbar max-h-56 space-y-2 overflow-y-auto">
        {Object.keys(grouped).length === 0 && (
          <p className="text-[0.625rem] text-cyan-700">No files uploaded yet</p>
        )}
        {["eeg", "document", "general"].map((cat) => {
          const list = grouped[cat];
          if (!list || list.length === 0) return null;
          return (
            <div key={cat}>
              <p
                className={`text-[0.5625rem] font-semibold uppercase tracking-widest ${
                  CATEGORY_COLORS[cat] ?? "text-cyan-500"
                }`}
              >
                {CATEGORY_LABELS[cat] ?? cat} ({list.length})
              </p>
              <div className="mt-0.5 space-y-0.5">
                {list.map((f) => (
                  <div
                    key={f.path}
                    className="group flex items-center justify-between rounded px-1.5 py-0.5 hover:bg-cyan-950/30"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-mono text-[0.625rem] text-cyan-200">
                        {f.name}
                      </p>
                      <p className="text-[0.5625rem] text-cyan-700">
                        {fmtSize(f.size)}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleDelete(f.category, f.name);
                      }}
                      className="ml-1 hidden rounded p-0.5 text-red-500/60 hover:bg-red-950/40 hover:text-red-400 group-hover:block"
                      title="Delete"
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-3 w-3"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2}
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M6 18L18 6M6 6l12 12"
                        />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
