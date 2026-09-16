@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo   kimodo-motion  -  로컬 웹 UI 실행기
echo ============================================
echo.

where py >nul 2>&1
if errorlevel 1 (
    echo [오류] 이 PC에 Python이 설치되어 있지 않습니다.
    echo.
    echo   https://www.python.org/downloads/ 에서 Python을 받아 설치한 뒤,
    echo   설치 화면에서 반드시 "Add python.exe to PATH" 체크박스를 켜주세요.
    echo   설치가 끝나면 이 파일을 다시 더블클릭하면 됩니다.
    echo.
    pause
    exit /b 1
)

echo [1/2] 실행 가능한 상태인지 점검 중...
echo.
py webui\server.py --check
if errorlevel 1 (
    echo.
    echo ============================================
    echo   점검에서 문제를 찾았습니다. 위 [FAIL] 항목을
    echo   먼저 해결한 뒤 이 파일을 다시 실행해주세요.
    echo ============================================
    pause
    exit /b 1
)

echo.
echo [2/2] 서버를 백그라운드 창으로 띄우고 브라우저를 엽니다...
echo   (이 창은 닫아도 됩니다 - 서버는 별도 창에서 계속 실행됩니다)
echo   서버를 완전히 끄려면, 새로 뜬 "kimodo-motion webui" 창을 닫으세요.
echo.

start "kimodo-motion webui" /min py webui\server.py

REM 서버가 뜰 시간을 잠깐 준 뒤 브라우저를 연다 (ping을 타이머 대용으로 씀 - 콘솔 없이도 동작).
ping -n 3 127.0.0.1 >nul
start "" http://127.0.0.1:8188/

echo 브라우저를 열었습니다. 이 창은 그냥 닫으셔도 됩니다.
ping -n 5 127.0.0.1 >nul
exit /b 0
