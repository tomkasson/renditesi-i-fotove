# Cinstaluesi i Renditesit te Fotove: heq vetem ate qe krijoi instalo.ps1 per kete perdorues.
#  - mbyll Renditesin nese eshte i hapur
#  - heq ikonat (vetem ato qe tregojne te ky instalim)
#  - cinstalon Python-in e instaluesit (vetem nese eshte ai te %LOCALAPPDATA%\RenditesiFotove\python)
#  - fshin kodin dhe Python-in; te dhenat (emrat, pema, historiku) i MBAN si parazgjedhje, ose i con te Koshi
#  - heq regjistrimin nga "Aplikacionet e instaluara"
param(
    [string]$Baza = "",          # vetem per prova: dosja e instalimit
    [switch]$Po,                 # mos pyet per konfirmim (prova)
    [switch]$FshiTeDhenat,       # con edhe te dhenat te Koshi (pa pyetur)
    [switch]$MbajTeDhenat,       # mban te dhenat (pa pyetur)
    [string]$RegKey = "RenditesiFotove",  # vetem per prova
    [string]$Desktop = "",       # vetem per prova
    [string]$StartMenu = ""      # vetem per prova
)
$ErrorActionPreference = "Continue"
$baza = if ($Baza) { $Baza } else { Join-Path $env:LOCALAPPDATA "RenditesiFotove" }
$baza = [IO.Path]::GetFullPath($baza).TrimEnd('\')
$pyDir = Join-Path $baza "python"
$dataDir = Join-Path $baza "data"
$uninstKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$RegKey"

function Hapi($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }
function Brenda($p) {  # a eshte shtegu brenda dosjes se instalimit?
    if (-not $p) { return $false }
    try { $f = [IO.Path]::GetFullPath($p) } catch { return $false }
    return $f.StartsWith($baza + '\', [StringComparison]::OrdinalIgnoreCase)
}
function NeKosh($p) {
    Add-Type -AssemblyName Microsoft.VisualBasic
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($p, 'OnlyErrorDialogs', 'SendToRecycleBin')
}

Write-Host "Renditesi i Fotove - cinstalimi" -ForegroundColor Cyan
if (-not (Test-Path $baza)) { Write-Host "Nuk u gjet asnje instalim te: $baza"; exit 0 }
Write-Host "Instalimi: $baza"
if (-not $Po) {
    $p = Read-Host "Ta cinstaloj Renditesin e Fotove? (p = po, cdo gje tjeter = jo)"
    if ($p -notmatch '^(p|po)$') { Write-Host "U anulua. Asgje nuk u fshi."; exit 0 }
}

# 1) Mbyll Renditesin (serveri, dritarja e Edge/Chrome me profilin e vet)
Hapi "1/5 Po mbyll Renditesin"
$st = Join-Path $baza "serveri.json"
if (Test-Path $st) {
    try { $s = Get-Content $st -Raw | ConvertFrom-Json; if ($s.pid) { Stop-Process -Id $s.pid -Force -ErrorAction SilentlyContinue } } catch {}
}
$all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
$vete = @{}  # ky cinstalim dhe proceset qe e nisen (cmd i .bat-it, "Aplikacionet e instaluara"): mos i mbyll
$id = [int]$PID  # [int] gjithandej: ProcessId vjen si UInt32 dhe celesat e ndryshem nuk perputhen
while ($id -and -not $vete.ContainsKey($id)) {
    $vete[$id] = $true
    $id = [int](($all | Where-Object { [int]$_.ProcessId -eq $id } | Select-Object -First 1).ParentProcessId)
}
$me = $all | Where-Object {
    (Brenda $_.ExecutablePath) -or ($_.CommandLine -and $_.CommandLine.IndexOf($baza, [StringComparison]::OrdinalIgnoreCase) -ge 0)
} | Where-Object { -not $vete.ContainsKey([int]$_.ProcessId) }
foreach ($p in $me) {
    Write-Host ("  mbyll: " + $p.Name + " (" + $p.ProcessId + ")")
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 1

# 2) Ikonat: vetem ato qe tregojne te ky instalim (jo kopje te tjera te programit)
Hapi "2/5 Ikonat"
$vende = @(
    $(if ($Desktop) { $Desktop } else { [Environment]::GetFolderPath("Desktop") }),
    $(if ($StartMenu) { $StartMenu } else { Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs" })
)
$sh = New-Object -ComObject WScript.Shell
foreach ($v in $vende) {
    $lnk = Join-Path $v "Renditesi i Fotove.lnk"
    if (Test-Path $lnk) {
        $t = $sh.CreateShortcut($lnk)
        if ((Brenda $t.TargetPath) -or (Brenda $t.WorkingDirectory)) { Remove-Item $lnk -Force; Write-Host "  u hoq: $lnk" }
        else { Write-Host "  u la (tregon gjetke): $lnk" }
    }
}

# 3) Python-i i instaluesit: menyra e rregullt e Windows-it, qe te mos mbetet te "Aplikacionet e instaluara"
Hapi "3/5 Python"
$pyOk = $false
foreach ($k in Get-ChildItem "HKCU:\Software\Python\PythonCore" -ErrorAction SilentlyContinue) {
    $ip = (Get-ItemProperty (Join-Path $k.PSPath "InstallPath") -ErrorAction SilentlyContinue).'(default)'
    if ($ip -and ([IO.Path]::GetFullPath($ip).TrimEnd('\') -ieq $pyDir)) { $pyOk = $true; $pyVer = $k.PSChildName }
}
if ($pyOk) {
    $bundle = Get-ChildItem "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall" -ErrorAction SilentlyContinue |
        ForEach-Object { Get-ItemProperty $_.PSPath } |
        Where-Object { $_.DisplayName -like "Python $pyVer*" -and $_.QuietUninstallString } | Select-Object -First 1
    if ($bundle) {
        Write-Host ("  po cinstaloj: " + $bundle.DisplayName + " (pak minuta)...")
        Start-Process -FilePath "cmd.exe" -ArgumentList ('/c "' + $bundle.QuietUninstallString + '"') -Wait -WindowStyle Hidden
    } else { Write-Host "  regjistrimi i Python-it nuk u gjet: do te fshihet vetem dosja" }
} else { Write-Host "  asnje Python i ketij instalimi (Python-et e tjera nuk preken)" }

# 4) Kodi, Python-i, dritarja; te dhenat sipas zgjedhjes
Hapi "4/5 Dosjet"
$mbaj = $true
if ($FshiTeDhenat) { $mbaj = $false }
elseif (-not $MbajTeDhenat -and (Test-Path $dataDir)) {
    Write-Host "Te dhenat e tua: emrat e fytyrave, pema e lidhjeve, historiku i skanimeve ($dataDir)."
    $p = Read-Host "Do t'i mbash per nje instalim te ardhshem? (Enter/p = po, mbaji; f = fshiji, shkojne te Koshi)"
    if ($p -match '^(f|fshi|fshiji)$') { $mbaj = $false }
}
foreach ($d in Get-ChildItem $baza -Force) {
    if ($d.FullName -ieq $dataDir) { continue }
    Remove-Item $d.FullName -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $d.FullName) { Write-Host ("  nuk u fshi plotesisht (ndoshta eshte i hapur): " + $d.FullName) -ForegroundColor Yellow }
    else { Write-Host ("  u fshi: " + $d.Name) }
}
if (Test-Path $dataDir) {
    if ($mbaj) { Write-Host "  te dhenat u mbajten: $dataDir" -ForegroundColor Green }
    else { NeKosh $dataDir; Write-Host "  te dhenat u cuan te Koshi (mund t'i rikthesh prej andej)" }
}
if (-not (Get-ChildItem $baza -Force -ErrorAction SilentlyContinue)) { Remove-Item $baza -Force -ErrorAction SilentlyContinue }

# 5) "Aplikacionet e instaluara"
Hapi "5/5 Regjistrimi ne Windows"
if (Test-Path $uninstKey) { Remove-Item $uninstKey -Recurse -Force; Write-Host "  u hoq nga 'Aplikacionet e instaluara'" }
else { Write-Host "  nuk ishte i regjistruar" }

Write-Host ""
Write-Host "Gati! Renditesi i Fotove u cinstalua. Fotot e tua origjinale nuk u preken." -ForegroundColor Green
