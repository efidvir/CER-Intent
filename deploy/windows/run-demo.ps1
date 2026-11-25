# Run the emulated flow natively on Windows (no Docker): two radios, the TeraFlowSDN stand-in,
# the twin and CER-Intent, each its own process. Sets up a virtual environment on first run.
#
#   powershell -ExecutionPolicy Bypass -File deploy\windows\run-demo.ps1 [-AutoApprove]
#
# The twin needs NS-3 for real runs; without it (Windows) it replays recorded runs, which never
# decide a verdict, so changes wait for a person unless auto-approval is told not to need the twin.
# For NS-3 on Windows use Docker Desktop:  docker compose -f compose.demo.yaml up --build
param([switch]$AutoApprove)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root

$twin = Join-Path (Split-Path -Parent $root) "tfs-ns3-digital-twin"
$fork = Join-Path (Split-Path -Parent $root) "teraflowsdn"
if (-not (Test-Path $twin) -or -not (Test-Path $fork)) {
  & (Join-Path $root "deploy\get-sources.ps1")
}

$venv = Join-Path $root ".venv"
$py = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $py)) {
  Write-Host "creating $venv"
  python -m venv $venv; if ($LASTEXITCODE) { throw "python -m venv failed (is Python 3.11+ on PATH?)" }
  & $py -m pip install --upgrade pip
  & $py -m pip install -r requirements.txt -r (Join-Path $twin "requirements.txt"); if ($LASTEXITCODE) { throw "pip install failed" }
  & $py -m pip install .\ceragon_tfs_adapter; if ($LASTEXITCODE) { throw "pip install of the adapter failed" }
}

$env:TWIN_SRC = $twin
$env:TFS_FORK_SRC = Join-Path $fork "src"
$env:PYTHON = $py
if ($AutoApprove) {
  $env:CER_IMF_AUTO = "1"
  Write-Host "auto-approval on; the twin replays recorded runs here, so the twin guardrail holds changes back"
  Write-Host "  (an admin can lift it in the studio: auto-approve chip, untick 'the twin's NS-3 run must pass')"
}
Write-Host "studio: http://localhost:5000/intent-studio.html"
& $py emulation\flow_stack.py up
