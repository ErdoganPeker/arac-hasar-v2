# scripts/prepare-ml-shim.ps1
# -----------------------------------------------------------
# Copies ML inference modules that the backend image needs to
# import at runtime into services/backend/ so that
# `docker build services/backend` includes them.
#
# Run before building the backend Docker image.
# -----------------------------------------------------------
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Src  = Join-Path $Root "services\ml"
$Dst  = Join-Path $Root "services\backend"

foreach ($f in @("pipeline.py", "cost_engine.py", "severity_classifier.py", "output_formatter.py", "parts.yaml")) {
    $srcFile = Join-Path $Src $f
    if (-not (Test-Path $srcFile)) {
        Write-Error "Missing $srcFile"
        exit 1
    }
    Copy-Item -Force $srcFile (Join-Path $Dst $f)
    Write-Host "  copied: $f"
}

Write-Host "ML shim ready in $Dst"
