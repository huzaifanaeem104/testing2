WINDOWS_SETUP_PS1 = r"""
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"

$Base = "__BASE_URL__".TrimEnd("/")
$Db = "__DB_NAME__"
$CertB64 = "__CERT_B64__"
$Temp = $env:TEMP
$CertPath = Join-Path $Temp "override.crt"
$Installer = Join-Path $Temp "qz-tray-setup.exe"
$UserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NARC-Direct-Print"

function Assert-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        $script = $MyInvocation.PSCommandPath
        if ($script) {
            Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
        }
        exit
    }
}

function Get-File($Url, $OutFile, $MinBytes) {
    if (-not $MinBytes) { $MinBytes = 100 }
    Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue

    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        & curl.exe -L --retry 4 --retry-delay 2 --fail --connect-timeout 20 --max-time 180 -A $UserAgent -o $OutFile $Url
        if ($LASTEXITCODE -eq 0 -and (Test-Path $OutFile) -and ((Get-Item $OutFile).Length -gt $MinBytes)) {
            return $true
        }
    }

    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $OutFile -TimeoutSec 180 -UserAgent $UserAgent
        if ((Test-Path $OutFile) -and ((Get-Item $OutFile).Length -gt $MinBytes)) {
            return $true
        }
    } catch {}

    try {
        Start-BitsTransfer -Source $Url -Destination $OutFile -ErrorAction Stop
        if ((Test-Path $OutFile) -and ((Get-Item $OutFile).Length -gt $MinBytes)) {
            return $true
        }
    } catch {}

    return $false
}

function Get-QzDir {
    foreach ($path in @(
        "${env:ProgramFiles}\QZ Tray",
        "${env:ProgramFiles(x86)}\QZ Tray"
    )) {
        if ($path -and (Test-Path (Join-Path $path "qz-tray.exe"))) {
            return $path
        }
    }
    return $null
}

function Install-QzTray {
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "x86_64" }
    $urls = @(
        "https://github.com/qzind/tray/releases/download/v2.2.6/qz-tray-2.2.6-$arch.exe"
    )
    foreach ($url in $urls) {
        Write-Host "Downloading QZ Tray..."
        if (Get-File $url $Installer 1000000) {
            Write-Host "Installing QZ Tray. This is only needed once on this computer..."
            Start-Process -FilePath $Installer -ArgumentList "/S" -Wait
            Start-Sleep -Seconds 8
            if (Get-QzDir) { return $true }
        }
    }
    return $false
}

function Write-EmbeddedCert {
    if (-not $CertB64 -or $CertB64 -eq "__CERT_B64__") {
        return $false
    }
    try {
        [IO.File]::WriteAllBytes($CertPath, [Convert]::FromBase64String($CertB64))
        return ((Test-Path $CertPath) -and ((Get-Item $CertPath).Length -gt 200))
    } catch {
        return $false
    }
}

function Get-OdooCert {
    if (Write-EmbeddedCert) {
        return $true
    }
    $urls = @(
        "$Base/narc_direct_print/static/setup/override.crt",
        "$Base/narc_direct_print/qz/certificate?download=1"
    )
    if ($Db) {
        $urls += "$Base/narc_direct_print/qz/certificate?download=1&db=$Db"
    }
    foreach ($url in $urls) {
        if (Get-File $url $CertPath 200) {
            return $true
        }
    }
    return $false
}

Assert-Admin
Write-Host "Installing Odoo print certificate..."
if (-not (Get-OdooCert)) {
    Write-Host "Could not install the print certificate. Download narc-print-setup.bat from Odoo again and run that new file."
    cmd /c pause
    exit 1
}

$QzDir = Get-QzDir
if (-not $QzDir) {
    [void](Install-QzTray)
    $QzDir = Get-QzDir
}

if (-not $QzDir) {
    Write-Host ""
    Write-Host "This network blocked the automatic QZ Tray download."
    Write-Host "The QZ Tray website will open. Install QZ Tray, then run this setup again."
    Start-Process "https://qz.io/download/"
    cmd /c pause
    exit 1
}

Copy-Item -Force $CertPath (Join-Path $QzDir "override.crt")
Write-Host "Trusted Odoo on this computer: $QzDir\override.crt"
Get-Process -Name "qz-tray","javaw" -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*QZ Tray*" -or $_.ProcessName -eq "qz-tray"
} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Process (Join-Path $QzDir "qz-tray.exe")
Write-Host ""
Write-Host "This computer is ready. Click Print PDF in Odoo."
Write-Host "The job goes to the default printer. No Allow box. No printer picker."
cmd /c pause
"""

WINDOWS_SETUP_BAT = r"""@echo off
setlocal EnableExtensions
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting administrator permission so this PC can be set up for all users...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

set "PS1=%TEMP%\narc-print-setup.ps1"
echo Preparing setup...
if exist "%PS1%" del /f /q "%PS1%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "[IO.File]::WriteAllBytes($env:TEMP + '\narc-print-setup.ps1', [Convert]::FromBase64String('__PS1_B64__'))"
if not exist "%PS1%" (
    echo Could not write the setup script on this computer.
    pause
    exit /b 1
)
findstr /C:"Write-EmbeddedCert" "%PS1%" >nul 2>&1
if errorlevel 1 (
    echo This is an old setup file. Download a new narc-print-setup.bat from Odoo and run that.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
"""

LINUX_SETUP_SH = r"""#!/bin/bash
set -euo pipefail
BASE="__BASE_URL__"
DB="__DB_NAME__"
CERT_B64="__CERT_B64__"
QZDIR="/opt/qz-tray"

echo "Installing Odoo print certificate..."
if [ -n "$CERT_B64" ] && [ "$CERT_B64" != "__CERT_B64__" ]; then
    printf '%s' "$CERT_B64" | base64 -d > /tmp/override.crt
else
    CERT_URL="$BASE/narc_direct_print/static/setup/override.crt"
    curl -fsSL "$CERT_URL" -o /tmp/override.crt || curl -fsSL "$BASE/narc_direct_print/qz/certificate?download=1" -o /tmp/override.crt
fi
if [ ! -s /tmp/override.crt ]; then
    echo "Could not install the print certificate. Download narc-print-setup.sh from Odoo again."
    exit 1
fi

if [ ! -x "$QZDIR/qz-tray" ]; then
    echo "Installing QZ Tray. This is only needed once on this computer..."
    wget -qO - https://qz.sh | bash
fi

if [ ! -d "$QZDIR" ]; then
    echo "QZ Tray was not found. Install it, then run this script again."
    exit 1
fi

sudo cp /tmp/override.crt "$QZDIR/override.crt"
echo "Trusted Odoo on this computer: $QZDIR/override.crt"
pkill -f qz-tray.jar >/dev/null 2>&1 || true
nohup "$QZDIR/qz-tray" >/tmp/qz-tray-narc.log 2>&1 &
echo "This computer is ready. Click Print PDF in Odoo."
"""
