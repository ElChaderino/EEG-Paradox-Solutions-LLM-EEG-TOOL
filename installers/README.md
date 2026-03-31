# Windows installers (optional)

Place release artifacts here so they are tracked in git and available from the repository.

**Suggested files**

- `Paradox Solutions LLM_*_x64-setup.exe` — NSIS installer from `src-tauri/target/release/bundle/nsis/` after `scripts\build_release.ps1`
- Or copy the MSI from `bundle/msi/` if you prefer that format

**GitHub limits**

- Files over **100 MB** are rejected. Between **50–100 MB** you may see a warning.
- For very large binaries, use **[Git LFS](https://git-lfs.github.com/)** (e.g. `git lfs track "installers/*.exe"` before adding the file).

After copying an installer into this folder, run `git add installers/` and commit from the repo root.
