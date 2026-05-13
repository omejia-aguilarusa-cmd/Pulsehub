param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if ($Clean) {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "$RepoRoot\build"
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "$RepoRoot\dist"
}

uv run pyinstaller `
    --noconfirm `
    --clean `
    --name TakeoffPro `
    --onefile `
    --windowed `
    --specpath build `
    --workpath build `
    --distpath dist `
    --collect-all pymupdf `
    --collect-data reportlab `
    --hidden-import PyQt6.sip `
    src\takeoff_pro\__main__.py
