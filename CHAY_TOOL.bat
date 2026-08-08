@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY_CMD=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Khong tim thay Python. Hay cai Python 3 va chon Add Python to PATH.
        pause
        exit /b 1
    )
    set "PY_CMD=python"
)

%PY_CMD% -m pip install -r requirements.txt
if errorlevel 1 (
    echo Cai thu vien that bai.
    pause
    exit /b 1
)

%PY_CMD% facebook_cookie_login.py --csv infor.csv %*
set "EXIT_CODE=%errorlevel%"
echo.
echo Tool ket thuc voi ma %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
