$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonModuleRoot = Join-Path $projectRoot "python"
$stateDir = Join-Path $projectRoot "state"
$tokenPath = Join-Path $projectRoot "token.json"
$lockPath = Join-Path $stateDir "maintain-recent.lock"
$heartbeatPath = Join-Path $stateDir "maintain-recent-heartbeat.json"
$maintainScript = Join-Path $projectRoot "run-maintain-recent.ps1"
$scheduledTaskNames = @("GmailAgent Maintain", "\GmailAgent Maintain")
$pythonCandidates = @(
    "C:\Python313\python.exe",
    "C:\Users\kalro\AppData\Local\Programs\Python\Python314\python.exe",
    "C:\Users\kalro\AppData\Local\Programs\Python\Python313\python.exe",
    "C:\Users\kalro\AppData\Local\Programs\Python\Python312\python.exe",
    (Join-Path $projectRoot ".venv\Scripts\python.exe")
)

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "=== $Title ===" -ForegroundColor Cyan
}

function Confirm-Step {
    param([string]$Prompt)
    $answer = Read-Host "$Prompt [s/N]"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $false }
    return $answer.Trim().ToLower() -in @("s", "sim", "y", "yes")
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

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    try {
        return Get-Content $Path -Raw -Encoding utf8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Run-CommandSafe {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$Label
    )

    Write-Host ""
    Write-Host "Executando: $Label" -ForegroundColor Yellow
    & $FilePath @ArgumentList
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) { $exitCode = 0 }
    Write-Host "Exit code: $exitCode"
    return $exitCode
}

function Get-ScheduledTaskStatusText {
    foreach ($taskName in $scheduledTaskNames) {
        $output = & schtasks /Query /TN $taskName /V /FO LIST 2>&1
        if ($LASTEXITCODE -eq 0) {
            return ($output -join [Environment]::NewLine)
        }
    }
    return $null
}

Write-Section "Diagnostico"
Write-Host "Projeto: $projectRoot"

$pythonPath = Resolve-PythonPath
if (-not $pythonPath) {
    Write-Host "Python nao encontrado." -ForegroundColor Red
    exit 1
}

Write-Host "Python detectado: $pythonPath"
& $pythonPath --version

if (Test-Path $tokenPath) {
    $tokenFile = Get-Item $tokenPath
    Write-Host "token.json: presente ($($tokenFile.LastWriteTime))"
} else {
    Write-Host "token.json: ausente" -ForegroundColor Yellow
}

if (Test-Path $lockPath) {
    $lockFile = Get-Item $lockPath
    Write-Host "Lock encontrado: $($lockFile.LastWriteTime)" -ForegroundColor Yellow
} else {
    Write-Host "Lock: nenhum"
}

$heartbeat = Read-JsonFile -Path $heartbeatPath
if ($null -ne $heartbeat) {
    Write-Host "Heartbeat: $($heartbeat.status) | $($heartbeat.timestamp) | $($heartbeat.message)"
} else {
    Write-Host "Heartbeat: indisponivel"
}

$taskStatusText = Get-ScheduledTaskStatusText
Write-Section "Tarefa Agendada"
if ($null -ne $taskStatusText) {
    $interestingLines = $taskStatusText -split [Environment]::NewLine | Where-Object {
        $_ -match "Nome da tarefa:" -or
        $_ -match "Hora da próxima execução:" -or
        $_ -match "Horário da última execução:" -or
        $_ -match "Último resultado:" -or
        $_ -match "Status:" -or
        $_ -match "Tarefa a ser executada:" -or
        $_ -match "Repetir a cada:"
    }
    $interestingLines | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "Tarefa agendada não localizada." -ForegroundColor Yellow
}

Write-Section "Teste de Rede"
$curlExit = Run-CommandSafe -FilePath "curl.exe" -ArgumentList @("-I", "https://oauth2.googleapis.com") -Label "curl oauth2.googleapis.com"
$networkOk = ($curlExit -eq 0)
if (-not $networkOk) {
    Write-Host "Acesso HTTPS falhou. Isso costuma indicar bloqueio de firewall/rede." -ForegroundColor Red
}

Write-Section "Health Check"
$env:PYTHONPATH = $pythonModuleRoot
$healthExit = Run-CommandSafe -FilePath $pythonPath -ArgumentList @("-m", "gmail_agent.cli", "health-check") -Label "gmail-agent health-check"

if ($healthExit -eq 0) {
    Write-Host "Health check OK." -ForegroundColor Green
} else {
    Write-Host "Health check falhou." -ForegroundColor Yellow
}

if (Test-Path $lockPath) {
    Write-Section "Lock"
    if (Confirm-Step "Deseja remover o lock atual?") {
        Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
        Write-Host "Lock removido." -ForegroundColor Green
    }
}

if (($null -ne $heartbeat) -and ($heartbeat.status -eq "reauth_required")) {
    Write-Section "Reautenticacao"
    if (Confirm-Step "Deseja apagar token.json para forcar nova autenticacao?") {
        Remove-Item -LiteralPath $tokenPath -Force -ErrorAction SilentlyContinue
        Write-Host "token.json removido." -ForegroundColor Green
    }
}

if ((-not (Test-Path $tokenPath)) -and (Confirm-Step "Deseja executar o agente agora para reautenticar e/ou manter emails recentes?")) {
    Write-Section "Execucao Manual"
    $env:GMAIL_AGENT_INTERACTIVE_REAUTH = "1"
    Run-CommandSafe -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $maintainScript) -Label "run-maintain-recent.ps1"
} elseif (Confirm-Step "Deseja executar uma rodada manual do maintain-recent agora?") {
    Write-Section "Execucao Manual"
    $env:GMAIL_AGENT_INTERACTIVE_REAUTH = "1"
    Run-CommandSafe -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $maintainScript) -Label "run-maintain-recent.ps1"
}

if (($null -ne $taskStatusText) -and (Confirm-Step "Deseja disparar a tarefa agendada agora para teste?")) {
    Write-Section "Teste da Tarefa Agendada"
    $ran = $false
    foreach ($taskName in $scheduledTaskNames) {
        & schtasks /Run /TN $taskName 2>$null
        if ($LASTEXITCODE -eq 0) {
            $ran = $true
            break
        }
    }
    if ($ran) {
        Write-Host "Tarefa disparada." -ForegroundColor Green
    } else {
        Write-Host "Não foi possível disparar a tarefa agendada." -ForegroundColor Yellow
    }
}

Write-Section "Resumo Final"
$heartbeat = Read-JsonFile -Path $heartbeatPath
if ($null -ne $heartbeat) {
    Write-Host "Heartbeat final: $($heartbeat.status) | $($heartbeat.timestamp) | $($heartbeat.message)"
}
Write-Host "Script de verificacao concluido."
