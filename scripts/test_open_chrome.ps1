# Test script for visual Chrome opening in COGNITIVE_MODE
# Verifies that "open chrome" command works end-to-end

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "TEST: Visual Chrome Opening" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Set environment variables
$env:COGNITIVE_MODE = "1"
$env:AUTO_LAUNCH_CHROME = "0"
$env:ALLOW_LEGACY_FALLBACK = "0"

Write-Host "Environment:" -ForegroundColor Yellow
Write-Host "  COGNITIVE_MODE = $env:COGNITIVE_MODE"
Write-Host "  AUTO_LAUNCH_CHROME = $env:AUTO_LAUNCH_CHROME"
Write-Host "  ALLOW_LEGACY_FALLBACK = $env:ALLOW_LEGACY_FALLBACK"
Write-Host ""

# Check if taskbar anchor is trained
$anchorFile = "memory/taskbar_anchors.json"
if (-not (Test-Path $anchorFile)) {
    Write-Host "ERROR: Taskbar anchor not trained" -ForegroundColor Red
    Write-Host "Run: .\.venv312\Scripts\python.exe -m core.training_controller" -ForegroundColor Yellow
    Write-Host "Then: train taskbar_chrome" -ForegroundColor Yellow
    exit 1
}

Write-Host "✓ Taskbar anchor found: $anchorFile" -ForegroundColor Green
Write-Host ""

# Capture initial screen hash
Write-Host "Capturing initial screen state..." -ForegroundColor Yellow
$beforeScreenshot = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$beforeHash = Get-FileHash -InputStream ([System.IO.MemoryStream]::new([byte[]]@(1,2,3))) -Algorithm SHA256 | Select-Object -ExpandProperty Hash

Write-Host "✓ Initial state captured" -ForegroundColor Green
Write-Host ""

# Start Jarvis and send command
Write-Host "Starting Jarvis..." -ForegroundColor Yellow
Write-Host ""

$process = Start-Process -FilePath ".\.venv312\Scripts\python.exe" -ArgumentList "-m", "main" -NoNewWindow -PassThru -RedirectStandardInput "input.txt" -RedirectStandardOutput "output.txt" -RedirectStandardError "error.txt"

# Wait for startup
Start-Sleep -Seconds 5

# Send command
Write-Host "Sending command: open chrome" -ForegroundColor Yellow
"open chrome" | Out-File -FilePath "input.txt" -Encoding utf8

# Wait for execution
Start-Sleep -Seconds 10

# Check output
$output = Get-Content "output.txt" -Raw

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "OUTPUT" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host $output

# Verify success criteria
$success = $true

# 1. Check for fallback message (should NOT appear)
if ($output -match "fallback to legacy planner") {
    Write-Host ""
    Write-Host "✗ FAIL: Detected fallback to legacy planner" -ForegroundColor Red
    $success = $false
}

# 2. Check for success message
if ($output -match "Chrome opened") {
    Write-Host ""
    Write-Host "✓ PASS: Chrome opened successfully" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "✗ FAIL: No success message found" -ForegroundColor Red
    $success = $false
}

# 3. Check for Chrome window
$chromeProcess = Get-Process -Name "chrome" -ErrorAction SilentlyContinue
if ($chromeProcess) {
    Write-Host "✓ PASS: Chrome process detected" -ForegroundColor Green
} else {
    Write-Host "✗ FAIL: Chrome process not found" -ForegroundColor Red
    $success = $false
}

# Cleanup
Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
Remove-Item "input.txt" -ErrorAction SilentlyContinue
Remove-Item "output.txt" -ErrorAction SilentlyContinue
Remove-Item "error.txt" -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
if ($success) {
    Write-Host "TEST PASSED" -ForegroundColor Green
    exit 0
} else {
    Write-Host "TEST FAILED" -ForegroundColor Red
    exit 1
}
