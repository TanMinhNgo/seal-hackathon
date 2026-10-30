$ErrorActionPreference = 'Stop'
$runScript = Join-Path (Split-Path $PSScriptRoot -Parent) 'run.ps1'
$originalLocation = (Get-Location).Path
$global:sealRunTest = @{}

# Mock cac thao tac ngoai de khong cham vao container hoac tien trinh that.
function global:docker {
    $command = $args -join ' '
    $global:sealRunTest.Commands.Add($command)
    $global:LASTEXITCODE = 0
    if ($global:sealRunTest.Fail -eq 'docker') { $global:LASTEXITCODE = 1 }
}
function global:Get-Command { param($Name, $ErrorAction) return @{ Name = $Name } }
function global:Test-Path { param($LiteralPath) return $true }
function global:Get-NetTCPConnection { param($LocalPort, $State, $ErrorAction) }
function global:New-Item { param($ItemType, $Path, [switch]$Force) }
function global:Start-Process {
    param($FilePath, $ArgumentList, $WorkingDirectory, $WindowStyle,
        $RedirectStandardOutput, $RedirectStandardError,
        [switch]$PassThru, [switch]$NoNewWindow, [switch]$Wait)
    $global:sealRunTest.Commands.Add("process $ArgumentList")
    if ($Wait) {
        return @{ ExitCode = [int]($global:sealRunTest.Fail -eq 'migration') }
    }
    if ($global:sealRunTest.Fail -eq 'start' -and $global:sealRunTest.Started -eq 2) {
        throw 'simulated start failure'
    }
    $global:sealRunTest.Started++
    return [PSCustomObject]@{ Id = 40000 + $global:sealRunTest.Started; HasExited = $false }
}
function global:Start-Sleep { param($Seconds) throw 'test stop' }
function global:taskkill.exe {
    $global:sealRunTest.Stopped++
    $global:LASTEXITCODE = 0
}

try {
    Set-Location $env:TEMP
    $testLocation = (Get-Location).Path
    foreach ($scenario in @('', 'docker', 'migration', 'start')) {
        $global:sealRunTest = @{
            Commands = [System.Collections.Generic.List[string]]::new()
            Fail = $scenario; Started = 0; Stopped = 0
        }
        $caught = $null
        try { & $runScript } catch { $caught = $_ }
        if (-not $caught) { throw 'Script phai thoat khi gap loi hoac test stop.' }
        if ($scenario -eq '' -and $caught.Exception.Message -ne 'test stop') { throw $caught }
        $expected = switch ($scenario) { '' { 4 }; 'start' { 2 }; default { 0 } }
        if ($global:sealRunTest.Started -ne $expected -or $global:sealRunTest.Stopped -ne $expected) {
            throw "Sai so tien trinh khoi dong/don dep: $scenario"
        }
        if ((Get-Location).Path -ne $testLocation) { throw 'Khong khoi phuc thu muc.' }
        if ($scenario -eq '' -and $global:sealRunTest.Commands[1] -ne 'compose up --detach --wait') {
            throw 'Compose chi duoc dung de chay dich vu phu tro.'
        }
    }
    Write-Host 'PASS: local startup, migration failure, Docker failure, partial-start cleanup, location.'
}
finally {
    foreach ($name in @('docker', 'Get-Command', 'Test-Path', 'Get-NetTCPConnection', 'New-Item', 'Start-Process', 'Start-Sleep', 'taskkill.exe')) {
        Remove-Item -LiteralPath "Function:\$name"
    }
    Remove-Variable sealRunTest -Scope Global
    Set-Location $originalLocation
}
