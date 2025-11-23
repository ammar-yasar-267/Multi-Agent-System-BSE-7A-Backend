@echo off
REM This script must be run from the project root directory
REM Navigate to project root (assumes script is in project root)
cd /d "%~dp0"

echo ============================================
echo Starting Presentation Feedback Agent
echo Port: 5019
echo ============================================
echo.

set GEMINI_API_KEY=AIzaSyDuBxbd9t-wbe0DOeeLIFH3ePdH6QlDpmI
set GEMINI_MODEL=gemini-2.5-flash

python -m uvicorn agents.presentation_feedback_agent.app:app --host 0.0.0.0 --port 5019 --reload

