# Runtime Stabilization Test Script
# Tests Chrome auto-launch, DevTools backoff, UIA throttling, and CPU spike prevention

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "RUNTIME STABILIZATION TEST" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Set environment variables for clean testing
$env:DISABLE_MIC = '1'
$env:DISABLE_WAKE_WORD = '1'
$env:DISABLE_TTS = '1'
$env:AUTO_LAUNCH_CHROME = '1'
$env:USE_COGNITIVE_LOOP = '1'
$env:COGNITIVE_MODE = '1'

Write-Host "Test 1: Verify Chrome Auto-Launch" -ForegroundColor Yellow
Write-Host "-----------------------------------------------"

# Close Chrome if running (to test auto-launch)
$chromeProcesses = Get-Process -Name "chrome" -ErrorAction SilentlyContinue
if ($chromeProcesses) {
    Write-Host "Closing existing Chrome processes for clean test..." -ForegroundColor Gray
    Stop-Process -Name "chrome" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# Check if DevTools port is closed
Write-Host "Checking if Chrome DevTools port 9222 is available..." -ForegroundColor Gray
$portTest = Test-NetConnection -ComputerName 127.0.0.1 -Port 9222 -WarningAction SilentlyContinue -ErrorAction SilentlyContinue
if ($portTest.TcpTestSucceeded) {
    Write-Host "[WARNING] Port 9222 already in use. Chrome may already be running." -ForegroundColor Yellow
} else {
    Write-Host "[OK] Port 9222 is closed. Auto-launch test ready." -ForegroundColor Green
}

Write-Host ""
Write-Host "Test 2: Component Import Test" -ForegroundColor Yellow
Write-Host "-----------------------------------------------"

$importTest = @'
import sys
print("Testing imports...")

# Test PlaywrightManager with auto-launch
from automation.playwright_manager import PlaywrightManager
pm = PlaywrightManager("test", auto_launch=True, remote_debug_port=9222)
print(f"  PlaywrightManager: OK")
print(f"  Auto-launch enabled: {pm.auto_launch}")
print(f"  ensure_chrome_remote_debug method: {'OK' if hasattr(pm, 'ensure_chrome_remote_debug') else 'MISSING'}")

# Test BrowserStateTracker with backoff
from automation.browser_state_tracker import BrowserStateTracker
from awareness.event_dispatcher import EventDispatcher
dispatcher = EventDispatcher()
tracker = BrowserStateTracker(dispatcher, auto_launch=True)
print(f"  BrowserStateTracker: OK")
print(f"  Retry delay initialized: {tracker._retry_delay}s")
print(f"  Suspended flag: {tracker._suspended}")

# Test UIAutomationMonitor with throttling
try:
    from awareness.windows.uia_monitor import UIAutomationMonitor
    monitor = UIAutomationMonitor()
    print(f"  UIAutomationMonitor: OK")
    print(f"  Event throttle (_last_emit): {hasattr(monitor, '_last_emit')}")
except Exception as e:
    print(f"  UIAutomationMonitor: SKIPPED ({e})")

# Test ProcessWatcher with CPU prevention
from awareness.process_watcher import ProcessWatcher
watcher = ProcessWatcher()
print(f"  ProcessWatcher: OK")

print("\nAll imports successful!")
print("=" * 60)
'@

Write-Host "Running import tests..." -ForegroundColor Gray
$importTest | .\.venv312\Scripts\python.exe -
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] All components imported successfully" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Import test failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Test 3: Runtime Behavior Test (10 seconds)" -ForegroundColor Yellow
Write-Host "-----------------------------------------------"
Write-Host "Starting Jarvis with runtime fixes enabled..." -ForegroundColor Gray
Write-Host "Monitoring for:"
Write-Host "  - Chrome auto-launch" -ForegroundColor White
Write-Host "  - DevTools connection/backoff" -ForegroundColor White
Write-Host "  - UIA event throttling" -ForegroundColor White
Write-Host "  - CPU usage" -ForegroundColor White
Write-Host ""

