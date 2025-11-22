import uuid
import logging
import json
import httpx
from typing import Dict, List, Optional, Union
from datetime import datetime, UTC

from .question_bank import QuestionBank
from .ltm import (
    get_user_performance,
    save_performance,
    save_quiz,
    get_generated_questions,
    cache_generated_questions,
    lookup_quiz_history
)

_logger = logging.getLogger("aqma")

class AdaptiveQuizMaster:
    def __init__(self, question_bank_path: str):
        self.question_bank = QuestionBank(question_bank_path)
        self.difficulty_levels = ["easy", "medium", "hard"]
        self.bloom_levels = ["remember", "understand", "apply", "analyze"]
        self.learning_level_map = {"beginner": "easy", "intermediate": "medium", "advanced": "hard"}

    def adjust_difficulty(self, previous_score: Optional[float], previous_difficulty: Optional[str], learning_level: str) -> str:
        """Determine the appropriate difficulty level."""
        if previous_score is None:
            return self.learning_level_map.get(learning_level.lower(), "easy")
        
        if previous_difficulty not in self.difficulty_levels:
            previous_difficulty = "medium"
            
        current_idx = self.difficulty_levels.index(previous_difficulty)
        
        if previous_score < 50:
            return self.difficulty_levels[max(0, current_idx - 1)]
        elif previous_score > 80:
            return self.difficulty_levels[min(len(self.difficulty_levels) - 1, current_idx + 1)]
        else:
            return previous_difficulty

    def adjust_bloom_level(self, previous_score: Optional[float], previous_bloom_level: Optional[str], learning_level: str) -> str:
        """Determine the appropriate Bloom's taxonomy level."""
        if previous_score is None:
            return "remember" if learning_level.lower() == "beginner" else "understand"
        
        if previous_bloom_level not in self.bloom_levels:
            previous_bloom_level = "understand"
            
        current_idx = self.bloom_levels.index(previous_bloom_level)
        
        if previous_score < 50:
            return self.bloom_levels[max(0, current_idx - 1)]
        elif previous_score > 80:
            return self.bloom_levels[min(len(self.bloom_levels) - 1, current_idx + 1)]
        else:
            return previous_bloom_level

    def get_adaptation_reason(self, previous_score: Optional[float], previous_difficulty: Optional[str], new_difficulty: str, previous_bloom_level: Optional[str], new_bloom_level: str, learning_level: str) -> str:
        """Generate a reason for the difficulty and Bloom's level adjustment."""
        reasons = []
        if previous_score is None:
            reasons.append(f"Initial quiz based on learning level: {learning_level}")
        else:
            if previous_score < 50:
                reasons.append(f"Struggling with topic (score: {previous_score:.1f}%)")
            elif previous_score > 80:
                reasons.append(f"Improved performance (score: {previous_score:.1f}%)")
            else:
                reasons.append(f"Stable performance (score: {previous_score:.1f}%)")
        
        if previous_difficulty != new_difficulty:
            reasons.append(f"Difficulty adjusted to: {new_difficulty}")
        if previous_bloom_level != new_bloom_level:
            reasons.append(f"Bloom's level adjusted to: {new_bloom_level}")
        
        return "; ".join(reasons)

    async def generate_with_gemini(self, topic: str, types: List[str], bloom: str, difficulty: str, count: int) -> List[Dict]:
        """Generate questions via Gemini Wrapper Agent."""
        prompt = f"""
        Generate {count} high-quality quiz questions on '{topic}'.
        Question types: {', '.join(types)}
        Bloom's Taxonomy level: {bloom}
        Difficulty: {difficulty}

        Return ONLY a valid JSON array with this exact schema:
        [
          {{
            "id": "gen-001",
            "type": "mcq|true_false|short_answer",
            "question_text": "Your question here",
            "options": ["choice1", "choice2", ...],  // empty array for short_answer
            "correct_option_index": 0,  // null for short_answer
            "difficulty": "{difficulty}",
            "bloom_taxonomy_level": "{bloom}"
          }}
        ]
        Do not include explanations, markdown, or extra text.
        """

        payload = {
            "message_id": str(uuid.uuid4()),
            "sender": "adaptive-quiz-master",
            "recipient": "gemini-wrapper",
            "type": "task_assignment",
            "task": {
                "name": "generate_text",
                "parameters": {
                    "prompt": prompt,
                    "max_tokens": 2000
                }
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post("http://localhost:5010/process", json=payload)
                resp.raise_for_status()
                raw = resp.json()["results"]["generated_text"]
                questions = json.loads(raw)
                for q in questions:
                    q["id"] = str(uuid.uuid4())
                _logger.info(f"Generated {len(questions)} questions for '{topic}' via Gemini")
                return questions
        except Exception as e:
            _logger.error(f"Gemini generation failed: {e}")
            return []

    async def get_questions(
        self,
        topic: str,
        question_types: List[str],
        bloom_level: str,
        difficulty: str,
        num_questions: int
    ) -> List[Dict]:
        """Get questions from local → cache → Gemini."""
        questions = []

        # 1. Local question bank
        local = self.question_bank.get_questions(topic, question_types, bloom_level, difficulty, num_questions)
        questions.extend(local)
        _logger.debug(f"Found {len(local)} local questions for {topic}")

        # 2. Cached generated questions
        if len(questions) < num_questions:
            cached = await get_generated_questions(topic, question_types, bloom_level, difficulty)
            questions.extend(cached)
            _logger.debug(f"Found {len(cached)} cached generated questions")

        # 3. Generate new ones via Gemini
        if len(questions) < num_questions:
            missing = num_questions - len(questions)
            generated = await self.generate_with_gemini(topic, question_types, bloom_level, difficulty, missing)
            if generated:
                questions.extend(generated)
                await cache_generated_questions(topic, generated)
                _logger.info(f"Generated and cached {len(generated)} new questions")

        return questions[:num_questions]

    async def calculate_score(self, quiz_id: str, user_answers: List[Union[int, str]]) -> float:
        """Calculate performance score based on user answers."""
        quiz = await lookup_quiz_history(quiz_id)
        if not quiz:
            raise ValueError(f"Quiz {quiz_id} not found")
        
        questions = quiz["questions"]
        if len(user_answers) != len(questions):
            raise ValueError(f"Mismatch: {len(user_answers)} answers for {len(questions)} questions")
        
        correct_count = 0
        for i, (question, answer) in enumerate(zip(questions, user_answers)):
            if question["type"] in ["mcq", "true_false"]:
                if isinstance(answer, int) and answer == question["correct_option_index"]:
                    correct_count += 1
            elif question["type"] == "short_answer":
                # TODO: Implement short answer evaluation (e.g., keyword matching or Gemini)
                _logger.warning(f"Short answer scoring not implemented for question {question['id']}")
                continue
        
        score = (correct_count / len(questions)) * 100 if questions else 0.0
        _logger.info(f"Calculated score for quiz {quiz_id}: {score:.1f}%")
        return score

    async def generate_quiz(
        self,
        user_id: str,
        topic: str,
        num_questions: int,
        question_types: List[str],
        bloom_level: str,
        adaptive: bool,
        session_id: str,
        learning_level: str = "intermediate"
    ) -> Dict:
        """Generate an adaptive quiz."""
        quiz_id = str(uuid.uuid4())
        
        if not question_types:
            question_types = ["mcq", "true_false", "short_answer"]

        # Get previous performance
        previous_performance = None
        if adaptive:
            previous_performance = await get_user_performance(user_id, topic)
        
        previous_score = previous_performance["score"] if previous_performance else None
        previous_difficulty = previous_performance["difficulty"] if previous_performance else None
        previous_bloom_level = previous_performance["bloom_level"] if previous_performance else None

        # Adjust difficulty and Bloom's level
        if adaptive:
            difficulty = self.adjust_difficulty(previous_score, previous_difficulty, learning_level)
            bloom_level = self.adjust_bloom_level(previous_score, previous_bloom_level or bloom_level, learning_level)
            adaptation_reason = self.get_adaptation_reason(previous_score, previous_difficulty, difficulty, previous_bloom_level, bloom_level, learning_level)
        else:
            difficulty = "medium"
            bloom_level = bloom_level  # Use provided bloom_level
            adaptation_reason = "Non-adaptive mode"

        # Validate bloom level
        if bloom_level not in self.bloom_levels:
            return {
                "response_metadata": {
                    "quiz_id": quiz_id,
                    "session_id": session_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "status": "error"
                },
                "error": f"Invalid Bloom level: {bloom_level}. Available: {', '.join(self.bloom_levels)}"
            }

        questions = await self.get_questions(topic, question_types, bloom_level, difficulty, num_questions)

        if not questions:
            return {
                "response_metadata": {
                    "quiz_id": quiz_id,
                    "session_id": session_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "status": "error"
                },
                "error": f"No questions available for topic '{topic}' with current filters. Try different bloom/difficulty."
            }

        # Store initial quiz with placeholder score (updated later via /submit_answers)
        performance_score = previous_score if previous_score is not None else 50.0
        await save_performance(user_id, topic, performance_score, difficulty, bloom_level)
        await save_quiz(quiz_id, user_id, session_id, topic, questions, performance_score, difficulty)

        quiz_questions = [
            {k: v for k, v in q.items() if k not in ["bloom_taxonomy_level", "generated_at"]}
            for q in questions
        ]

        return {
            "response_metadata": {
                "quiz_id": quiz_id,
                "session_id": session_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "status": "success"
            },
            "adaptation_summary": {
                "previous_performance_score": round(previous_score, 1) if previous_score is not None else 0.0,
                "difficulty_adjusted_to": difficulty,
                "bloom_level_adjusted_to": bloom_level,
                "adaptation_reason": adaptation_reason
            },
            "quiz_content": {
                "topic": topic,
                "total_questions": len(quiz_questions),
                "questions": quiz_questions
            },
            "next_actions": {
                "store_result_endpoint": "/update_user_performance",
                "feedback_required": True
            }
        }