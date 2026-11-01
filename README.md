# Frame Studio

A native Tauri desktop app with a Rust image-processing backend for previewing and batch-exporting photos through transparent image frames. The interface follows a dark, professional creative-suite layout: an app bar, a tool rail, a zoomable canvas, collapsible Properties and Photos panels, and a status bar with export progress. Shortcuts: Ctrl+O open frame, Ctrl+I add photos, Ctrl+E export, Ctrl+= / Ctrl+- zoom, Ctrl+0 fit, Ctrl+1 actual size, arrow keys to step through photos, Delete to remove the selected photo. Previews preserve the selected frame's aspect ratio.

## Run

On Windows, double-click `run.bat`, or start it from this folder:

```powershell
cargo run --release --target-dir target-tauri
```

The first launch downloads Rust dependencies and compiles the application. The app uses the Windows WebView2 runtime. You can also build a standalone executable with:

```powershell
cargo build --release
```

The launcher builds the updated app at `target-tauri\release\frame-studio-dock.exe`, separately from the earlier `frame-studio.exe` so an already-open older version won't lock the updated executable. The preview is constrained to the selected frame's aspect ratio and fits the available canvas; the preview output is normalized to the frame dimensions for every fit mode.

## Releases

Download the latest installer from the [Releases page](https://github.com/omaiow/Frame-adder/releases).

To publish a new release, bump `version` in `Cargo.toml` and `tauri.conf.json`, commit, then push a matching tag:

```powershell
git tag v1.0.1
git push origin v1.0.1
```

GitHub Actions (`.github/workflows/release.yml`) builds the NSIS installer, MSI, and a portable `.exe`, and attaches them to a release for that tag.

## Workflow

1. Choose a transparent frame image. The transparent opening is detected automatically; enable manual opening controls to adjust it.
2. Add photos, choose a folder, or drag images into the window.
3. Adjust the fit mode, layer order, output format, quality, filename pattern, and destination.
4. Preview the composition and select **Export photos**.

The app supports PNG, JPEG, WEBP, BMP, and TIFF input. PNG, JPEG, WEBP, and original-format export are available; formats without a matching output encoder are exported as PNG when **Original** is selected.
