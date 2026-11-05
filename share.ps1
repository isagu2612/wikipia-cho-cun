param(
    [string]$Public = 'https://sgk.ncd-congdinh2612.workers.dev',
    [int]$Port = 8765
)

# Chạy server.py (nếu chưa chạy) + cloudflared quick tunnel, in sẵn link có ?api=
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

# 2) cloudflared
$cf = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
if (-not (Test-Path $cf)) {
    $cmd = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
    if ($cmd) { $cf = $cmd.Source }
}
if (-not (Test-Path $cf)) {
    Write-Host 'Chua cai cloudflared. Chay: winget install Cloudflare.cloudflared'
    Read-Host 'Nhan Enter de thoat'
    exit 1
}

$log = Join-Path $env:TEMP 'toan-tunnel.log'
Remove-Item $log -ErrorAction SilentlyContinue
$tunnel = Start-Process -FilePath $cf `
    -ArgumentList 'tunnel', '--url', "http://127.0.0.1:$Port", '--no-autoupdate' `
    -RedirectStandardError $log -WindowStyle Hidden -PassThru

$url = $null
for ($i = 0; $i -lt 30 -and -not $url; $i++) {
    Start-Sleep 1
    $hit = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' `
        -AllMatches -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { $url = $hit.Matches[0].Value }
}
if (-not $url) {
    Write-Host "Khong lay duoc URL tunnel. Xem log: $log"
    if (-not $tunnel.HasExited) { $tunnel.Kill() }
    Read-Host 'Nhan Enter de thoat'
    exit 1
}

$link = "$Public/?api=$url"
Set-Clipboard -Value $link

Write-Host ''
Write-Host '  API backend : ' -NoNewline; Write-Host $url
Write-Host '  Link de mo  : ' -NoNewline; Write-Host $link
Write-Host ''
Write-Host '  Da copy link vao clipboard. Dan cho nguoi khac, hoac mo link do'
Write-Host '  tren may nay (chi can 1 lan, trinh duyet tu nho dia chi API).'
Write-Host ''
Write-Host '  Giu cua so nay mo. Nhan Ctrl+C de dung tunnel.'

try {
    while (-not $tunnel.HasExited) { Start-Sleep 2 }
    Write-Host 'Tunnel da dung.'
}
finally {
    if (-not $tunnel.HasExited) { $tunnel.Kill() }
}
