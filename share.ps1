param(
    [string]$Public = 'https://sgk.ncd-congdinh2612.workers.dev',
    [int]$Port = 8765
)

# Chạy server.py (nếu chưa chạy) + ngrok với domain cố định.
# Link công khai luôn là $Public, không đổi giữa các lần chạy.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Test-Port {
    param([int]$p)
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue)
}

# 1) Server
if (-not (Test-Port $Port)) {
    Write-Host 'Dang khoi dong server...'
    Start-Process -FilePath 'python' -ArgumentList 'server.py', '--no-browser', '--port', $Port `
        -WorkingDirectory $root -WindowStyle Hidden
    for ($i = 0; $i -lt 20 -and -not (Test-Port $Port); $i++) { Start-Sleep -Milliseconds 500 }
}
if (-not (Test-Port $Port)) {
    Write-Host 'Khong khoi dong duoc server. Chay thu: python server.py'
    Read-Host 'Nhan Enter de thoat'
    exit 1
}

# 2) ngrok (domain free co dinh gan voi tai khoan)
$ngrok = (Get-Command ngrok.exe -ErrorAction SilentlyContinue).Source
if (-not $ngrok) {
    $ngrok = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter ngrok.exe `
        -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $ngrok) {
    Write-Host 'Chua cai ngrok. Chay: winget install Ngrok.Ngrok'
    Read-Host 'Nhan Enter de thoat'
    exit 1
}

Write-Host ''
Write-Host '  Link de chia se : ' -NoNewline; Write-Host $Public
Write-Host '  (domain backend co dinh, khong doi khi chay lai)'
Write-Host ''

if (Get-Process ngrok -ErrorAction SilentlyContinue) {
    Write-Host '  ngrok dang chay san. Khong mo them.'
    Write-Host ''
    Read-Host '  Nhan Enter de thoat'
    exit 0
}

Write-Host '  Giu cua so nay mo. Nhan Ctrl+C de dung tunnel.'
& $ngrok http $Port
