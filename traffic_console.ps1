$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$StatusPath = Join-Path $ProjectRoot "reports\dashboard\status.json"
$DashboardUrl = "http://127.0.0.1:8000/dashboard/"
$ControlPanelUrl = "http://127.0.0.1:8010/"
$ActionsUrl = "https://github.com/JaRu77/awp-traffic-monitor/actions"

function Wait-Key {
    Write-Host ""
    Read-Host "Enter aby kontynuowac"
}

function Require-Python {
    if (-not (Test-Path $Python)) {
        Write-Host "Brak .venv\Scripts\python.exe" -ForegroundColor Red
        Write-Host "Najpierw zainstaluj zaleznosci projektu."
        Wait-Key
        return $false
    }
    return $true
}

function Show-Status {
    Clear-Host
    Write-Host "Stan badania AWP" -ForegroundColor Cyan
    Write-Host "----------------"

    if (-not (Test-Path $StatusPath)) {
        Write-Host "Brak reports\dashboard\status.json. Najpierw odswiez z GitHuba." -ForegroundColor Yellow
        Wait-Key
        return
    }

    $status = Get-Content -Raw $StatusPath | ConvertFrom-Json
    $slot = $status.latest_scheduled_slot
    if (-not $slot) { $slot = $status.latest_measurement }

    Write-Host ("Data:                 {0}" -f $status.date)
    Write-Host ("Ostatni cykl:         {0}" -f $status.latest_run_status)
    Write-Host ("Requesty dzis:        {0} / {1}" -f $status.request_total, $status.request_limit_reference)
    Write-Host ("Punkty:               {0}" -f $status.points)
    Write-Host ("Bledy dzis:           {0}" -f $status.errors_today)
    Write-Host ("Sloty dzis:           {0} / {1}" -f $status.completed_slots_today, $status.expected_slots_so_far)
    Write-Host ("Braki slotow:         {0}" -f $status.missing_slots_so_far)
    Write-Host ("Wiek danych:          {0} min" -f $status.stale_minutes)
    Write-Host ("Slot pomiaru:         {0}" -f (Short-Time $slot))
    Write-Host ("Pobrano faktycznie:   {0}" -f (Short-Time $status.latest_measurement))
    Wait-Key
}

function Short-Time($value) {
    if (-not $value) { return "brak" }
    $text = [string]$value
    if ($text.Contains("T")) {
        $parts = $text.Split("T", 2)
        return ("{0} {1}" -f $parts[0], $parts[1].Substring(0, [Math]::Min(5, $parts[1].Length)))
    }
    return $text.Substring(0, [Math]::Min(16, $text.Length))
}

function Refresh-GitHub {
    if (-not (Require-Python)) { return }
    Clear-Host
    & $Python scripts\sync_from_github.py
    Wait-Key
}

function Start-ControlPanel {
    if (-not (Require-Python)) { return }
    Start-Process -FilePath $Python -ArgumentList "scripts\control_panel.py" -WorkingDirectory $ProjectRoot -WindowStyle Hidden
    Start-Process $ControlPanelUrl
}

function Start-Dashboard {
    if (-not (Require-Python)) { return }
    Start-Process -FilePath $Python -ArgumentList "scripts\serve_dashboard.py --sync" -WorkingDirectory $ProjectRoot -WindowStyle Hidden
    Start-Process $DashboardUrl
}

function Make-Report {
    if (-not (Require-Python)) { return }
    Clear-Host
    & $Python scripts\make_daily_report.py
    Wait-Key
}

function Export-Csv {
    if (-not (Require-Python)) { return }
    Clear-Host
    & $Python scripts\export_csv.py
    Wait-Key
}

while ($true) {
    Clear-Host
    Write-Host "AWP Traffic Monitor - konsola" -ForegroundColor Cyan
    Write-Host "--------------------------------"
    Write-Host "1. Pokaz stan badania"
    Write-Host "2. Odswiez dane z GitHuba"
    Write-Host "3. Otworz appke kontrolna w przegladarce"
    Write-Host "4. Otworz pulpit HTML"
    Write-Host "5. Generuj raport dzienny"
    Write-Host "6. Eksportuj CSV"
    Write-Host "7. Otworz GitHub Actions"
    Write-Host "Q. Wyjdz"
    Write-Host ""

    $choice = Read-Host "Wybierz"
    switch ($choice.ToUpperInvariant()) {
        "1" { Show-Status }
        "2" { Refresh-GitHub }
        "3" { Start-ControlPanel }
        "4" { Start-Dashboard }
        "5" { Make-Report }
        "6" { Export-Csv }
        "7" { Start-Process $ActionsUrl }
        "Q" { break }
        default { Wait-Key }
    }
}
