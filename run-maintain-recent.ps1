$ErrorActionPreference = "Stop"

$projectRoot = "D:\AGENTES-IA"
$stateDir = Join-Path $projectRoot "state"
$logPath = Join-Path $stateDir "maintain-recent.log"
$exePath = "C:\Users\kalro\AppData\Local\Programs\Python\Python314\Scripts\gmail-agent.exe"

if (-not (Test-Path $stateDir)) {
    New-Item -ItemType Directory -Path $stateDir | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$timestamp] Starting maintain-recent" | Out-File -FilePath $logPath -Append -Encoding utf8

try {
    & $exePath maintain-recent --limit 300 --recent-days 60 --learning-days 14 2>&1 |
        Out-File -FilePath $logPath -Append -Encoding utf8

    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) {
        $exitCode = 0
    }
    "[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss")] Exit code: $exitCode" | Out-File -FilePath $logPath -Append -Encoding utf8
    exit $exitCode
}
catch {
    "[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss")] ERROR: $($_.Exception.Message)" | Out-File -FilePath $logPath -Append -Encoding utf8
    exit 1
}
