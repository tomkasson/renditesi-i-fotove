# Instaluesi i Renditesit te Fotove (Windows 10/11, me internet). Nuk kerkon te drejta administratori.
#  - Python 3.13 vetem per kete perdorues: %LOCALAPPDATA%\RenditesiFotove\python
#  - kodi:  %LOCALAPPDATA%\RenditesiFotove\app   (nga GitHub, ose nga dosja ku ndodhet ky skedar)
#  - te dhenat (emrat, pema...): %LOCALAPPDATA%\RenditesiFotove\data   (nuk preken nga perditesimet)
#  - ikonat ne Desktop dhe ne menune Start
param(
    [string]$Repo = "",        # "pronari/emri" ne GitHub (bosh = merret nga versioni.json, ose kodi i kesaj dosjeje)
    [string]$Dega = "main",
    [switch]$PaLibrari,        # vetem per prova: mos instalo librarite
    [switch]$PaIkona,          # vetem per prova: mos krijo ikonat
    [string]$Baza = "",        # vetem per prova: dosja e instalimit
    [string]$Python = ""       # vetem per prova: python.exe ekzistues
)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$PYVER = "3.13.9"
$baza = if ($Baza) { $Baza } else { Join-Path $env:LOCALAPPDATA "RenditesiFotove" }
$app = Join-Path $baza "app"
$pyDir = Join-Path $baza "python"
$py = if ($Python) { $Python } else { Join-Path $pyDir "python.exe" }
$ketu = $PSScriptRoot

function Hapi($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }

Write-Host "Renditesi i Fotove - instalimi" -ForegroundColor Cyan
Write-Host "Zgjat 5-20 minuta (shkarkohen rreth 1 GB librari). Mos e mbyll kete dritare."
New-Item -ItemType Directory -Force -Path $baza | Out-Null

if (-not $Repo -and (Test-Path (Join-Path $ketu "versioni.json"))) {
    $Repo = (Get-Content (Join-Path $ketu "versioni.json") -Raw | ConvertFrom-Json).repo
}

# 1) Python
Hapi "1/4 Python $PYVER"
if (Test-Path $py) { Write-Host "Eshte tashme: $py" }
else {
    $exe = Join-Path $env:TEMP "python-$PYVER-amd64.exe"
    Write-Host "Po shkarkoj Python nga python.org..."
    Invoke-WebRequest -UseBasicParsing "https://www.python.org/ftp/python/$PYVER/python-$PYVER-amd64.exe" -OutFile $exe
    Write-Host "Po instaloj Python (vetem per kete perdorues)..."
    $pyArgs = "/quiet InstallAllUsers=0 TargetDir=`"$pyDir`" Include_launcher=0 Include_test=0 Include_doc=0 " +
            "PrependPath=0 Shortcuts=0 AssociateFiles=0"
    Start-Process -FilePath $exe -ArgumentList $pyArgs -Wait
    if (-not (Test-Path $py)) { throw "Python nuk u instalua ne $pyDir" }
}

# 2) Kodi
Hapi "2/4 Kodi i Renditesit"
$burim = $null
if ($Repo) {
    $zip = Join-Path $env:TEMP "renditesi.zip"
    $tmp = Join-Path $env:TEMP ("renditesi_" + [guid]::NewGuid().ToString("N"))
    Write-Host "Po shkarkoj kodin nga GitHub: $Repo ($Dega)..."
    Invoke-WebRequest -UseBasicParsing "https://codeload.github.com/$Repo/zip/refs/heads/$Dega" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $burim = (Get-ChildItem $tmp | Where-Object { $_.PSIsContainer } | Select-Object -First 1).FullName
} elseif (Test-Path (Join-Path $ketu "app.py")) {
    $burim = $ketu
    Write-Host "Po kopjoj kodin nga: $burim"
} else { throw "Nuk di nga t'i marr kodin: jep -Repo pronari/emri" }
New-Item -ItemType Directory -Force -Path $app | Out-Null
if ((Resolve-Path $burim).Path -ne (Resolve-Path $app).Path) {
    Get-ChildItem $burim -Force | Where-Object { @(".venv", ".git", "cache", "__pycache__") -notcontains $_.Name } |
        ForEach-Object { Copy-Item $_.FullName -Destination $app -Recurse -Force }
}

# 3) Librarite
Hapi "3/4 Librarite (AI, faqet...)"
$venvPy = Join-Path $app ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { & $py -m venv (Join-Path $app ".venv") }
if ($PaLibrari) { Write-Host "(prove: librarite nuk instalohen)" }
else {
    & $venvPy -m pip install --upgrade pip --quiet
    & $venvPy -m pip install -r (Join-Path $app "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Instalimi i librarive deshtoi (shih me lart)." }
}

# 4) Ikonat dhe nisja
Hapi "4/4 Ikonat"
if (-not $PaIkona) { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $app "krijo_ikonat.ps1") -AppDir $app }
Write-Host ""
Write-Host "Gati! Renditesi i Fotove u instalua. Hape nga ikona ne Desktop." -ForegroundColor Green
if (-not $PaLibrari) { Start-Process (Join-Path $app ".venv\Scripts\pythonw.exe") -ArgumentList ('"' + (Join-Path $app "Renditesi.pyw") + '"') -WorkingDirectory $app }
