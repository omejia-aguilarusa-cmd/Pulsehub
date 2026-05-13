param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if ($Clean) {
    foreach ($Path in @("$RepoRoot\build", "$RepoRoot\dist")) {
        $ResolvedParent = Resolve-Path -LiteralPath (Split-Path -Parent $Path)
        if (-not $Path.StartsWith($ResolvedParent.Path, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean unexpected path: $Path"
        }
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

uv run pyinstaller --noconfirm --clean .\TakeoffPro.spec

if (-not (Test-Path -LiteralPath "$RepoRoot\dist\TakeoffPro.exe")) {
    throw "PyInstaller did not create dist\TakeoffPro.exe"
}
