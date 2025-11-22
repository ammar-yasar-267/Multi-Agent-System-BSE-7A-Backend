import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
import pytest
import asyncio
from agents.adaptive_quiz_master.quiz_master import AdaptiveQuizMaster
from agents.adaptive_quiz_master.ltm import init_db, save_performance, get_user_performance, save_quiz, lookup_quiz_history

@pytest.fixture
async def quiz_master():
    await init_db()
    return AdaptiveQuizMaster("./agents/adaptive_quiz_master/question_bank.json")

@pytest.mark.asyncio
async def test_generate_quiz(quiz_master):
    result = await quiz_master.generate_quiz(
        user_id="user123",
        topic="Python Loops",
        num_questions=2,
        question_types=["mcq", "true_false"],
        bloom_level="remember",
        adaptive=False,
        session_id="session123"
    )
    assert result["response_metadata"]["status"] == "success"
    assert result["quiz_content"]["total_questions"] == 1
    assert len(result["quiz_content"]["questions"]) == 1

@pytest.mark.asyncio
async def test_adaptive_difficulty(quiz_master):
    # Simulate poor performance
    await save_performance("user123", "Python Loops", 40.0, "medium")
    result = await quiz_master.generate_quiz(
        user_id="user123",
        topic="Python Loops",
        num_questions=2,
        question_types=["mcq"],
        bloom_level="remember",
        adaptive=True,
        session_id="session456"
    )
    assert result["adaptation_summary"]["difficulty_adjusted_to"] == "easy"
    assert result["adaptation_summary"]["adaptation_reason"] == "Struggling with topic (score: 40.0)"

@pytest.mark.asyncio
async def test_ltm_storage():
    quiz_id = "quiz989"
    await save_quiz(
        quiz_id=quiz_id,
        user_id="user323",
        session_id="session123",
        topic="Python Loops",
        questions=[{"id": "py_loop_001", "type": "mcq"}],
        performance_score=75.0,
        difficulty="medium"
    )
    quiz = await lookup_quiz_history(quiz_id)
    assert quiz["user_id"] == "user323"
    assert quiz["performance_score"] == 75.0