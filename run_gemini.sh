#!/bin/bash
# run_gemini.sh
echo "Starting Gemini Wrapper..."
python -m uvicorn agents.gemini_wrapper_agent.app:app --host 0.0.0.0 --port 5010 --reload
