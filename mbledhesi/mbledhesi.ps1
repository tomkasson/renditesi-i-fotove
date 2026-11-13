# Mbledhesi i fotove - per PC-ne e vjeter (Windows 7, PowerShell 2.0, pa instalim).
# Gjen fotot (dhe sipas deshires videot) ne te gjithe disqet e PC-se dhe i kopjon ne USB-ne ku ndodhet ky skedar.
# Kur USB-ja mbushet: fut USB-ne tjeter, kopjo dosjen "mbledhesi" edhe aty, hape perseri: vazhdon nga aty ku mbeti.
# Cfare u kopjua mbahet mend ne PC-ne e vjeter: %USERPROFILE%\Mbledhesi\kopjuar.txt
# Mesazhet jane pa shkronjat e / c me pika, qe te lexohen mire ne konsolen e Windows 7.

param(
    [string[]]$Burimet = @(),     # dosjet/disqet per kerkim (bosh = te gjithe disqet e brendshem)
    [string]$Dest = "",           # ku kopjohen (bosh = rrenja e USB-se ku ndodhet ky skedar)
    [string]$Progresi = "",       # ku mbahet mend cfare u kopjua (bosh = %USERPROFILE%\Mbledhesi)
    [long]$MaksBytes = 0,         # vetem per prova: sa bajt "nxe" USB-ja
    [string]$Videot = ""          # "p" / "j": pa pyetje (per prova)
)

