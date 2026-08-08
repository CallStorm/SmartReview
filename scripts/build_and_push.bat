@echo off
REM 切换到 UTF-8 代码页，避免脚本里的中文被 cmd 当成命令名乱执行
chcp 65001 >nul

REM ============================================================
REM SmartReview - 镜像构建与推送脚本（Windows cmd）
REM 用法：scripts\build_and_push.bat [options]
REM   (无参)        PATCH 自增 1，构建并推送
REM   --minor       MINOR 自增 1，PATCH 归零
REM   --major       MAJOR 自增 1，MINOR/PATCH 归零
REM   --no-push     只构建，不推送（本地调试用）
REM   --no-latest   不打 latest 标签（只打精确版本）
REM   --git-tag     推送成功后自动创建 git tag vX.Y.Z
REM   --help        显示帮助
REM
REM 仓库前缀配置（可选）：在 scripts\build.env 里设置
REM   REGISTRY=docker.io
REM   NAMESPACE=yourname/
REM ============================================================

setlocal enabledelayedexpansion

set BUMP_TYPE=patch
set DO_PUSH=1
set DO_LATEST=1
set DO_GIT_TAG=0

:parse_args
if "%~1"=="" goto :parse_done
if /i "%~1"=="--minor"  ( set BUMP_TYPE=minor  & shift & goto :parse_args )
if /i "%~1"=="--major"  ( set BUMP_TYPE=major  & shift & goto :parse_args )
if /i "%~1"=="--no-push"   ( set DO_PUSH=0   & shift & goto :parse_args )
if /i "%~1"=="--no-latest" ( set DO_LATEST=0 & shift & goto :parse_args )
if /i "%~1"=="--git-tag"   ( set DO_GIT_TAG=1 & shift & goto :parse_args )
if /i "%~1"=="--help"      ( goto :show_help )
if /i "%~1"=="/?"          ( goto :show_help )
echo [错误] 未知参数：%~1
exit /b 1

:show_help
echo 用法：scripts\build_and_push.bat [options]
echo   --minor       MINOR 自增 1，PATCH 归零
echo   --major       MAJOR 自增 1，MINOR/PATCH 归零
echo   --no-push     只构建，不推送
echo   --no-latest   不打 latest 标签
echo   --git-tag     推送后自动 git tag vX.Y.Z
echo   --help        显示帮助
echo.
echo 仓库前缀在 scripts\build.env 中配置（不存在则用默认 10.72.2.15:80/review/）。
exit /b 0

:parse_done

REM --- 切到仓库根目录（脚本可能在任意位置调用） ---
set SCRIPT_DIR=%~dp0
pushd "%SCRIPT_DIR%.."

REM --- 加载可选配置 build.env ---
if exist scripts\build.env (
  for /f "usebackq tokens=1,2 delims==" %%a in ("scripts\build.env") do (
    set "KEY=%%a"
    if not "!KEY:~0,1!"=="#" if not "%%a"=="" set "%%a=%%b"
  )
)

if not defined REGISTRY  set REGISTRY=10.72.2.15:80
if not defined NAMESPACE set NAMESPACE=review/

REM --- 读 VERSION ---
set VERSION_FILE=VERSION
if not exist "%VERSION_FILE%" (
  echo [错误] 找不到 VERSION 文件
  popd & exit /b 1
)

set OLD_VERSION=
for /f "usebackq delims=" %%v in ("%VERSION_FILE%") do (
  set "LINE=%%v"
  if not "!LINE!"=="" if not "!LINE:~0,1!"=="#" (
    if not defined OLD_VERSION set "OLD_VERSION=%%v"
  )
)

if not defined OLD_VERSION (
  echo [错误] VERSION 文件为空
  popd & exit /b 1
)

REM 去掉可选的 v 前缀
set VER=%OLD_VERSION%
if "%VER:~0,1%"=="v" set VER=%VER:~1%

REM 解析 MAJOR.MINOR.PATCH
for /f "tokens=1,2,3 delims=." %%a in ("%VER%") do (
  set MAJOR=%%a
  set MINOR=%%b
  set PATCH=%%c
)

if not defined MAJOR goto :bad_version
if not defined MINOR goto :bad_version
if not defined PATCH goto :bad_version

REM --- 自增版本 ---
if /i "%BUMP_TYPE%"=="major" (
  set /a MAJOR+=1
  set MINOR=0
  set PATCH=0
) else if /i "%BUMP_TYPE%"=="minor" (
  set /a MINOR+=1
  set PATCH=0
) else (
  set /a PATCH+=1
)

set NEW_VERSION=%MAJOR%.%MINOR%.%PATCH%

echo.
echo ============================================================
echo   SmartReview 镜像构建与推送
echo ============================================================
echo   当前版本  : %OLD_VERSION%
echo   新版本    : %NEW_VERSION%   (bump=%BUMP_TYPE%)
echo   仓库前缀  : %REGISTRY%/%NAMESPACE%
echo   推送      : %DO_PUSH%   latest=%DO_LATEST%
echo ============================================================
echo.

