@echo off
chcp 65001 >nul
title MIDAS MCP 管理器 · Web 版
cd /d "%~dp0.."
echo ============================================================
echo  MIDAS MCP 管理器 · Web 版服务端
echo  访问地址: http://127.0.0.1:8765/
echo  访问地址: http://127.0.0.1:8790/
echo  (若端口被占用，请修改下面的 --port)
echo  关闭本窗口即停止服务
echo ============================================================
python -m uvicorn server.app.main:app --host 0.0.0.0 --port 8790
pause
