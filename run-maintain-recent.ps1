$ErrorActionPreference = "Stop"

$projectRoot = "D:\AGENTES-IA"
$stateDir = Join-Path $projectRoot "state"
$logPath = Join-Path $stateDir "maintain-recent.log"
$heartbeatPath = Join-Path $stateDir "maintain-recent-heartbeat.json"
$lockPath = Join-Path $stateDir "maintain-recent.lock"
$stdoutPath = Join-Path $stateDir "maintain-recent.stdout.log"
$stderrPath = Join-Path $stateDir "maintain-recent.stderr.log"
$pythonPath = "C:\Users\kalro\AppData\Local\Programs\Python\Python314\python.exe"
$args = @("-m", "gmail_agent.cli", "maintain-recent", "--limit", "300", "--recent-days", "60", "--learning-days", "14")
$timeoutSeconds = 1500
$staleLockMinutes = 120

if (-not (Test-Path $stateDir)) {
    New-Item -ItemType Directory -Path $stateDir | Out-Null
}

Set-Location $projectRoot

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$timestamp] $Message" | Out-File -FilePath $logPath -Append -Encoding utf8
}

function Write-Heartbeat {
    param(
        [string]$Status,
        [string]$Message,
        [int]$ExitCode = -1
    )
    $payload = @{
        timestamp = (Get-Date).ToString("s")
        status = $Status
        message = $Message
        exit_code = $ExitCode
    }
    $payload | ConvertTo-Json | Set-Content -Path $heartbeatPath -Encoding utf8
}

function Clear-Lock {
    if (Test-Path $lockPath) {
        Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
    }
}

try {
    if (Test-Path $lockPath) {
        $lockAge = (Get-Date) - (Get-Item $lockPath).LastWriteTime
        if ($lockAge.TotalMinutes -lt $staleLockMinutes) {
            Write-Log "Skipped maintain-recent because another run appears active."
            Write-Heartbeat -Status "skipped" -Message "Another run appears active." -ExitCode 0
            exit 0
        }

        Write-Log "Found stale lock older than $staleLockMinutes minute(s); clearing it."
        Clear-Lock
    }

    "running $(Get-Date -Format 's')" | Set-Content -Path $lockPath -Encoding utf8
    Write-Log "Starting maintain-recent"
    Write-Heartbeat -Status "running" -Message "Starting maintain-recent."

    if (Test-Path $stdoutPath) {
        Remove-Item -LiteralPath $stdoutPath -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $stderrPath) {
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
    }

    $process = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList $args `
        -WorkingDirectory $projectRoot `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru

    $null = $process.WaitForExit($timeoutSeconds * 1000)

    if (-not $process.HasExited) {
        Write-Log "maintain-recent exceeded timeout of $timeoutSeconds second(s); terminating process."
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        if (Test-Path $stdoutPath) {
            Get-Content $stdoutPath | Out-File -FilePath $logPath -Append -Encoding utf8
        }
        if (Test-Path $stderrPath) {
            Get-Content $stderrPath | Out-File -FilePath $logPath -Append -Encoding utf8
        }
        Write-Heartbeat -Status "timeout" -Message "Process exceeded timeout and was terminated." -ExitCode 124
        exit 124
    }

    if (Test-Path $stdoutPath) {
        Get-Content $stdoutPath | Out-File -FilePath $logPath -Append -Encoding utf8
    }
    if (Test-Path $stderrPath) {
        Get-Content $stderrPath | Out-File -FilePath $logPath -Append -Encoding utf8
    }

    $exitCode = $process.ExitCode
    Write-Log "Exit code: $exitCode"
    Write-Heartbeat -Status "completed" -Message "maintain-recent completed." -ExitCode $exitCode
    exit $exitCode
}
catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    Write-Heartbeat -Status "error" -Message $_.Exception.Message -ExitCode 1
    exit 1
}
finally {
    Clear-Lock
}