set /p CONFIRM=确认继续? [y/N]:
if /i not "%CONFIRM%"=="y" (
  echo 已取消。
  popd & exit /b 0
)

REM --- 写回 VERSION ---
> "%VERSION_FILE%.tmp" echo %NEW_VERSION%
move /y "%VERSION_FILE%.tmp" "%VERSION_FILE%" >nul
if errorlevel 1 (
  echo [错误] 写 VERSION 失败
  popd & exit /b 1
)

REM --- 构建 + 推送 ---
call :build_and_push_image smartreview-backend backend
if errorlevel 1 goto :fail

call :build_and_push_image smartreview-frontend frontend
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo   [完成] 版本已更新为 %NEW_VERSION%
echo ============================================================
echo   镜像：
echo     %REGISTRY%/%NAMESPACE%smartreview-backend:%NEW_VERSION%
if "%DO_LATEST%"=="1" echo     %REGISTRY%/%NAMESPACE%smartreview-backend:latest
echo     %REGISTRY%/%NAMESPACE%smartreview-frontend:%NEW_VERSION%
if "%DO_LATEST%"=="1" echo     %REGISTRY%/%NAMESPACE%smartreview-frontend:latest

REM --- 可选 git tag ---
if "%DO_GIT_TAG%"=="1" (
  git rev-parse --is-inside-work-tree >nul 2>&1
  if errorlevel 1 (
    echo [警告] 当前不是 git 仓库，跳过 git tag
  ) else (
    git tag "v%NEW_VERSION%"
    if errorlevel 1 (
      echo [警告] git tag v%NEW_VERSION% 创建失败（可能已存在）
    ) else (
      echo [完成] 已创建 git tag v%NEW_VERSION%（记得 git push --tags）
    )
  )
)

popd
endlocal
exit /b 0

:bad_version
echo [错误] VERSION 格式不合法：%OLD_VERSION%  (期望 MAJOR.MINOR.PATCH)
popd
endlocal
exit /b 1

:fail
echo [失败] 构建/推送已终止
popd
endlocal
exit /b 1

REM ============================================================
REM 子例程：构建单个镜像并（可选）推送
REM   %1 = image_name（如 smartreview-backend）
REM   %2 = build_context（如 backend）
REM ============================================================
:build_and_push_image
set IMG=%~1
set CTX=%~2
set TAG_VER=%REGISTRY%/%NAMESPACE%%IMG%:%NEW_VERSION%
set TAG_LATEST=%REGISTRY%/%NAMESPACE%%IMG%:latest

echo.
echo ----- 构建 %IMG% -----
docker build -t "%TAG_VER%" -f "%CTX%\Dockerfile" "%CTX%"
if errorlevel 1 exit /b 1

if "%DO_LATEST%"=="1" (
  docker tag "%TAG_VER%" "%TAG_LATEST%"
  if errorlevel 1 exit /b 1
)

if "%DO_PUSH%"=="1" (
  echo ----- 推送 %IMG% -----
  call :clear_proxy
  docker push "%TAG_VER%"
  set PUSH_ERR=!errorlevel!
  call :restore_proxy
  if !PUSH_ERR! neq 0 exit /b !PUSH_ERR!
  if "%DO_LATEST%"=="1" (
    call :clear_proxy
    docker push "%TAG_LATEST%"
    set PUSH_ERR=!errorlevel!
    call :restore_proxy
    if !PUSH_ERR! neq 0 exit /b !PUSH_ERR!
  )
)

exit /b 0

REM ============================================================
REM 临时清空常见代理环境变量（推内网仓库会被外网代理截胡）
REM ============================================================
:clear_proxy
set OLD_HTTP_PROXY=%HTTP_PROXY%
set OLD_HTTPS_PROXY=%HTTPS_PROXY%
set OLD_http_proxy=%http_proxy%
set OLD_https_proxy=%https_proxy%
set OLD_ALL_PROXY=%ALL_PROXY%
set OLD_all_proxy=%all_proxy%
set OLD_NO_PROXY=%NO_PROXY%
set OLD_no_proxy=%no_proxy%
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set ALL_PROXY=
set all_proxy=
set NO_PROXY=
set no_proxy=
exit /b 0

:restore_proxy
if defined OLD_HTTP_PROXY  set HTTP_PROXY=%OLD_HTTP_PROXY%
if defined OLD_HTTPS_PROXY set HTTPS_PROXY=%OLD_HTTPS_PROXY%
if defined OLD_http_proxy  set http_proxy=%OLD_http_proxy%
if defined OLD_https_proxy set https_proxy=%OLD_https_proxy%
if defined OLD_ALL_PROXY   set ALL_PROXY=%OLD_ALL_PROXY%
if defined OLD_all_proxy   set all_proxy=%OLD_all_proxy%
if defined OLD_NO_PROXY    set NO_PROXY=%OLD_NO_PROXY%
if defined OLD_no_proxy    set no_proxy=%OLD_no_proxy%
exit /b 0