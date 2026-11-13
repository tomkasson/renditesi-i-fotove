# Krijon ikonat e Renditesit te Fotove: ne Desktop dhe ne menune Start.
# Ikona hap Renditesi.pyw me pythonw (pa dritaren e zeze), nga mjedisi .venv i kesaj dosjeje.
param([string]$AppDir = $PSScriptRoot)

$pyw = Join-Path $AppDir ".venv\Scripts\pythonw.exe"
$launcher = Join-Path $AppDir "Renditesi.pyw"
$icon = Join-Path $AppDir "renditesi.ico"
if (-not (Test-Path $pyw)) { Write-Host "Mungon $pyw (instalimi nuk ka mbaruar?)"; exit 1 }

$sh = New-Object -ComObject WScript.Shell
$vende = @([Environment]::GetFolderPath("Desktop"), (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"))
foreach ($v in $vende) {
    $lnk = $sh.CreateShortcut((Join-Path $v "Renditesi i Fotove.lnk"))
    $lnk.TargetPath = $pyw
    $lnk.Arguments = '"' + $launcher + '"'
    $lnk.WorkingDirectory = $AppDir
    $lnk.IconLocation = $icon
    $lnk.Description = "Renditesi i Fotove: fotot, personat dhe pema e lidhjeve"
    $lnk.Save()
    Write-Host ("Ikona u krijua: " + (Join-Path $v "Renditesi i Fotove.lnk"))
}
