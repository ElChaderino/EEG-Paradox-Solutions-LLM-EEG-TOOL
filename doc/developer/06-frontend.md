# Developer Guide 06 — Frontend (Web Console)

## Objective

Describe how `web/` couples to the API and how to extend the UI safely.

## Stack

- Next.js 16 (App Router)
- React 19
- Tailwind CSS v4 (`@import "tailwindcss"` in `globals.css`)
- Geist fonts via `next/font/google`

## Styling lineage

Visual variables and HUD toggle behavior are aligned with the Paradox Solutions HUD lineage dark console pattern: CSS custom properties under `:root`, optional matrix remap via `[data-hud="matrix"]`.

## API usage

**Module:** `web/src/lib/api.ts`

All fetches use `NEXT_PUBLIC_HEX_API` defaulting to `http://127.0.0.1:8765`.

| Function | Route |
|----------|--------|
| `postAgent` | `POST /agent` — non-OK responses throw with body text; **504** when Ollama read-timeout. |
| `getHealth` | `GET /health` — includes `eeg_subprocess` for EEG Data panel / operators. |
| `getStats` | `GET /system/stats` |
| `getFocus` | `GET /focus` |
| `postMemoryQuery` | `POST /memory/query` |

## Client component boundary

`web/src/app/page.tsx` is a client component (`"use client"`). Server components are minimal (`layout.tsx`).

## Extending the UI

- **New panel:** Add a section in `page.tsx` or extract a component under `web/src/components/` (create directory if needed).
- **New API call:** Add a typed function in `api.ts`; ensure CORS on server includes dev origin.
- **Environment:** Document new `NEXT_PUBLIC_*` variables in `reference/configuration.md`.

## Build

```powershell
cd web
npm run build
```

**Shall** run build before tagging a release that includes UI changes.

## Related

- `user/04-web-console.md` — operator view.
- `reference/rest-api.md` — server contract.
