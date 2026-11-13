<#
Builds the offline ANVESHAN installer.

Needs internet ONCE, to fetch the embeddable Python, the WebView2 offline
installer and Inno Setup. The resulting setup file needs none of them.

    powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
#>
param(
    [string]$Dist       = "$env:USERPROFILE\Desktop\anveshan-dist",
    [string]$PyVersion  = "3.13.7"   # must match .venv, the .pyd files are ABI-locked
)
$ErrorActionPreference = 'Stop'
$src = Split-Path $PSScriptRoot -Parent
$app = Join-Path $Dist 'ANVESHAN'

# The venv's own python is NOT shippable: pyvenv.cfg hardcodes an absolute
# path to the build machine's interpreter. Use the embeddable distribution.
$embed = Join-Path $Dist 'runtime'
if (-not (Test-Path (Join-Path $embed 'python.exe'))) {
    New-Item -ItemType Directory -Force $embed | Out-Null
    $zip = Join-Path $Dist 'py-embed.zip'
    Invoke-WebRequest "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip" -OutFile $zip
    Expand-Archive $zip -DestinationPath $embed -Force
}

$prereq = Join-Path $Dist 'prereq'
$wv2 = Join-Path $prereq 'MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
if (-not (Test-Path $wv2)) {
    New-Item -ItemType Directory -Force $prereq | Out-Null
    # Evergreen Standalone Installer: a full ~203 MB offline package, not the
    # 1.7 MB bootstrapper (that one needs the network).
    Invoke-WebRequest 'https://go.microsoft.com/fwlink/p/?LinkId=2124701' -OutFile $wv2
}

# ANVESHAN.exe is a copy of pythonw.exe, so without this it shows Python's
# icon and "Python" as its description in the title bar and Task Manager.
$rcedit = Join-Path $Dist 'rcedit.exe'
if (-not (Test-Path $rcedit)) {
    Invoke-WebRequest 'https://github.com/electron/rcedit/releases/download/v2.0.0/rcedit-x64.exe' -OutFile $rcedit
}

Write-Host 'Staging bundle...'
if (Test-Path $app) { Remove-Item $app -Recurse -Force }
New-Item -ItemType Directory -Force (Join-Path $app 'runtime'),(Join-Path $app 'lib') | Out-Null
Copy-Item "$embed\*" (Join-Path $app 'runtime') -Recurse -Force
$exe = Join-Path $app 'runtime\ANVESHAN.exe'
Copy-Item (Join-Path $app 'runtime\pythonw.exe') $exe
& $rcedit $exe --set-icon (Join-Path $PSScriptRoot 'anveshan.ico') `
    --set-version-string FileDescription 'ANVESHAN Offline Analyst Workstation' `
    --set-version-string ProductName 'ANVESHAN' `
    --set-version-string CompanyName 'Team ANVESHAN' `
    --set-version-string OriginalFilename 'ANVESHAN.exe'
if ($LASTEXITCODE -ne 0) { throw 'rcedit failed' }
Copy-Item "$src\.venv\Lib\site-packages\*" (Join-Path $app 'lib') -Recurse -Force
# venv-only shims confuse a plain interpreter
foreach ($junk in '_virtualenv.pth','_virtualenv.py','activate_this.py') {
    Remove-Item (Join-Path $app "lib\$junk") -Force -ErrorAction SilentlyContinue
}
# Generate from local weights only; exporter rejects numerical differences.
& "$src\.venv\Scripts\python.exe" "$PSScriptRoot\export_cluster_runtime.py" --root $src
if ($LASTEXITCODE -ne 0) { throw 'Offline inference bundle validation failed' }
foreach ($d in 'app','web','models') { Copy-Item "$src\$d" $app -Recurse -Force }
Copy-Item "$src\desktop.py" $app -Force

# Relative paths only -- the bundle has to run from whatever directory the
# operator installs it into.
@'
python313.zip
.
..\lib
..
import site
'@ | Set-Content -Path (Join-Path $app 'runtime\python313._pth') -Encoding ascii

Get-ChildItem $app -Recurse -Directory -Filter __pycache__ |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $iscc)) { throw "Inno Setup missing: winget install --id JRSoftware.InnoSetup" }

# scriptsnveshan.iss is the authoritative copy; the dist folder is scratch.
Copy-Item (Join-Path $PSScriptRoot 'anveshan.iss') $Dist -Force
Copy-Item (Join-Path $PSScriptRoot 'anveshan.ico') $Dist -Force

Write-Host 'Compiling installer (takes several minutes)...'
& $iscc (Join-Path $Dist 'anveshan.iss')
if ($LASTEXITCODE -ne 0) { throw "ISCC failed with $LASTEXITCODE" }
Get-ChildItem "$Dist\ANVESHAN-Setup-*.exe" | Select-Object Name,@{n='MB';e={[int]($_.Length/1MB)}}