$ErrorActionPreference = "Continue"
$IMG = @(".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".bmp", ".tif", ".tiff")
$VID = @(".mp4", ".mov", ".m4v", ".3gp", ".avi", ".mkv", ".wmv", ".mpg", ".mpeg", ".mts")
$SKIP = @("appdata", "windows", "program files", "program files (x86)", "programdata", "system volume information",
          "node_modules", "site-packages", "venv", "steamapps", "steamlibrary", "epic games", "recovery", "perflogs",
          "msocache", "intel", "drivers", "fotot nga pc i vjeter", "mbledhesi")
$MIN_IMG = 20KB      # me te vogla = ikona/miniatura, jo foto
$REZERVE = 50MB      # hapesire qe lihet e lire ne USB

function Shkruaj($tekst, $ngjyra) {
    if ($ngjyra) { Write-Host $tekst -ForegroundColor $ngjyra } else { Write-Host $tekst }
}

function Madhesia($b) {
    if ($b -ge 1GB) { return "{0:N1} GB" -f ($b / 1GB) }
    return "{0:N0} MB" -f ($b / 1MB)
}

# ---------------- ku jemi ----------------
$skedari = $MyInvocation.MyCommand.Path
$usbRoot = Split-Path $skedari -Qualifier                  # p.sh. "F:"
if (-not $Dest) { $Dest = $usbRoot + "\" }
$destDir = Join-Path $Dest "Fotot nga PC i vjeter"
if (-not $Progresi) { $Progresi = Join-Path $env:USERPROFILE "Mbledhesi" }
if (-not (Test-Path $Progresi)) { New-Item -ItemType Directory -Path $Progresi | Out-Null }
$fileKopjuar = Join-Path $Progresi "kopjuar.txt"
$fileZgjedhja = Join-Path $Progresi "videot.txt"
$fileNr = Join-Path $Progresi "usb_nr.txt"
$fileLog = Join-Path $Progresi "ditari.txt"

Shkruaj ""
Shkruaj "=== Mbledhesi i fotove ===" Cyan
Shkruaj "Kerkon fotot ne kete PC dhe i kopjon ne: $destDir"
Shkruaj ""

# ---------------- videot: po apo jo (pyetet vetem heren e pare) ----------------
if (-not $Videot) {
    if (Test-Path $fileZgjedhja) { $Videot = (Get-Content $fileZgjedhja | Select-Object -First 1).Trim() }
    else {
        $Videot = Read-Host "Te kopjohen edhe videot? Fotot kopjohen te parat, videot pas tyre. (p = po / j = jo)"
        $Videot = $Videot.Trim().ToLower()
        if ($Videot -ne "p") { $Videot = "j" }
        Set-Content -Path $fileZgjedhja -Value $Videot
    }
}
$meVideo = ($Videot -eq "p")

# ---------------- cfare eshte kopjuar me pare ----------------
$bere = @{}
if (Test-Path $fileKopjuar) {
    foreach ($l in [IO.File]::ReadAllLines($fileKopjuar)) { if ($l) { $bere[$l] = $true } }
}
Shkruaj ("Te kopjuara me pare: {0} skedare" -f $bere.Count)

# ---------------- ku kerkohet ----------------
if ($Burimet.Count -eq 0) {
    foreach ($d in [IO.DriveInfo]::GetDrives()) {
        if ($d.IsReady -and $d.DriveType -eq "Fixed" -and $d.Name.Substring(0, 2) -ne $usbRoot) { $Burimet += $d.Name }
    }
}
Shkruaj ("Disqet/dosjet: " + ($Burimet -join ", "))
Shkruaj "Po kerkoj fotot... (mund te zgjase disa minuta)" Yellow

$listaFoto = New-Object System.Collections.ArrayList   # (PowerShell nuk dallon $videot nga $Videot)
$listaVideo = New-Object System.Collections.ArrayList
$pare = @{}   # celesi i skedarit: e njejta foto ne dy vende kopjohet nje here
foreach ($burim in $Burimet) {
    $stack = New-Object System.Collections.Stack
    $stack.Push($burim)
    while ($stack.Count -gt 0) {
        $dir = $stack.Pop()
        try { $subs = [IO.Directory]::GetDirectories($dir) } catch { $subs = @() }
        foreach ($s in $subs) {
            $emri = [IO.Path]::GetFileName($s)
            if ($SKIP -contains $emri.ToLower() -or $emri.StartsWith(".") -or $emri.StartsWith("$")) { continue }
            try {
                $attr = [IO.File]::GetAttributes($s)
                if (($attr -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }  # lidhje te Windows-it: jo
            } catch { continue }
            $stack.Push($s)
        }
        try { $files = [IO.Directory]::GetFiles($dir) } catch { $files = @() }
        foreach ($f in $files) {
            $ext = [IO.Path]::GetExtension($f).ToLower()
            $eshteFoto = $IMG -contains $ext
            $eshteVideo = $VID -contains $ext
            if (-not ($eshteFoto -or ($meVideo -and $eshteVideo))) { continue }
            try { $fi = New-Object IO.FileInfo($f) } catch { continue }
            if ($eshteFoto -and $fi.Length -lt $MIN_IMG) { continue }
            $celes = ("{0}|{1}|{2}" -f $fi.Name.ToLower(), $fi.Length, $fi.LastWriteTimeUtc.Ticks)
            if ($pare.ContainsKey($celes)) { continue }
            $pare[$celes] = $true
            if ($bere.ContainsKey($celes)) { continue }
            if ($eshteFoto) { [void]$listaFoto.Add($fi) } else { [void]$listaVideo.Add($fi) }
        }
    }
}
$gjith = New-Object System.Collections.ArrayList
foreach ($x in $listaFoto) { [void]$gjith.Add($x) }
foreach ($x in $listaVideo) { [void]$gjith.Add($x) }
$sFoto = [long]0; foreach ($x in $listaFoto) { $sFoto += $x.Length }
$sVideo = [long]0; foreach ($x in $listaVideo) { $sVideo += $x.Length }

Shkruaj ""
Shkruaj ("Mbeten per kopjim: {0} foto ({1})" -f $listaFoto.Count, (Madhesia $sFoto)) Green
if ($meVideo) { Shkruaj ("                   {0} video ({1})" -f $listaVideo.Count, (Madhesia $sVideo)) Green }
if ($gjith.Count -eq 0) {
    Shkruaj ""
    Shkruaj "Gjithcka eshte kopjuar. Mbarove! Lidh USB-te me PC-ne e re (shih LEXOME.txt)." Cyan
    exit 0
}

# ---------------- USB-ja ----------------
$drive = New-Object IO.DriveInfo($Dest.Substring(0, 1))
$lire = $drive.AvailableFreeSpace
if ($MaksBytes -gt 0) { $lire = $MaksBytes }
$fat32 = ($drive.DriveFormat -eq "FAT32")
$teGjitha = $sFoto + $sVideo
if ($MaksBytes -gt 0) { $REZERVE = 100KB }   # prova me "USB" te vogel
$kapaciteti = [double]$drive.TotalSize
if ($MaksBytes -gt 0) { $kapaciteti = [double]$MaksBytes }
$sasUsb = [math]::Ceiling([double]$teGjitha / [math]::Max([double]1, $kapaciteti - $REZERVE))
Shkruaj ("Kjo USB ka te lire: {0}. Per gjithcka duhen rreth {1} USB si kjo." -f (Madhesia $lire), $sasUsb)
if ($fat32) { Shkruaj "Kujdes: USB-ja eshte FAT32: skedaret mbi 4 GB (video te gjata) nuk kopjohen dot ne te." Yellow }

$nr = 1
if (Test-Path $fileNr) { $nr = [int](Get-Content $fileNr | Select-Object -First 1) + 1 }
Shkruaj ("Kjo eshte USB-ja nr. {0}." -f $nr)
Shkruaj ""
Shkruaj "Po kopjoj... (mos e hiq USB-ne)" Yellow

if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir | Out-Null }
$md5 = [Security.Cryptography.MD5]::Create()
$kopjuar = 0; $bajt = [long]0; $mbetur = 0; $teMedha = 0; $gabime = 0
$shkruesi = New-Object IO.StreamWriter($fileKopjuar, $true)
$ditari = New-Object IO.StreamWriter($fileLog, $true)
$ditari.WriteLine(("--- {0} USB nr. {1}" -f (Get-Date), $nr))
$i = 0
foreach ($fi in $gjith) {
    $i++
    if ($fat32 -and $fi.Length -ge 4GB) { $teMedha++; $mbetur++; continue }
    if ($fi.Length + $REZERVE -gt $lire) { $mbetur++; continue }   # s'nxe: per USB-ne tjeter
    $rel = $fi.FullName.Substring(0, 1) + $fi.FullName.Substring(2)   # "D:\Foto\a.jpg" -> "D\Foto\a.jpg"
    $dst = Join-Path $destDir $rel
    if ($dst.Length -gt 240) {   # shteg shume i gjate per Windows: ne nje dosje te vecante
        $h = [BitConverter]::ToString($md5.ComputeHash([Text.Encoding]::UTF8.GetBytes($fi.FullName))).Replace("-", "").Substring(0, 8)
        $dst = Join-Path (Join-Path $destDir "_shtigje_te_gjata") ($h + "_" + $fi.Name)
    }
    try {
        $dd = Split-Path $dst -Parent
        if (-not (Test-Path -LiteralPath $dd)) { [void][IO.Directory]::CreateDirectory($dd) }
        $ka = (Test-Path -LiteralPath $dst) -and ((New-Object IO.FileInfo($dst)).Length -eq $fi.Length)
        if (-not $ka) { [IO.File]::Copy($fi.FullName, $dst, $true) }   # i paplote (u nderpre): rikopjohet
        [IO.File]::SetCreationTime($dst, $fi.CreationTime)
        [IO.File]::SetLastWriteTime($dst, $fi.LastWriteTime)
        $shkruesi.WriteLine(("{0}|{1}|{2}" -f $fi.Name.ToLower(), $fi.Length, $fi.LastWriteTimeUtc.Ticks))
        $kopjuar++; $bajt += $fi.Length; $lire -= $fi.Length
    } catch {
        $gabime++
        $ditari.WriteLine("GABIM: " + $fi.FullName + " :: " + $_.Exception.Message)
    }
    if ($i % 200 -eq 0) { Shkruaj ("  {0} nga {1} ({2})" -f $i, $gjith.Count, (Madhesia $bajt)) }
}
$shkruesi.Close()
$ditari.WriteLine(("kopjuar {0}, mbetur {1}, gabime {2}" -f $kopjuar, $mbetur, $gabime))
$ditari.Close()
if ($kopjuar -gt 0) { Set-Content -Path $fileNr -Value $nr }

$lexo = @"
Mbledhesi i fotove - USB nr. $nr
Ketu jane fotot e PC-se se vjeter, te dosja "Fotot nga PC i vjeter" (me dosjet origjinale: D\..., E\...).

Ne PC-ne e re:
1. Kopjo dosjen "Fotot nga PC i vjeter" nga cdo USB ne te njejtin vend ne PC-ne e re
   (p.sh. C:\Users\...\Fotot nga PC i vjeter). USB-te nuk mbishkruajne njera-tjetren.
2. Ne Renditesin e Fotove: Skano -> shto ate dosje -> Skano.
"@
Set-Content -Path (Join-Path $destDir "LEXOME.txt") -Value $lexo

Shkruaj ""
Shkruaj ("U kopjuan {0} skedare ({1}) ne USB-ne nr. {2}." -f $kopjuar, (Madhesia $bajt), $nr) Green
if ($gabime -gt 0) { Shkruaj ("{0} skedare nuk u kopjuan (shih {1})." -f $gabime, $fileLog) Yellow }
if ($teMedha -gt 0) { Shkruaj ("{0} video jane mbi 4 GB: duhet nje USB e formatuar NTFS ose exFAT." -f $teMedha) Yellow }
if ($mbetur -gt 0) {
    Shkruaj ""
    Shkruaj ("Mbeten edhe {0} skedare. Hiq kete USB, fut tjetren, kopjo aty dosjen 'mbledhesi' dhe hap perseri Mbledhesi.bat." -f $mbetur) Cyan
} else {
    Shkruaj ""
    Shkruaj "Gjithcka u kopjua. Mbarove! Lidh USB-te me PC-ne e re (shih LEXOME.txt ne USB)." Cyan
}
