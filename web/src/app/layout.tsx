/*
 * @license GPL-3.0-or-later
 * Copyright (C) 2026 EEG Paradox Solutions LLM contributors
 *
 * This file is part of Paradox Solutions LLM. See LICENSE in the repository root.
 */

import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ThemeProvider } from "@/lib/ThemeContext";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "PARADOX // SOLUTIONS LLM",
  description: "Local AI orchestrator — Paradox Solutions LLM",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-[var(--bg-primary)] font-sans`}
        suppressHydrationWarning
      >
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
