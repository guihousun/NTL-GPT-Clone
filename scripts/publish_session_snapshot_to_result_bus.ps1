param(
    [string]$ResultRepo = "E:\codex-result-bus",
    [string]$SourceWorkspace = "E:\NTL-GPT-Clone",
    [string]$SummaryTitle = "Codex Session Snapshot",
    [string]$SummaryBody = "",
    [string]$RemoteUrl = "",
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ResultRepo)) {
    New-Item -ItemType Directory -Path $ResultRepo | Out-Null
}

if (-not (Test-Path (Join-Path $ResultRepo ".git"))) {
    git -C $ResultRepo init -b main | Out-Null
}

$recordsDir = Join-Path $ResultRepo "records"
if (-not (Test-Path $recordsDir)) {
    New-Item -ItemType Directory -Path $recordsDir | Out-Null
}

$tsFile = Get-Date -Format "yyyy-MM-dd_HHmmss"
$tsText = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$recordPath = Join-Path $recordsDir "${tsFile}_session.md"

$defaultBody = @"
# $SummaryTitle

- timestamp_local: $tsText
- source_workspace: $SourceWorkspace

## Summary
$SummaryBody
"@

Set-Content -Path $recordPath -Encoding UTF8 -Value $defaultBody

if (-not (Test-Path (Join-Path $ResultRepo "README.md"))) {
    Set-Content -Path (Join-Path $ResultRepo "README.md") -Encoding UTF8 -Value @"
# Codex Result Bus

This repository stores asynchronous session snapshots from Codex.
"@
}

if ($RemoteUrl) {
    $hasOrigin = (git -C $ResultRepo remote) -contains "origin"
    if (-not $hasOrigin) {
        git -C $ResultRepo remote add origin $RemoteUrl
    }
}

git -C $ResultRepo add .
$status = (git -C $ResultRepo status --porcelain).Trim()
if ($status) {
    git -C $ResultRepo commit -m "session snapshot: $tsFile" | Out-Null
}

$commit = (git -C $ResultRepo rev-parse --short HEAD).Trim()
$pushMessage = "push_skipped"

if (-not $NoPush) {
    $hasOrigin = (git -C $ResultRepo remote) -contains "origin"
    if ($hasOrigin) {
        try {
            git -C $ResultRepo push origin main | Out-Null
            $pushMessage = "push_ok"
        } catch {
            $pushMessage = "push_failed: $($_.Exception.Message)"
        }
    } else {
        $pushMessage = "push_failed: remote origin not configured"
    }
}

Write-Output "record_path=$recordPath"
Write-Output "commit=$commit"
Write-Output "push_status=$pushMessage"

