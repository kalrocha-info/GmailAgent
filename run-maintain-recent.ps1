$ErrorActionPreference = "Stop"

$projectRoot = "D:\AGENTES-IA"
$stateDir = Join-Path $projectRoot "state"
$logPath = Join-Path $stateDir "maintain-recent.log"
$heartbeatPath = Join-Path $stateDir "maintain-recent-heartbeat.json"
$lockPath = Join-Path $stateDir "maintain-recent.lock"
$stdoutPath = Join-Path $stateDir "maintain-recent.stdout.log"
$stderrPath = Join-Path $stateDir "maintain-recent.stderr.log"
$pythonPath = "C:\Users\kalro\AppData\Local\Programs\Python\Python314\python.exe"
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

    # --- Limpar logs anteriores (mas guardar, não apagar silenciosamente) ---
    # MELHORIA-4: não apagamos antes de correr — sobrescrevemos depois
    # Assim garantimos que stderr e stdout são sempre capturados

    # --- Verificar que o Python existe ---
    if (-not (Test-Path $pythonPath)) {
        Write-Log "ERRO: Python nao encontrado em $pythonPath"
        Write-Heartbeat -Status "error" -Message "Python not found at $pythonPath" -ExitCode 1
        exit 1
    }

    Write-Log "Python: $pythonPath"
    Write-Log "Args: $($pythonArgs -join ' ')"

    # --- Lançar processo ---
    $process = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList $pythonArgs `
        -WorkingDirectory $projectRoot `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru `
        -NoNewWindow

    Write-Log "Processo iniciado (PID $($process.Id)). Timeout: ${timeoutSeconds}s."
    Write-Heartbeat -Status "running" -Message "Process started (PID $($process.Id))."

    # --- Aguardar com timeout ---
    $finished = $process.WaitForExit($timeoutSeconds * 1000)

    if (-not $finished) {
        Write-Log "TIMEOUT: maintain-recent excedeu ${timeoutSeconds}s; encerrando processo."
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500  # dar tempo ao processo para encerrar

        Append-FileToLog -FilePath $stdoutPath -Label "STDOUT (timeout)"
        Append-FileToLog -FilePath $stderrPath -Label "STDERR (timeout)"

        Write-Heartbeat -Status "timeout" -Message "Process exceeded timeout and was terminated." -ExitCode 124
        exit 124
    }

    # --- MELHORIA-4: Capturar stdout e stderr SEMPRE, mesmo em sucesso ---
    Append-FileToLog -FilePath $stdoutPath -Label "STDOUT"
    Append-FileToLog -FilePath $stderrPath -Label "STDERR"

    # --- Obter exit code com fallback explícito ---
    # BUG PS1 corrigido: $process.ExitCode pode ser $null em edge cases;
    # usar Refresh() para garantir que o valor está atualizado
    $process.Refresh()
    $exitCode = $process.ExitCode
    if ($null -eq $exitCode) {
        Write-Log "AVISO: Exit code nulo (processo pode ter sido encerrado externamente). Assumindo 1."
        $exitCode = 1
    }

    Write-Log "Exit code: $exitCode"

    if ($exitCode -ne 0) {
        Write-Heartbeat -Status "error" -Message "maintain-recent terminou com erro (exit $exitCode)." -ExitCode $exitCode
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
