FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

# Copy dependency manifest and install first to leverage build cache
COPY agents/presentation_feedback_agent/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY agents/presentation_feedback_agent ./agents/presentation_feedback_agent
# Copy shared utilities and config so imports like `shared.models` and
# `config/settings.yaml` are available inside the container
COPY shared ./shared
COPY config/settings.yaml ./config/settings.yaml

# Run the agent
CMD ["python", "-m", "uvicorn", "agents.presentation_feedback_agent.app:app", "--host", "0.0.0.0", "--port", "5030"]
