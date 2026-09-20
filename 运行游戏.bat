@echo off
chcp 65001 >nul
title 一箭又一箭
cd /d "%~dp0"
echo ============================================
echo   一箭又一箭 - 环境检查与启动
echo ============================================
python --version
if errorlevel 1 (
  echo [错误] 未检测到 Python，请先安装 Python 3.10+ 并勾选 Add to PATH。
  pause
  exit /b 1
)
echo.
echo [1/2] 检查 / 安装依赖库 pygame、numpy ...
python -m pip install pygame numpy -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
  echo [错误] 依赖安装失败，请检查网络后重试。
  pause
  exit /b 1
)
echo.
echo [2/2] 启动游戏 ...
python main.py
pause
