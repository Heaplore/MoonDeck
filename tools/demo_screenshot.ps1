# MoonDeck integrated demo screenshot
# 1) Launch MoonDeck (background)
# 2) Wait for canvas+cards to settle
# 3) Screenshot full screen
# 4) Kill MoonDeck

param(
    [int]$WaitSeconds = 4,
    [string]$OutPath = "C:\Users\Administrator\.easyclaw\workspace\tools\desktop-canvas\demo_run.png"
)

$ErrorActionPreference = "Stop"
$ProjectDir = "C:\Users\Administrator\.easyclaw\workspace\tools\desktop-canvas"
$LogFile = Join-Path $ProjectDir "logs\demo_run.log"
$PythonExe = "C:\Users\Administrator\AppData\Local\easyclaw\ai\tool_cache\resources\tools\win\python-3.11.9\python.exe"

function Stop-MoDeck {
    Get-Process python -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $PythonExe } |
        ForEach-Object {
            try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
}

# Pre-clean
Stop-MoDeck
Start-Sleep -Seconds 1

# Check deps: try a quick import via redirected stderr
$need = @("PyQt6", "PyYAML")
$missing = @()
foreach ($pkg in $need) {
    $stderr_file = [System.IO.Path]::GetTempFileName()
    $stdout_file = [System.IO.Path]::GetTempFileName()
    $p = Start-Process -FilePath $PythonExe -ArgumentList @("-c","import $pkg") `
        -RedirectStandardOutput $stdout_file -RedirectStandardError $stderr_file `
        -PassThru -Wait -NoNewWindow
    if ($p.ExitCode -ne 0) { $missing += $pkg }
    Remove-Item $stderr_file -Force -ErrorAction SilentlyContinue
    Remove-Item $stdout_file -Force -ErrorAction SilentlyContinue
}
if ($missing.Count -gt 0) {
    Write-Host "[demo] Missing pkgs: $($missing -join ', '), installing..." -ForegroundColor Yellow
    $install_log = Join-Path $ProjectDir "logs\demo_install.log"
    $install_err = Join-Path $ProjectDir "logs\demo_install.err"
    $argList = @("-m","pip","install") + $missing
    $ip = Start-Process -FilePath $PythonExe -ArgumentList $argList `
        -RedirectStandardOutput $install_log -RedirectStandardError $install_err `
        -PassThru -Wait -NoNewWindow
    Write-Host "[demo] pip install exit=$($ip.ExitCode)" -ForegroundColor Gray
}

# Force UTF-8 for child process (so Chinese log lines work)
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = $ProjectDir

Write-Host "[demo] Launching MoonDeck in background..." -ForegroundColor Cyan
$proc = Start-Process -FilePath $PythonExe `
    -ArgumentList @("-X","utf8","main.py","--debug") `
    -WorkingDirectory $ProjectDir `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError "$LogFile.err" `
    -PassThru -WindowStyle Hidden

Write-Host "[demo] PID=$($proc.Id), waiting ${WaitSeconds}s..." -ForegroundColor Cyan
Start-Sleep -Seconds $WaitSeconds

# Check if still alive
if ($proc.HasExited) {
    Write-Host "[demo] FAIL: MoonDeck exited. Code=$($proc.ExitCode). Log:" -ForegroundColor Red
    if (Test-Path $LogFile) { Get-Content $LogFile -Tail 40 }
    if (Test-Path "$LogFile.err") { Get-Content "$LogFile.err" -Tail 20 }
    exit 1
}

# Screenshot
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$gfx = [System.Drawing.Graphics]::FromImage($bmp)
$gfx.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bmp.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
$gfx.Dispose()
$bmp.Dispose()

$file = Get-Item $OutPath
Write-Host "[demo] Screenshot saved: $($file.FullName) ($($file.Length) bytes, $($bounds.Width)x$($bounds.Height))" -ForegroundColor Green

# Shutdown
Write-Host "[demo] Stopping MoonDeck..." -ForegroundColor Cyan
try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
Start-Sleep -Seconds 1
Stop-MoDeck

Write-Host "[demo] Done." -ForegroundColor Green
exit 0
