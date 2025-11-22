from .Abstract_Class_Worker_Agent import AbstractWorkerAgent
from .quiz_master import AdaptiveQuizMaster
from .ltm import get_user_performance, save_performance, save_quiz, lookup_quiz_history
import json
import uuid
from datetime import datetime
import yaml
import asyncio

with open("config/settings.yaml", "r") as f:
    config = yaml.safe_load(f)

QUESTION_BANK_PATH = config['adaptive_quiz_master']['question_bank_path']

class AdaptiveQuizMasterAgent(AbstractWorkerAgent):
    def __init__(self, agent_id: str, supervisor_id: str):
        super().__init__(agent_id, supervisor_id)
        self.quiz_master = AdaptiveQuizMaster(QUESTION_BANK_PATH)

    async def process_task(self, task_data: dict) -> dict:
        """Process the task and generate a quiz."""
        try:
            if task_data.get("agent_name") != "adaptive_quiz_master_agent" or task_data.get("intent") != "generate_adaptive_quiz":
                return {"error": "Invalid agent_name or intent"}

            payload = task_data.get("payload", {})
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
                return {"error": f"Missing required fields: {missing_fields}"}

            # Generate quiz (async call)
            result = await self.quiz_master.generate_quiz(
                user_id=user_info["user_id"],
                topic=quiz_request["topic"],
                num_questions=quiz_request["num_questions"],
                question_types=quiz_request["question_types"],
                bloom_level=quiz_request["bloom_taxonomy_level"],
                adaptive=quiz_request["adaptive"],
                session_id=session_info["session_id"],
                learning_level=user_info.get("learning_level", "intermediate")
            )
            return result
        except Exception as e:
            return {"error": f"Task processing failed: {str(e)}"}

    def send_message(self, recipient: str, message_obj: dict):
        """Send message to the supervisor (placeholder for HTTP POST)."""
        print(f"[{self._id}] Sending message to {recipient}: {json.dumps(message_obj, indent=2)}")

    def write_to_ltm(self, key: str, value: dict) -> bool:
        """Write data to LTM."""
        try:
            quiz_id = key
            user_id = value.get("user_id")
            session_id = value.get("session_id")
            topic = value.get("topic")
            questions = value.get("questions", [])
            performance_score = value.get("performance_score", 0.0)
            difficulty = value.get("difficulty", "medium")
            bloom_level = value.get("bloom_level", "remember")  # NEW: Include bloom_level
            asyncio.run(save_quiz(quiz_id, user_id, session_id, topic, questions, performance_score, difficulty))
            asyncio.run(save_performance(user_id, topic, performance_score, difficulty, bloom_level))
            return True
        except Exception as e:
            print(f"[{self._id}] LTM write failed: {e}")
            return False

    def read_from_ltm(self, key: str) -> dict | None:
        """Read data from LTM."""
        try:
            return asyncio.run(lookup_quiz_history(key))
        except Exception as e:
            print(f"[{self._id}] LTM read failed: {e}")
            return None