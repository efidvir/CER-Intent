# Clone (or update) the twin and the TeraFlowSDN fork next to this repository, at the refs in
# deploy\sources.env (Windows). Only the fork's parts the demo uses are checked out (sparse).
#
#   powershell -ExecutionPolicy Bypass -File deploy\get-sources.ps1 [-Dest C:\src] [-Update]
#
# An existing checkout is left as it is (your own working clone, say) unless -Update is given.
param([string]$Dest = "", [switch]$Update)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
if (-not $Dest) { $Dest = Split-Path -Parent $root }
$cfg = @{}
Get-Content (Join-Path $here "sources.env") | Where-Object { $_ -match '^\s*[A-Z_]+=' } | ForEach-Object {
  $k, $v = $_ -split '=', 2; $cfg[$k.Trim()] = $v.Trim()
}

function Fetch([string]$repo, [string]$ref, [string]$dir, [string[]]$sparse) {
  if ((Test-Path (Join-Path $dir ".git")) -and -not $Update) {
    Write-Host ("using $dir as it is (" + (git -C $dir rev-parse --abbrev-ref HEAD) + "); -Update moves it to $ref")
  } elseif (Test-Path (Join-Path $dir ".git")) {
    Write-Host "updating $dir to $ref"
    git -C $dir fetch --depth 1 origin $ref; if ($LASTEXITCODE) { throw "git fetch failed" }
    git -C $dir checkout -q --detach FETCH_HEAD; if ($LASTEXITCODE) { throw "git checkout failed" }
  } else {
    Write-Host "cloning $repo ($ref) into $dir"
    if ($sparse) {
      git clone -q --depth 1 --filter=blob:none --sparse --branch $ref $repo $dir; if ($LASTEXITCODE) { throw "git clone failed" }
      git -C $dir sparse-checkout set --no-cone @sparse; if ($LASTEXITCODE) { throw "sparse checkout failed" }
    } else {
      git clone -q --depth 1 --branch $ref $repo $dir; if ($LASTEXITCODE) { throw "git clone failed" }
    }
  }
  Write-Host ("  $dir at " + (git -C $dir rev-parse --short HEAD))
}

Fetch $cfg.TWIN_REPO $cfg.TWIN_REF (Join-Path $Dest "tfs-ns3-digital-twin") @()
Fetch $cfg.TFS_FORK_REPO $cfg.TFS_FORK_REF (Join-Path $Dest "teraflowsdn") @(
  "/src/common/", "/src/device/__init__.py", "/src/device/service/__init__.py", "/src/device/service/driver_api/",
  "/src/device/service/drivers/ceragon/", "/src/service/__init__.py", "/src/service/service/__init__.py",
  "/src/service/service/service_handlers/ceragon_transport/")
