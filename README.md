# Gitoder

**Git, minus the headaches.** A warm, crafted Windows desktop app that does four
GitHub things without the terminal, the website maze, or the re-verification dance:

| | |
|---|---|
| **Create Repo** | new repository + push your project folder, verified |
| **Delete Repo** | list and delete, red Confirm — no re-verification |
| **Update Repo** | replace a repo's files completely in one atomic commit |
| **Download Repo** | paste any repo link, get a `.zip` in your Downloads folder |

Built with Python + PySide6. Uses the GitHub REST API only — **no git installation
required**. Your token lives in **Windows Credential Manager**, never in a file or log.

---

## Run from source

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

(Any Python 3.11+ works; fonts and icons are bundled in `gitoder/assets/`.)

## Get a token (one time)

1. In Gitoder, click **Create my token** — it opens GitHub with the right
   permissions pre-checked (`repo`, `delete_repo`), or go to
   <https://github.com/settings/tokens/new?scopes=repo,delete_repo&description=Gitoder>
2. Scroll down, click **Generate token**.
3. Copy it, paste into Gitoder, click **Connect**.

Use a **classic** token: fine-grained tokens cannot delete repositories.

## Build the .exe

```bat
build_exe.bat
```

or manually: `.venv\Scripts\pyinstaller.exe --noconfirm gitoder.spec`
→ `dist\Gitoder.exe` (single windowed executable, fonts and icon included).

## Project layout

```
main.py                 entry point (fonts, single-instance, crash guard)
gitoder/
  core/                 GitHub API, push engine, downloader (no Qt here)
  ui/                   E-Sense theme, painted widgets, screens (no HTTP here)
  utils/                Downloads-folder resolution, rotating redacted logs
  assets/fonts/         Syne + DM Sans (OFL) — loaded at startup
  assets/icons/         generated app .ico
logs: %LOCALAPPDATA%\Gitoder\logs\gitoder.log   (tokens are never logged)
```

## Notes

- Default branch is your repository's real default (usually `main`); Gitoder never
  assumes.
- Pushes are **verified** after upload — success is only shown when GitHub confirms
  every file.
- Downloads go to your **actual** Downloads folder (Known Folder API), never
  overwriting: `repo.zip`, `repo (1).zip`, …
