@echo off
REM ============================================================
REM scripts\push_no_proxy.bat - Push Docker images with proxy off
REM ============================================================
REM Temporarily disable Windows system proxy (Clash Verge, etc.)
REM to push images to the internal registry (10.72.2.15:80).
REM After push completes, proxy is restored automatically.
REM
REM Why: Clash Verge may leave Windows system proxy active even
REM when its UI switch is OFF. Docker daemon then fails to reach
REM internal registry, returning a fake "authentication required"
REM error during push.
REM
REM Usage (in cmd):
REM   scripts\push_no_proxy.bat <image[:tag]> [<image[:tag]> ...]
REM
REM   Example:
REM     scripts\push_no_proxy.bat 10.72.2.15:80/review/smartreview-frontend:1.0.2
REM     scripts\push_no_proxy.bat 10.72.2.15:80/review/smartreview-backend:1.0.2
REM
REM Side effect: modifies Windows registry temporarily.
REM Auto-restores on completion. If interrupted (Ctrl+C / killed),
REM run scripts\restore_proxy.bat manually.
REM ============================================================

setlocal enabledelayedexpansion

REM --- arg check ---
if "%~1"=="" (
    echo Usage: %~nx0 ^<image[:tag]^> [...]
    exit /b 2
)

REM --- backup current proxy state ---
set BACKUP_FILE=%TEMP%\push_no_proxy_backup_%RANDOM%.txt
(
    echo === Backup at %DATE% %TIME% ===
    echo --- WinHTTP proxy ---
    netsh winhttp show proxy 2^>^&1
    echo --- Registry ProxyEnable ---
    reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable 2^>^&1
    echo --- Registry ProxyServer ---
    reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer 2^>^&1
) > "%BACKUP_FILE%"
echo [proxy-mgr] State backed up to %BACKUP_FILE%

REM --- disable proxy ---
echo [proxy-mgr] Disabling Windows system proxy...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul 2>&1
netsh winhttp reset proxy >nul 2>&1
echo [proxy-mgr] Proxy disabled

REM --- run push ---
REM Note: Harbor token negotiation can be flaky. If push fails with
REM "authentication required" but proxy is clearly disabled, just
REM run this script again. After 2-3 retries it usually works.
set PUSH_ERR=0
for %%I in (%*) do (
    echo.
    echo [push] docker push %%I
    docker push %%I
    if errorlevel 1 (
        set PUSH_ERR=1
        echo [push] FAILED: %%I
    ) else (
        echo [push] OK: %%I
    )
)

REM --- restore proxy ---
echo.
echo [proxy-mgr] Restoring Windows system proxy (Clash 127.0.0.1:7897)...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer /t REG_SZ /d "http=127.0.0.1:7897;https=127.0.0.1:7897" /f >nul 2>&1
netsh winhttp set proxy proxy-server="http=127.0.0.1:7897" >nul 2>&1
echo [proxy-mgr] Proxy restored

endlocal & exit /b %PUSH_ERR%