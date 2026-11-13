# ANVESHAN — Offline Analyst Workstation

ANVESHAN is the local-first prototype for satellite-imagery analysis. The current delivery direction is a Windows desktop application: a native ANVESHAN window starts the local FastAPI service internally, uses a local per-user data directory, and does not require the operator to open a terminal or type a localhost URL.

## What the prototype does

- Imports a local imagery folder and preserves source metadata, hashes and provenance.
- Builds local visual / semantic indexes from staged offline model weights.
- Supports text search, image-to-image search, AOI/date/sensor filters and similar-site clustering.
- Compares same-location scenes across dates with side-by-side, overlay, swipe, blink, timeline and measurement tools.
- Flags quality and false-alarm confounders such as cloud, shadow, season and misregistration instead of blindly claiming physical change.
- Records analyst review decisions and exports provenance evidence.

## Development run

For source-tree development, run:

```powershell
.\run_offline.ps1
```

Then open the local URL printed by the script. This is a development workflow only.

## Desktop run

The packaged app runs through `desktop.py` with WebView2 and an embedded local server. It stores user data under `%LOCALAPPDATA%\ANVESHAN\datasets` unless `--data` or `ANVESHAN_DATA_DIR` is provided.

To run the installed app against the dev archive:

```powershell
"C:\Program Files\ANVESHAN\runtime\ANVESHAN.exe" "C:\Program Files\ANVESHAN\desktop.py" --data "<repo>\datasets"
```

## Build installer

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

The build script may use the internet once to stage the embeddable Python runtime, WebView2 offline installer and icon tools. The delivered installer is intended to run offline.

## Tests

Use a writable pytest temp directory on Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp="$env:TEMP\anveshan-pytest"
```

If that temp path is locked by Windows, use a fresh folder inside the repo, for example:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=".pytest-run-local"
```

## Important limits

No claim should be presented without the dataset and hardware it was measured on. Text/image retrieval scores, change metrics, build time, storage footprint and latency must come from a recorded run. Large imagery archives and local generated previews are intentionally not committed to git.
