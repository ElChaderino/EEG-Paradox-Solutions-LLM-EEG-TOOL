# EEG norms add-on (Cuban databases)

The main Paradox Solutions LLM installer stays smaller by **not** bundling full Cuban normative file trees. Optional **EEG Norms Add-on** installs those files so the app can:

- Load Cuban 2nd-wave CSV norms into `NormManager` (richer `cuban2ndwave` lookups)
- Resolve `visualization_config` Cuban paths to real directories
- Add per-channel keys like `Alpha_z_normative` during EEG visualization runs (`run_visualizations.py`)

## Install location

Default (Windows): `%ProgramData%\ParadoxSolutions\EEGNorms\`

After installation you should see `manifest.json` and `data\cuban_databases\` under that folder.

## Override path (developers / IT)

Set environment variable **`EEG_NORMS_DLC_ROOT`** to the folder that contains `data\cuban_databases` (same layout as `addons/eeg-norms-dlc/payload` in the repo).

## Check from the app

- **Sidebar → System**: “EEG norms add-on” shows installed / not installed (from `/health`).
- API: `GET /health` → `eeg_norms_addon` object with `installed`, `root`, `version`, etc.

## Build the add-on installer (vendors)

From the Super Bot repo root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_dlc_eeg_norms.ps1
```

Requires [NSIS](https://nsis.sourceforge.io/). Output: `dist/Paradox_EEG_Norms_Addon_Setup.exe`.

## Troubleshooting

| Symptom | What to check |
|--------|----------------|
| Add-on shows “Not installed” | Run the add-on setup as admin; confirm `ProgramData\ParadoxSolutions\EEGNorms\data\cuban_databases` exists |
| Z-scores still sparse | CSV paths inside `cuban_2nd_wave_database` must match Decoder layout (`eyes_closed_normative_database.csv` or `qeeg_analysis_tables\normative_database.csv`) |
| Wrong folder detected | Set `EEG_NORMS_DLC_ROOT` explicitly |

## Font size (UI)

Use the **S / M / L / XL** control next to **HUD** in the header to scale interface text (stored in browser `localStorage`).
