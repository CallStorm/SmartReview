@echo off
chcp 65001 >nul
REM ============================================================
REM scripts\restore_proxy.bat
REM 手动恢复 Windows 系统代理到 Clash 默认设置
REM 当 push_no_proxy.bat 被异常中断（Ctrl+C / 任务管理器）、
REM 代理可能停在关闭状态时，用这个脚本手动恢复。
REM ============================================================

echo [代理管理] 恢复 Clash 系统代理（127.0.0.1:7897）...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 1 /f
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer /t REG_SZ /d "http=127.0.0.1:7897;https=127.0.0.1:7897" /f
netsh winhttp set proxy proxy-server="http=127.0.0.1:7897"
echo [代理管理] 已恢复