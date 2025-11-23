@echo off
setlocal

REM Get test file from argument or use default
set TEST_FILE=%1
if "%TEST_FILE%"=="" set TEST_FILE=test_sample.json

echo ============================================
echo Presentation Feedback Agent - Test
echo Test File: %TEST_FILE%
echo ============================================
echo.

REM Check if agent is running
echo [1/3] Checking agent...
curl -s http://127.0.0.1:5019/health >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Agent not running!
    echo Start with: run_presentation_feedback.bat
    pause
    exit /b 1
)
echo [OK] Agent healthy
echo.

REM Check test file exists
if not exist "%TEST_FILE%" (
    echo [ERROR] Test file not found: %TEST_FILE%
    echo Available: test_sample.json, test_sample_confident.json, test_sample_poor.json, test_sample_technical.json
    pause
    exit /b 1
)

REM Send request
echo [2/3] Analyzing presentation...
curl -X POST http://127.0.0.1:5019/process ^
  -H "Content-Type: application/json" ^
  -d @%TEST_FILE% ^
  -o test_result.json ^
  -s

echo [3/3] Results saved to: test_result.json
echo.
pause
