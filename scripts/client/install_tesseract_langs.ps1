$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
Set-Location $ProjectRoot

param(
    [string]$Langs = "ukr eng"
)

$tesseract = Get-Command tesseract -ErrorAction SilentlyContinue
if (-not $tesseract) {
    throw "Tesseract is not installed or not available in PATH."
}

$exePath = $tesseract.Source
$installRoot = Split-Path $exePath -Parent
$tessdata = Join-Path $installRoot "tessdata"
if (-not (Test-Path $tessdata)) {
    throw "Could not locate tessdata directory next to tesseract.exe: $tessdata"
}

$normalized = ($Langs -replace "\+", " " -replace ",", " ").Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries)
if (-not $normalized.Count) {
    throw "No language codes were provided."
}

foreach ($lang in $normalized) {
    $target = Join-Path $tessdata "$lang.traineddata"
    if (Test-Path $target) {
        Write-Host "[Aiya] OCR language already present: $lang" -ForegroundColor Green
        continue
    }
    $url = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/$lang.traineddata"
    Write-Host "[Aiya] Downloading OCR language pack: $lang" -ForegroundColor Cyan
    Invoke-WebRequest -Uri $url -OutFile $target
}

Write-Host "[Aiya] OCR language packs are ready." -ForegroundColor Green
