# MoonDeck 月坞 - 开发启动脚本
# 用途：开发模式下启动 MoonDeck

[CmdletBinding()]
param(
    [switch]$NoVenv,
    [switch]$Reset
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "🌙 MoonDeck 月坞 - 开发启动" -ForegroundColor Cyan
Write-Host "项目根: $root" -ForegroundColor Gray

# venv 处理
$venvPath = Join-Path $root ".venv"
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"

if ($Reset -and (Test-Path $venvPath)) {
    Write-Host "[Reset] 删除旧 venv..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $venvPath
}

if (-not $NoVenv) {
    if (-not (Test-Path $activateScript)) {
        Write-Host "[Venv] 创建虚拟环境..." -ForegroundColor Yellow
        python -m venv $venvPath
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] venv 创建失败" -ForegroundColor Red
            exit 1
        }
    }
    Write-Host "[Venv] 激活虚拟环境..." -ForegroundColor Green
    & $activateScript
}

# 依赖检查
$reqFile = Join-Path $root "requirements.txt"
if (Test-Path $reqFile) {
    Write-Host "[Deps] 安装/更新依赖..." -ForegroundColor Yellow
    python -m pip install -r $reqFile --quiet
}

# 启动
Write-Host "[Run] 启动 MoonDeck..." -ForegroundColor Green
Write-Host ""
python main.py
