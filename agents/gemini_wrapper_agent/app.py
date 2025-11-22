import logging
import uuid
from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager
from datetime import datetime

from shared.models import TaskEnvelope, CompletionReport
from agents.gemini_wrapper_agent import ltm, client

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await ltm.init_db()
    yield

app = FastAPI(lifespan=lifespan)

@app.get('/health')
async def health():
    return {"status": "healthy", "version": "1.0.0", "timestamp": datetime.utcnow().isoformat()}

@app.post('/process', response_model=CompletionReport)
async def process_task(req: Request):
    try:
        body = await req.json()
        task_envelope = TaskEnvelope(**body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")

    input_text = task_envelope.task.parameters.get("request")
    if not input_text:
        return CompletionReport(
            message_id=str(uuid.uuid4()),
            sender="GeminiWrapperAgent",
            recipient=task_envelope.sender,
            related_message_id=task_envelope.message_id,
            status="FAILURE",
            results={"error": "Missing 'request' in task parameters"}
        )

    # Check LTM first
    cached_output = await ltm.lookup(input_text)
    if cached_output:
        return CompletionReport(
            message_id=str(uuid.uuid4()),
            sender="GeminiWrapperAgent",
            recipient=task_envelope.sender,
            related_message_id=task_envelope.message_id,
            status="SUCCESS",
            results={"output": cached_output, "cached": True}
        )

    # If not in LTM, call the Gemini client
    model_override = task_envelope.task.parameters.get("modelOverride")
    result = await client.call_gemini_or_mock(input_text, model_override)

    if "error" in result:
        return CompletionReport(
            message_id=str(uuid.uuid4()),
            sender="GeminiWrapperAgent",
            recipient=task_envelope.sender,
            related_message_id=task_envelope.message_id,
            status="FAILURE",
            results={"error": result["error"]}
        )

    # Save to LTM and return success
    await ltm.save(input_text, result["output"])
    return CompletionReport(
        message_id=str(uuid.uuid4()),
        sender="GeminiWrapperAgent",
        recipient=task_envelope.sender,
        related_message_id=task_envelope.message_id,
        status="SUCCESS",
        results=result
    )
