# Windows installers (optional)

Place release artifacts here so they are tracked in git and available from the repository.

**Suggested files**

- `Paradox Solutions LLM_*_x64-setup.exe` — NSIS installer from `src-tauri/target/release/bundle/nsis/` after `scripts\build_release.ps1`
- Or copy the MSI from `bundle/msi/` if you prefer that format

**GitHub limits**

- Plain Git rejects files **> 100 MB**. The NSIS `.exe` and MSI here are tracked with **[Git LFS](https://git-lfs.github.com/)** (see root `.gitattributes`: `installers/*.exe`, `installers/*.msi`).
- Cloners need `git lfs install` (once per machine) so `git clone` pulls the real binaries, not pointer files.

**Current bundles (v0.3.2, x64)**

- `Paradox Solutions LLM_0.3.2_x64-setup.exe` — NSIS (copied from `src-tauri/target/release/bundle/nsis/`)
- `Paradox Solutions LLM_0.3.2_x64_en-US.msi` — WiX MSI (from `bundle/msi/`)

Rebuild and replace these filenames when you bump `VERSION` / run `scripts\build_release.ps1`, then commit again.
