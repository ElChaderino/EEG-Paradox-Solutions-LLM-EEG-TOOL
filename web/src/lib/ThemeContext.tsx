"use client";

/*
 * @license GPL-3.0-or-later
 * Copyright (C) 2026 EEG Paradox Solutions LLM contributors
 *
 * This file is part of Paradox Solutions LLM. See LICENSE in the repository root.
 */

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

type HudColor = "cyan" | "matrix";

/** Presets applied to --paradox-font-scale (multiplier on 16px root). */
export const FONT_SCALE_PRESETS = [0.875, 1, 1.125, 1.25] as const;
export type FontScalePreset = (typeof FONT_SCALE_PRESETS)[number];

export const FONT_SCALE_LABELS: Record<FontScalePreset, string> = {
  0.875: "S",
  1: "M",
  1.125: "L",
  1.25: "XL",
};

const STORAGE_KEY = "paradox-hud-color";
const LEGACY_KEY = "anton-hud-color";
const FONT_STORAGE_KEY = "paradox-font-scale";

const ThemeContext = createContext<{
  hudColor: HudColor;
  cycleHudColor: () => void;
  fontScale: FontScalePreset;
  setFontScale: (s: FontScalePreset) => void;
  cycleFontScale: () => void;
}>({
  hudColor: "cyan",
  cycleHudColor: () => {},
  fontScale: 1,
  setFontScale: () => {},
  cycleFontScale: () => {},
});

export type { HudColor };

function isPreset(n: number): n is FontScalePreset {
  return (FONT_SCALE_PRESETS as readonly number[]).includes(n);
}

function applyFontScaleToDom(scale: FontScalePreset) {
  if (typeof document === "undefined") return;
  document.documentElement.style.setProperty("--paradox-font-scale", String(scale));
  document.documentElement.setAttribute("data-font-scale", String(scale));
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [hudColor, setHudColor] = useState<HudColor>("cyan");
  const [fontScale, setFontScaleState] = useState<FontScalePreset>(1);

  useEffect(() => {
    let saved = localStorage.getItem(STORAGE_KEY) as HudColor | null;
    if (saved !== "cyan" && saved !== "matrix") {
      const legacy = localStorage.getItem(LEGACY_KEY) as HudColor | null;
      if (legacy === "cyan" || legacy === "matrix") {
        saved = legacy;
        localStorage.setItem(STORAGE_KEY, legacy);
      }
    }
    if (saved === "cyan" || saved === "matrix") {
      setHudColor(saved);
      document.documentElement.setAttribute("data-hud", saved);
    }

    const rawFs = localStorage.getItem(FONT_STORAGE_KEY);
    const parsed = rawFs ? parseFloat(rawFs) : 1;
    const fs: FontScalePreset = isPreset(parsed) ? parsed : 1;
    setFontScaleState(fs);
    applyFontScaleToDom(fs);
  }, []);

  const cycleHudColor = () => {
    const next = hudColor === "cyan" ? "matrix" : "cyan";
    setHudColor(next);
    localStorage.setItem(STORAGE_KEY, next);
    document.documentElement.setAttribute("data-hud", next);
  };

  const setFontScale = useCallback((s: FontScalePreset) => {
    setFontScaleState(s);
    localStorage.setItem(FONT_STORAGE_KEY, String(s));
    applyFontScaleToDom(s);
  }, []);

  const cycleFontScale = useCallback(() => {
    const i = FONT_SCALE_PRESETS.indexOf(fontScale);
    const next = FONT_SCALE_PRESETS[(i + 1) % FONT_SCALE_PRESETS.length];
    setFontScale(next);
  }, [fontScale, setFontScale]);

  return (
    <ThemeContext.Provider
      value={{ hudColor, cycleHudColor, fontScale, setFontScale, cycleFontScale }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
