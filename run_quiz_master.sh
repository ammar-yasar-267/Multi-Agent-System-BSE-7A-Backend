#!/bin/bash
echo "Starting Adaptive Quiz Master Agent..."
uvicorn agents.adaptive_quiz_master.app:app --host 0.0.0.0 --port 5020 --reload