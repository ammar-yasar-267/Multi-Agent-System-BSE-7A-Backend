"""
Presentation Feedback Agent - FastAPI application.
Analyzes presentation transcripts and provides feedback on improvements.
"""

import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import yaml
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from shared.models import TaskEnvelope, CompletionReport
from .models import PresentationInput, PresentationOutput
from .analyzer import PresentationAnalyzer
from .ltm import LongTermMemory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
analyzer: PresentationAnalyzer = None
ltm: LongTermMemory = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    global analyzer, ltm

    logger.info("Starting Presentation Feedback Agent...")

    # Load configuration
    config_path = os.getenv("CONFIG_PATH", "./config/settings.yaml")
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning(f"Config file not found at {config_path}, using defaults")
        config = {}

    # Get API key from environment or config
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key and config.get('gemini_wrapper'):
        api_key = config['gemini_wrapper'].get('api_key')

    if not api_key:
        logger.error("GEMINI_API_KEY not found in environment or config")
        raise ValueError("GEMINI_API_KEY must be set")

    # Initialize analyzer
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
    analyzer = PresentationAnalyzer(api_key=api_key, model_name=model_name)

    # Initialize LTM
    db_path = os.getenv("LTM_DB_PATH", "./agents/presentation_feedback_agent/ltm_cache.db")
    ltm = LongTermMemory(db_path=db_path)
    await ltm.initialize()

    logger.info("Presentation Feedback Agent started successfully")

    yield

    logger.info("Shutting down Presentation Feedback Agent...")


app = FastAPI(
    title="Presentation Feedback Agent",
    description="Analyzes presentation transcripts and provides feedback on improvements",
    version="1.0.0",
    lifespan=lifespan
)


async def ensure_initialized():
    """Ensure analyzer and ltm are initialized (for testing)."""
    global analyzer, ltm

    if analyzer is None or ltm is None:
        logger.warning("Initializing analyzer and ltm (likely in test mode)")

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY must be set")

        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
        analyzer = PresentationAnalyzer(api_key=api_key, model_name=model_name)

        db_path = os.getenv("LTM_DB_PATH", "./agents/presentation_feedback_agent/ltm_cache.db")
        ltm = LongTermMemory(db_path=db_path)
        await ltm.initialize()


@app.get('/health')
async def health():
    """Health check endpoint for supervisor monitoring."""
    return {
        "status": "healthy",
        "agent": "presentation_feedback_agent",
        "version": "1.0.0"
    }


@app.post('/process', response_model=CompletionReport)
async def process_task(request: Request):
    """
    Process presentation analysis task from supervisor.

    Expects TaskEnvelope with presentation data in task.parameters.
    Returns CompletionReport with analysis results.
    """
    try:
        # Ensure initialized (for tests)
        await ensure_initialized()

        # Parse request body
        body = await request.json()
        task_envelope = TaskEnvelope(**body)

        logger.info(f"Received task from {task_envelope.sender}: {task_envelope.task.name}")

        # Extract presentation data from parameters
        params = task_envelope.task.parameters

        # Handle different input formats
        # If supervisor sends data wrapped in 'data' key
        if 'data' in params:
            presentation_data_dict = params['data']
        else:
            presentation_data_dict = params

        # Validate and parse input
        try:
            presentation_input = PresentationInput(**presentation_data_dict)
        except Exception as e:
            logger.error(f"Invalid input data: {str(e)}")
            return CompletionReport(
                message_id=f"resp_{task_envelope.message_id}",
                sender="presentation_feedback_agent",
                recipient=task_envelope.sender,
                type="completion_report",
                related_message_id=task_envelope.message_id,
                status="FAILURE",
                results={
                    "error": "Invalid input format",
                    "details": str(e)
                },
                timestamp=task_envelope.timestamp
            )

        # Check cache first
        cached_result = await ltm.lookup(presentation_input.transcript)
        if cached_result:
            logger.info(f"Returning cached result for presentation: {presentation_input.presentation_id}")
            return CompletionReport(
                message_id=f"resp_{task_envelope.message_id}",
                sender="presentation_feedback_agent",
                recipient=task_envelope.sender,
                type="completion_report",
                related_message_id=task_envelope.message_id,
                status="SUCCESS",
                results={
                    "output": cached_result,
                    "cached": True
                },
                timestamp=task_envelope.timestamp
            )

        # Perform analysis
        analysis_output = analyzer.analyze_presentation(presentation_input)

        # Cache the result
        await ltm.save(
            presentation_input.transcript,
            presentation_input.presentation_id,
            analysis_output.model_dump()
        )

        # Return success response
        return CompletionReport(
            message_id=f"resp_{task_envelope.message_id}",
            sender="presentation_feedback_agent",
            recipient=task_envelope.sender,
            type="completion_report",
            related_message_id=task_envelope.message_id,
            status="SUCCESS",
            results={
                "output": analysis_output.model_dump(),
                "cached": False
            },
            timestamp=task_envelope.timestamp
        )

    except Exception as e:
        logger.error(f"Error processing task: {str(e)}", exc_info=True)
        return CompletionReport(
            message_id=f"resp_{task_envelope.message_id}",
            sender="presentation_feedback_agent",
            recipient=task_envelope.sender,
            type="completion_report",
            related_message_id=task_envelope.message_id,
            status="FAILURE",
            results={
                "error": "Internal server error",
                "details": str(e)
            },
            timestamp=task_envelope.timestamp
        )


@app.get('/stats')
async def get_stats():
    """Get cache statistics (optional endpoint for monitoring)."""
    await ensure_initialized()
    stats = await ltm.get_stats()
    return stats


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5030))
    uvicorn.run(app, host="0.0.0.0", port=port)
