# Local portable Windows build. PowerShell 5.1 and PowerShell 7.
# Not a CI script. Run from the repository root:
#   .\build.ps1
# Writes build\cli-avatars.exe and build\cli-avatars-emit.exe, then
# removes the PyInstaller work tree and dist folder.

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Invoke-Checked {
    param([Parameter(Mandatory = $true)][scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$Venv = Join-Path $Root ".venv-build"
$Python = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        & py -3 -m venv $Venv
    } else {
        & python -m venv $Venv
    }
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Invoke-Checked { & $Python -m pip install --upgrade pip }
Invoke-Checked { & $Python -m pip install -r (Join-Path $Root "requirements-build.txt") }

$BuildDir = Join-Path $Root "build"
$Work = Join-Path $BuildDir "_work"
$Dist = Join-Path $Root "dist"
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

Invoke-Checked {
    & $Python -m PyInstaller --noconfirm --clean `
        --workpath $Work `
        --distpath $Dist `
        (Join-Path $Root "cli-avatars.spec")
}

Copy-Item -LiteralPath (Join-Path $Dist "cli-avatars.exe") -Destination (Join-Path $BuildDir "cli-avatars.exe") -Force
Copy-Item -LiteralPath (Join-Path $Dist "cli-avatars-emit.exe") -Destination (Join-Path $BuildDir "cli-avatars-emit.exe") -Force

if (Test-Path -LiteralPath $Work) {
    Remove-Item -LiteralPath $Work -Recurse -Force
}
if (Test-Path -LiteralPath $Dist) {
    Remove-Item -LiteralPath $Dist -Recurse -Force
}

Get-ChildItem -LiteralPath $Root -Filter "warn-*.txt" -File -ErrorAction SilentlyContinue |
    Remove-Item -Force

& (Join-Path $BuildDir "cli-avatars.exe") --selftest
exit $LASTEXITCODE