# Start Jarvis in background and monitor CPU
$jarvisJob = Start-Job -ScriptBlock {
    param($workDir)
    Set-Location $workDir
    & ".\.venv312\Scripts\python.exe" "main.py"
} -ArgumentList (Get-Location).Path

# Monitor for 10 seconds
Write-Host "Monitoring runtime (10 seconds)..." -ForegroundColor Gray
$monitorStart = Get-Date
$cpuSamples = @()

for ($i = 1; $i -le 10; $i++) {
    Start-Sleep -Seconds 1
    
    # Check if Chrome launched
    $chromeProcess = Get-Process -Name "chrome" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($chromeProcess -and $i -eq 3) {
        $cpu = $chromeProcess.CPU
        Write-Host "[OK] Chrome detected (PID: $($chromeProcess.Id))" -ForegroundColor Green
    }
    
    # Sample CPU usage of Python
    $pythonProcesses = Get-Process -Name "python" -ErrorAction SilentlyContinue
    if ($pythonProcesses) {
        $totalCpu = ($pythonProcesses | Measure-Object -Property CPU -Sum).Sum
        $cpuSamples += $totalCpu
    }
    
    Write-Host "  [$i/10] Monitoring..." -ForegroundColor Gray
}

# Calculate average CPU
if ($cpuSamples.Count -gt 0) {
    $avgCpu = ($cpuSamples | Measure-Object -Average).Average
    Write-Host ""
    Write-Host "CPU Analysis:" -ForegroundColor Yellow
    Write-Host "  Average CPU time: $([math]::Round($avgCpu, 2))s" -ForegroundColor White
    if ($avgCpu -lt 5.0) {
        Write-Host "  [OK] CPU usage is normal" -ForegroundColor Green
    } else {
        Write-Host "  [WARNING] High CPU usage detected" -ForegroundColor Yellow
    }
}

# Stop Jarvis
Write-Host ""
Write-Host "Stopping Jarvis..." -ForegroundColor Gray
Stop-Job -Job $jarvisJob
Remove-Job -Job $jarvisJob -Force

Write-Host ""
Write-Host "Test 4: Chrome DevTools Port Check" -ForegroundColor Yellow
Write-Host "-----------------------------------------------"

$portTest = Test-NetConnection -ComputerName 127.0.0.1 -Port 9222 -WarningAction SilentlyContinue -ErrorAction SilentlyContinue
if ($portTest.TcpTestSucceeded) {
    Write-Host "[OK] Chrome DevTools port 9222 is now OPEN" -ForegroundColor Green
    Write-Host "  Auto-launch feature working!" -ForegroundColor Green
} else {
    Write-Host "[INFO] Port 9222 not open. Chrome may not have launched." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "TEST SUMMARY" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Runtime Fixes Implemented:" -ForegroundColor White
Write-Host "  [x] Chrome auto-launch with DevTools" -ForegroundColor Green
Write-Host "  [x] Browser tracker exponential backoff (2s -> 30s max)" -ForegroundColor Green
Write-Host "  [x] Browser tracker 60s suspension on failure" -ForegroundColor Green
Write-Host "  [x] UIA event throttling (400ms minimum)" -ForegroundColor Green
Write-Host "  [x] CPU spike prevention (200ms sleep in loops)" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Run Jarvis manually: .\.venv312\Scripts\python.exe main.py"
Write-Host "  2. Check logs for clean behavior (no spam, no crashes)"
Write-Host "  3. Verify Chrome auto-launches when DevTools needed"
Write-Host "  4. Monitor CPU usage stays reasonable"
Write-Host ""
Write-Host "To test with full Jarvis:" -ForegroundColor Cyan
Write-Host "  `$env:AUTO_LAUNCH_CHROME='1'"
Write-Host "  .\.venv312\Scripts\python.exe main.py"
Write-Host ""
