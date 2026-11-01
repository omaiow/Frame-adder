@echo off
title Frame Studio — Tauri
cd /d "%~dp0"

echo Launching Frame Studio...
cargo run --release --target-dir target-tauri
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Frame Studio failed to start. Check that Rust and WebView2 are installed.
    echo Install Rust from https://rustup.rs if needed.
    pause
)
