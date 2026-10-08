param(
    [ValidateSet('start', 'stop', 'restart', 'status', 'logs')]
    [string]$Action = 'status'
)
$ErrorActionPreference = 'Stop'
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$MainFile = Join-Path $PSScriptRoot 'main.py'
$PidFile = Join-Path $PSScriptRoot 'bot.pid'
$OutputLog = Join-Path $PSScriptRoot 'bot.out.log'
$ErrorLog = Join-Path $PSScriptRoot 'bot.err.log'

function Get-BotProcess {
    if (-not (Test-Path -LiteralPath $PidFile)) { return $null }
    $taskProcessId = 0
    if (-not [int]::TryParse((Get-Content -LiteralPath $PidFile -Raw).Trim(), [ref]$taskProcessId)) { return $null }
    $process = Get-Process -Id $taskProcessId -ErrorAction SilentlyContinue
    if ($process -and $process.Path -eq $Python) {
        $details = Get-CimInstance Win32_Process -Filter "ProcessId=$taskProcessId"
        if ($details.CommandLine.Contains($MainFile)) { return $process }
    }
    return $null
}

function Stop-BotTree {
    param([int]$TaskProcessId)
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$TaskProcessId" -ErrorAction SilentlyContinue
    foreach ($child in $children) { Stop-BotTree -TaskProcessId ([int]$child.ProcessId) }
    Stop-Process -Id $TaskProcessId -ErrorAction SilentlyContinue
}

if ($Action -eq 'logs') {
    foreach ($file in @($OutputLog, $ErrorLog)) {
        if (Test-Path -LiteralPath $file) { Get-Content -LiteralPath $file -Tail 50 }
    }
    exit 0
}
$current = Get-BotProcess
if ($Action -eq 'status') {
    if ($current) { Write-Output "Bot is running (PID $($current.Id))" }
    else { Write-Output 'Bot is not running' }
    exit 0
}
if ($Action -in @('stop', 'restart')) {
    if ($current) { Stop-BotTree -TaskProcessId $current.Id }
    if (Test-Path -LiteralPath $PidFile) { Remove-Item -LiteralPath $PidFile }
    if ($Action -eq 'stop') { Write-Output 'Bot stopped'; exit 0 }
    $current = $null
}
if ($current) { Write-Output "Bot already running (PID $($current.Id))"; exit 0 }
if (-not (Test-Path -LiteralPath $Python)) { throw "Python environment missing: $Python" }
$env:PYTHONIOENCODING = 'utf-8'
$process = Start-Process -FilePath $Python -ArgumentList ('"' + $MainFile + '"') `
    -WorkingDirectory $PSScriptRoot -WindowStyle Hidden `
    -RedirectStandardOutput $OutputLog -RedirectStandardError $ErrorLog -PassThru
Set-Content -LiteralPath $PidFile -Value $process.Id
Start-Sleep -Seconds 2
if (-not (Get-BotProcess)) { throw "Bot stopped during startup. See $ErrorLog" }
Write-Output "Bot started (PID $($process.Id))"
