@echo off
REM Navigate to project root (two levels up from agents/presentation_feedback_agent)
cd /d "%~dp0..\.."

echo ============================================
echo Presentation Feedback Agent
echo Port: 5019
echo ============================================
echo.

set GEMINI_API_KEY= { secret }
set GEMINI_MODEL=gemini-2.5-flash

python -m uvicorn agents.presentation_feedback_agent.app:app --host 0.0.0.0 --port 5019 --reload
