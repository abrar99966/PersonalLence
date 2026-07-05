# Download the standalone Go binaries (gosearch, phoneinfoga) into ./bin.
# These are not committed to git (see .gitignore). Run once after cloning.
$ErrorActionPreference = "Stop"
$bin = Join-Path $PSScriptRoot "..\bin"
New-Item -ItemType Directory -Force -Path $bin | Out-Null

Write-Host "Downloading gosearch.exe..."
Invoke-WebRequest -Uri "https://github.com/ibnaleem/gosearch/releases/latest/download/gosearch.exe" `
    -OutFile (Join-Path $bin "gosearch.exe")

Write-Host "Downloading phoneinfoga..."
$tar = Join-Path $env:TEMP "phoneinfoga.tar.gz"
Invoke-WebRequest -Uri "https://github.com/sundowndev/phoneinfoga/releases/latest/download/phoneinfoga_Windows_x86_64.tar.gz" `
    -OutFile $tar
tar -xzf $tar -C $bin phoneinfoga.exe
Remove-Item $tar -Force

Write-Host "Done. Binaries in $bin"
