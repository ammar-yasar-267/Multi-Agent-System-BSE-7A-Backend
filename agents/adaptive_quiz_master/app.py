import logging
import uuid
import yaml
import os
import aiosqlite
import json
from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager
from datetime import datetime, UTC
from pydantic import BaseModel
from typing import List, Union, Optional, Dict

# Add the parent directory to the path to import shared modules
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.models import TaskEnvelope, CompletionReport
from agents.adaptive_quiz_master.ltm import init_db, save_performance, save_quiz, lookup_quiz_history  # Use absolute import
from .quiz_master import AdaptiveQuizMaster



logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)

# Log file path at startup
_logger.info(f"Loading app.py from: {os.path.abspath(__file__)}")

# Load configuration
try:
    with open("config/settings.yaml", "r") as f:
        config = yaml.safe_load(f)
    QUESTION_BANK_PATH = config['adaptive_quiz_master']['question_bank_path']
except Exception as e:
    _logger.warning(f"Could not load config: {e}. Using default question bank path.")
    QUESTION_BANK_PATH = "./agents/adaptive_quiz_master/question_bank.json"

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)
quiz_master = AdaptiveQuizMaster(QUESTION_BANK_PATH)

@app.get('/health')
async def health():
    return {"status": "healthy", "version": "1.0.0", "timestamp": datetime.now(UTC).isoformat()}

@app.post('/process', response_model=CompletionReport)
async def process_task(req: Request):
    try:
        body = await req.json()
        task_envelope = TaskEnvelope(**body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")

    task_params = task_envelope.task.parameters
    
    _logger.info(f"Received task parameters: {task_params}")
    
    # Handle structured input as per required format
    if "agent_name" not in task_params or "intent" not in task_params or "payload" not in task_params:
        return CompletionReport(
            message_id=str(uuid.uuid4()),
            sender="AdaptiveQuizMasterAgent",
            recipient=task_envelope.sender,
            related_message_id=task_envelope.message_id,
            status="FAILURE",
            results={"error": "Missing required fields: agent_name, intent, or payload"}
        )
    
    if task_params["agent_name"] != "adaptive_quiz_master_agent" or task_params["intent"] != "generate_adaptive_quiz":
        return CompletionReport(
            message_id=str(uuid.uuid4()),
            sender="AdaptiveQuizMasterAgent",
            recipient=task_envelope.sender,
            related_message_id=task_envelope.message_id,
            status="FAILURE",
            results={"error": "Invalid agent_name or intent"}
        )
    
    payload = task_params["payload"]
    user_info = payload.get("user_info", {})
    quiz_request = payload.get("quiz_request", {})
    session_info = payload.get("session_info", {})
    
    # Validate required fields
    required_fields = {
        "user_id": user_info.get("user_id"),
        "topic": quiz_request.get("topic"),
        "num_questions": quiz_request.get("num_questions"),
        "question_types": quiz_request.get("question_types"),
        "bloom_taxonomy_level": quiz_request.get("bloom_taxonomy_level"),
        "adaptive": quiz_request.get("adaptive"),
        "session_id": session_info.get("session_id")
    }
    missing_fields = [k for k, v in required_fields.items() if v is None]
    if missing_fields:
        return CompletionReport(
            message_id=str(uuid.uuid4()),
            sender="AdaptiveQuizMasterAgent",
            recipient=task_envelope.sender,
            related_message_id=task_envelope.message_id,
            status="FAILURE",
            results={"error": f"Missing required fields in payload: {missing_fields}"}
        )
    
    quiz_params = required_fields.copy()
    quiz_params["learning_level"] = user_info.get("learning_level", "intermediate")
    
    # Map bloom_taxonomy_level to bloom_level for generate_quiz
    quiz_params["bloom_level"] = quiz_params.pop("bloom_taxonomy_level")
    
    try:
        # Generate quiz
        result = await quiz_master.generate_quiz(**quiz_params)
        
        _logger.info(f"Quiz generated successfully: {result['response_metadata']['quiz_id']}")
        
        return CompletionReport(
            message_id=str(uuid.uuid4()),
            sender="AdaptiveQuizMasterAgent",
            recipient=task_envelope.sender,
            related_message_id=task_envelope.message_id,
            status="SUCCESS",
            results=result
        )
            
    except Exception as e:
        _logger.error(f"Error generating quiz: {e}")
        return CompletionReport(
            message_id=str(uuid.uuid4()),
            sender="AdaptiveQuizMasterAgent",
            recipient=task_envelope.sender,
            related_message_id=task_envelope.message_id,
            status="FAILURE",
            results={"error": f"Process task failed: {str(e)}"}
        )

class AnswerSubmission(BaseModel):
    quiz_id: str
    user_id: str
    answers: List[Union[int, str]]  # Index for mcq/true_false, text for short_answer

@app.post('/submit_answers')
async def submit_answers(submission: AnswerSubmission):
    _logger.info(f"Submitting answers for quiz_id: {submission.quiz_id}, user_id: {submission.user_id}")
    
    try:

        try:
            from agents.adaptive_quiz_master.ltm import lookup_quiz_history 
        except ImportError:
            from .ltm import lookup_quiz_history

        # Retrieve quiz from database using lookup_quiz
        quiz = await lookup_quiz_history(submission.quiz_id)
        
        if not quiz:
            _logger.error(f"Quiz not found: {submission.quiz_id}")
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        if quiz["user_id"] != submission.user_id:
            _logger.error(f"Unauthorized user: {submission.user_id} for quiz {submission.quiz_id}")
            raise HTTPException(status_code=403, detail="Unauthorized user")
        
        # Calculate score
        score = await quiz_master.calculate_score(submission.quiz_id, submission.answers)
        
        # Update LTM with actual score
        await save_performance(
            user_id=submission.user_id,
            topic=quiz["topic"],
            score=score,
            difficulty=quiz["difficulty"],
            bloom_level=quiz["questions"][0]["bloom_taxonomy_level"] if quiz["questions"] else "remember"
        )
        await save_quiz(
            quiz_id=submission.quiz_id,
            user_id=submission.user_id,
            session_id=quiz["session_id"],
            topic=quiz["topic"],
            questions=quiz["questions"],
            performance_score=score,
            difficulty=quiz["difficulty"]
        )
        
        _logger.info(f"Answers processed successfully for quiz_id: {submission.quiz_id}, score: {score}")
        
        return {
            "status": "success",
            "quiz_id": submission.quiz_id,
            "score": score,
            "timestamp": datetime.now(UTC).isoformat()
        }
    
    except HTTPException as he:
        raise he  # Re-raise HTTP exceptions (e.g., 404, 403)
    except Exception as e:
        _logger.error(f"Error processing answers for quiz_id {submission.quiz_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing answers: {str(e)}")

@app.get('/test_lookup')
async def test_lookup():
    return {"lookup_quiz": str(lookup_quiz_history)}