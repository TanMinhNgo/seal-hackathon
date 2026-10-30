[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$backendPath = Join-Path $PSScriptRoot 'backend'
$frontendPath = Join-Path $PSScriptRoot 'frontend'
$pythonPath = Join-Path $backendPath '.venv/Scripts/python.exe'
$logPath = Join-Path $PSScriptRoot '.logs'
$startedProcesses = @()

foreach ($command in @('docker', 'node', 'npm.cmd')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Khong tim thay $command. Xem huong dan cai dat trong README.md."
    }
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Chua co backend/.venv. Hay setup backend theo README.md truoc.'
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendPath 'node_modules'))) {
    throw 'Chua cai thu vien frontend. Hay chay npm ci trong frontend/.'
}
foreach ($port in @(3000, 8000)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Cong $port dang duoc su dung. Hay dung ung dung do truoc khi chay lai."
    }
}

Push-Location $PSScriptRoot
try {
    docker info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Engine chua san sang. Hay mo Docker Desktop roi chay lai.'
    }
    docker compose up --detach --wait
    if ($LASTEXITCODE -ne 0) {
        throw 'Dich vu phu tro khoi dong that bai. Xem: docker compose logs --tail=100'
    }

    $migration = Start-Process -FilePath $pythonPath -ArgumentList '-m alembic upgrade head' `
        -WorkingDirectory $backendPath -NoNewWindow -Wait -PassThru
    if ($migration.ExitCode -ne 0) {
        throw 'Migration that bai. Kiem tra DATABASE_URL trong backend/.env.'
    }

    New-Item -ItemType Directory -Path $logPath -Force | Out-Null
    $services = @(
        @{ Name = 'api'; File = $pythonPath; Dir = $backendPath; Args = '-m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000' },
        @{ Name = 'worker'; File = $pythonPath; Dir = $backendPath; Args = '-m celery -A worker.celery_app:celery_app worker --pool=solo --loglevel=info' },
        @{ Name = 'beat'; File = $pythonPath; Dir = $backendPath; Args = '-m celery -A worker.celery_app:celery_app beat --loglevel=info' },
        @{ Name = 'frontend'; File = $env:ComSpec; Dir = $frontendPath; Args = '/d /s /c "npm.cmd run dev -- --hostname 127.0.0.1 --port 3000"' }
    )
    foreach ($service in $services) {
        $startedProcesses += Start-Process -FilePath $service.File -ArgumentList $service.Args `
            -WorkingDirectory $service.Dir -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $logPath "$($service.Name).out.log") `
            -RedirectStandardError (Join-Path $logPath "$($service.Name).err.log")
    }

    Write-Host 'Dang khoi dong local: http://localhost:3000 | API: http://localhost:8000/docs'
    Write-Host "Log: $logPath"
    Write-Host 'Nhan Ctrl+C de dung ung dung local. PostgreSQL/Redis van chay.'
    while ($true) {
        foreach ($process in $startedProcesses) {
            if ($process.HasExited) {
                throw "Tien trinh local $($process.Id) da dung. Kiem tra log trong $logPath."
            }
        }
        Start-Sleep -Seconds 1
    }
}
finally {
    # Chi dung cay tien trinh do lan chay nay tao, khong dung nham Node/Python khac.
    foreach ($process in $startedProcesses) {
        if (-not $process.HasExited) {
            try { & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null }
            catch { Write-Warning "Khong dung duoc tien trinh $($process.Id)." }
        }
    }
    Pop-Location
}
