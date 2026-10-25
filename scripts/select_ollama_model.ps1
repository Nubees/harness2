param(
    [string]$OutputFile = ""
)

$ErrorActionPreference = "SilentlyContinue"

Write-Host "Connecting to Ollama (http://localhost:11434)..." -ForegroundColor Cyan
try {
    $res = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop
    $allModels = $res.models
} catch {
    Write-Host "[WARNING] Could not connect to Ollama server at http://localhost:11434" -ForegroundColor Yellow
    Write-Host "Make sure Ollama is running." -ForegroundColor Yellow
    $allModels = @()
}

$cloudModels = @()
$localModels = @()

foreach ($m in $allModels) {
    if ($m.name -match ":cloud$" -or $m.size -lt 1000) {
        $cloudModels += $m
    } else {
        $localModels += $m
    }
}

$recommendedLibraryModels = @(
    "qwen3-coder:480b-cloud",
    "deepseek-v3.1:671b-cloud",
    "gpt-oss:120b-cloud",
    "kimi-k2.7-code:cloud",
    "qwen3-coder:30b",
    "qwen2.5-coder:32b",
    "llama3.3:70b",
    "deepseek-coder-v2:16b"
)

# Filter out recommended models that are already installed
$recommendedToPull = @()
foreach ($rec in $recommendedLibraryModels) {
    $exists = $allModels | Where-Object { $_.name -eq $rec }
    if (-not $exists) {
        $recommendedToPull += $rec
    }
}

Write-Host ""
Write-Host "=================== AVAILABLE OLLAMA MODELS ===================" -ForegroundColor Green

$index = 1
$menuMap = @{}

if ($cloudModels.Count -gt 0) {
    Write-Host "`n--- CLOUD MODELS (Configured in Ollama) ---" -ForegroundColor Cyan
    foreach ($m in $cloudModels) {
        Write-Host ("  [{0}] {1}" -f $index, $m.name) -ForegroundColor White
        $menuMap[$index] = @{ Name = $m.name; IsInstalled = $true }
        $index++
    }
}

if ($localModels.Count -gt 0) {
    Write-Host "`n--- LOCAL ON-DEVICE MODELS ---" -ForegroundColor Cyan
    foreach ($m in $localModels) {
        $gb = [math]::Round($m.size / 1GB, 2)
        Write-Host ("  [{0}] {1,-24} ({2} GB)" -f $index, $m.name, $gb) -ForegroundColor White
        $menuMap[$index] = @{ Name = $m.name; IsInstalled = $true }
        $index++
    }
}

if ($recommendedToPull.Count -gt 0) {
    Write-Host "`n--- AVAILABLE TO PULL (Ollama Cloud Library) ---" -ForegroundColor Yellow
    foreach ($rec in $recommendedToPull) {
        Write-Host ("  [{0}] {1,-24} [Requires download]" -f $index, $rec) -ForegroundColor Gray
        $menuMap[$index] = @{ Name = $rec; IsInstalled = $false }
        $index++
    }
}

Write-Host "`n==============================================================" -ForegroundColor Green
$maxIndex = $index - 1

function Get-SafeInput {
    try {
        if ([System.Console]::IsInputRedirected) {
            return [System.Console]::In.ReadLine()
        }
        return (Read-Host)
    } catch {
        return ""
    }
}

$defaultChoice = 1
$prompt = "Select a model [1-$maxIndex] or type a model name (Default: [{0}] {1}): " -f $defaultChoice, $menuMap[$defaultChoice].Name
Write-Host $prompt -NoNewline -ForegroundColor Yellow
$selection = Get-SafeInput

if ([string]::IsNullOrWhiteSpace($selection)) {
    $selectedModel = $menuMap[$defaultChoice].Name
    $isInstalled = $menuMap[$defaultChoice].IsInstalled
} elseif ($selection -as [int] -and $menuMap.ContainsKey([int]$selection)) {
    $choiceNum = [int]$selection
    $selectedModel = $menuMap[$choiceNum].Name
    $isInstalled = $menuMap[$choiceNum].IsInstalled
} else {
    $selectedModel = $selection.Trim()
    $installedMatch = $allModels | Where-Object { $_.name -eq $selectedModel }
    $isInstalled = [bool]$installedMatch
}

if (-not $isInstalled) {
    Write-Host "`nModel '$selectedModel' is not downloaded yet." -ForegroundColor Yellow
    Write-Host "Do you want to download/pull it now via 'ollama pull $selectedModel'? [y/N]: " -NoNewline -ForegroundColor Yellow
    $pullAnswer = Get-SafeInput
    if ($pullAnswer -match "^[yY]") {
        Write-Host "Pulling $selectedModel from Ollama library..." -ForegroundColor Cyan
        & ollama pull $selectedModel
    }
}

Write-Host "`nSelected Model: $selectedModel" -ForegroundColor Green

if ($OutputFile) {
    $fullPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputFile)
    [System.IO.File]::WriteAllText($fullPath, $selectedModel)
}
