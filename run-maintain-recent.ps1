$ErrorActionPreference = "Stop"
if ($null -ne (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue)) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$projectRoot = "D:\AGENTES-IA"
$pythonModuleRoot = Join-Path $projectRoot "python"
$stateDir = Join-Path $projectRoot "state"
$logPath = Join-Path $stateDir "maintain-recent.log"
$heartbeatPath = Join-Path $stateDir "maintain-recent-heartbeat.json"
$lockPath = Join-Path $stateDir "maintain-recent.lock"
$stdoutPath = Join-Path $stateDir "maintain-recent.stdout.log"
$stderrPath = Join-Path $stateDir "maintain-recent.stderr.log"
$pythonCandidates = @(
    "C:\Python313\python.exe",
    "C:\Users\kalro\AppData\Local\Programs\Python\Python314\python.exe",
    "C:\Users\kalro\AppData\Local\Programs\Python\Python313\python.exe",
    "C:\Users\kalro\AppData\Local\Programs\Python\Python312\python.exe",
    (Join-Path $projectRoot ".venv\Scripts\python.exe")
)
$pythonArgs = @("-u", "-m", "gmail_agent.cli", "maintain-recent", "--limit", "300", "--recent-days", "60", "--learning-days", "14")
$timeoutSeconds = 1500
$staleLockMinutes = 120

if (-not (Test-Path $stateDir)) {
    New-Item -ItemType Directory -Path $stateDir | Out-Null
}

Set-Location $projectRoot

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] $Message"
    $line | Out-File -FilePath $logPath -Append -Encoding utf8
    Write-Host $line
}

function Write-Heartbeat {
    param(
        [string]$Status,
        [string]$Message,
        [int]$ExitCode = -1
    )
    $payload = @{
        timestamp = (Get-Date).ToString("s")
        status    = $Status
        message   = $Message
        exit_code = $ExitCode
    }
    $payload | ConvertTo-Json | Set-Content -Path $heartbeatPath -Encoding utf8
}

function Clear-Lock {
    if (Test-Path $lockPath) {
        Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
    }
}

function Resolve-PythonPath {
    foreach ($candidate in $pythonCandidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand -and $pythonCommand.Source) {
        return $pythonCommand.Source
    }

    return $null
}

function Append-FileToLog {
    param([string]$FilePath, [string]$Label)
    if (Test-Path $FilePath) {
        $content = Get-Content $FilePath -Raw -Encoding utf8
        if ($content -and $content.Trim().Length -gt 0) {
            Write-Log "=== $Label ==="
            $content | Out-File -FilePath $logPath -Append -Encoding utf8
        }
    }
}

function Get-FileContentSafe {
    param([string]$FilePath)
    if (Test-Path $FilePath) {
        return (Get-Content $FilePath -Raw -Encoding utf8)
    }
    return ""
}

try {
    # --- Verificar lock ---
    if (Test-Path $lockPath) {
        $lockAge = (Get-Date) - (Get-Item $lockPath).LastWriteTime
        if ($lockAge.TotalMinutes -lt $staleLockMinutes) {
            Write-Log "Skipped maintain-recent porque outra execucao parece estar ativa (lock com $([int]$lockAge.TotalMinutes) min)."
            Write-Heartbeat -Status "skipped" -Message "Another run appears active." -ExitCode 0
            exit 0
        }
        Write-Log "Lock obsoleto encontrado ($([int]$lockAge.TotalMinutes) min); limpando."
        Clear-Lock
    }

    # --- Criar lock ---
    "running $(Get-Date -Format 's')" | Set-Content -Path $lockPath -Encoding utf8
    Write-Log "Iniciando maintain-recent"
    Write-Heartbeat -Status "running" -Message "Starting maintain-recent."

    # --- Reiniciar os arquivos desta execução para evitar mistura com erros antigos ---
    Set-Content -Path $stdoutPath -Value "" -Encoding utf8
    Set-Content -Path $stderrPath -Value "" -Encoding utf8

    # --- Verificar que o Python existe ---
    $pythonPath = Resolve-PythonPath
    if (-not $pythonPath) {
        Write-Log "ERRO: Python nao encontrado. Caminhos testados: $($pythonCandidates -join '; ')"
        Write-Heartbeat -Status "error" -Message "Python not found in expected locations." -ExitCode 1
        exit 1
    }

    Write-Log "Python: $pythonPath"
    Write-Log "Args: $($pythonArgs -join ' ')"

    # Garantir que o pacote local python/gmail_agent seja resolvido
    $env:PYTHONPATH = $pythonModuleRoot
    $env:GMAIL_AGENT_INTERACTIVE_REAUTH = "1"
    Write-Log "PYTHONPATH: $env:PYTHONPATH"

    # --- Executar processo síncrono com Start-Process; evita Start-Job e erros nativos do PowerShell ---
    Write-Log "Executando processo diretamente via PowerShell."
    Write-Heartbeat -Status "running" -Message "Process started."

    $proc = Start-Process -FilePath $pythonPath `
        -ArgumentList $pythonArgs `
        -WorkingDirectory $projectRoot `
        -NoNewWindow `
        -PassThru `
        -Wait `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath

    $stdoutContent = Get-FileContentSafe -FilePath $stdoutPath
    $stderrContent = Get-FileContentSafe -FilePath $stderrPath

    Append-FileToLog -FilePath $stdoutPath -Label "STDOUT"
    Append-FileToLog -FilePath $stderrPath -Label "STDERR"

    $exitCode = $proc.ExitCode
    if ($null -eq $exitCode) {
        $exitCode = 1
    }

    Write-Log "Exit code: $exitCode"

    $combinedOutput = "$stdoutContent`n$stderrContent"

    if ($exitCode -ne 0) {
        if ($combinedOutput -match "invalid_grant" -or $combinedOutput -match "Token OAuth inv.+ revogado") {
            Write-Heartbeat -Status "reauth_required" -Message "Token OAuth expirado ou revogado. Renove D:\AGENTES-IA\token.json executando o agente manualmente." -ExitCode $exitCode
        } elseif ($combinedOutput -match "OAUTH_NETWORK_BLOCKED" -or $combinedOutput -match "Sem conex.+o de rede para renovar o token OAuth" -or $combinedOutput -match "WinError 10013") {
            Write-Heartbeat -Status "network_blocked" -Message "Rede bloqueada ao renovar token OAuth. Verifique firewall, proxy, antivírus ou política de rede." -ExitCode $exitCode
        } else {
            Write-Heartbeat -Status "error" -Message "maintain-recent terminou com erro (exit $exitCode)." -ExitCode $exitCode
        }
    } else {
        Write-Heartbeat -Status "completed" -Message "maintain-recent completed." -ExitCode $exitCode
    }

    exit $exitCode
}
catch {
    Write-Log "ERRO inesperado: $($_.Exception.Message)"
    Write-Log "Stack: $($_.ScriptStackTrace)"
    # Tentar capturar saída mesmo em caso de erro do PS1
    Append-FileToLog -FilePath $stdoutPath -Label "STDOUT (erro)"
    Append-FileToLog -FilePath $stderrPath -Label "STDERR (erro)"
    Write-Heartbeat -Status "error" -Message $_.Exception.Message -ExitCode 1
    exit 1
}
finally {
    Clear-Lock
}
