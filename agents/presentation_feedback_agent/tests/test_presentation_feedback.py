"""
Unit tests for Presentation Feedback Agent.
"""

import os
import pytest
from fastapi.testclient import TestClient
import uuid

# Set API key for testing before importing app
os.environ["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY", "test-api-key")

from agents.presentation_feedback_agent.app import app
from agents.presentation_feedback_agent.models import PresentationInput
from shared.models import Task, TaskEnvelope

client = TestClient(app)


def test_health_check():
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["agent"] == "presentation_feedback_agent"


def test_process_presentation_analysis():
    """Test processing a presentation analysis request."""

    presentation_data = {
        "presentation_id": "PRES-2025-001",
        "title": "AI in Modern Healthcare",
        "presenter_name": "Dr. Sarah Lee",
        "transcript": "Good morning everyone. Today I'll be discussing how AI is transforming modern healthcare. Um, artificial intelligence has become, you know, really important in medical diagnosis. Machine learning algorithms can analyze medical images with high accuracy. This technology helps doctors make better decisions.",
        "metadata": {
            "language": "en",
            "duration_minutes": 12,
            "target_audience": "medical professionals",
            "presentation_type": "technical",
            "visuals_used": True,
            "slides_count": 15,
            "recording_quality": "good"
        },
        "analysis_parameters": {
            "focus_areas": ["clarity", "pacing", "engagement", "material_relevance", "structure"],
            "detail_level": "high"
        }
    }

    task = Task(name="analyze_presentation", parameters={"data": presentation_data})
    envelope = TaskEnvelope(
        message_id=str(uuid.uuid4()),
        sender="test_supervisor",
        recipient="presentation_feedback_agent",
        task=task
    )

    response = client.post("/process", json=envelope.model_dump(mode='json'))

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "SUCCESS"
    assert "output" in report["results"]

    output = report["results"]["output"]
    assert output["presentation_id"] == "PRES-2025-001"
    assert "summary" in output
    assert "optimizations" in output
    assert "overall_recommendations" in output

    # Check summary structure
    summary = output["summary"]
    assert "overall_score" in summary
    assert "strengths" in summary
    assert "weaknesses" in summary
    assert isinstance(summary["strengths"], list)
    assert isinstance(summary["weaknesses"], list)

    # Check optimizations structure
    assert isinstance(output["optimizations"], list)
    if len(output["optimizations"]) > 0:
        opt = output["optimizations"][0]
        assert "category" in opt
        assert "issue" in opt
        assert "suggestion" in opt
        assert "impact_score" in opt


def test_invalid_input_format():
    """Test handling of invalid input format."""

    invalid_data = {
        "wrong_field": "invalid"
    }

    task = Task(name="analyze_presentation", parameters={"data": invalid_data})
    envelope = TaskEnvelope(
        message_id=str(uuid.uuid4()),
        sender="test_supervisor",
        recipient="presentation_feedback_agent",
        task=task
    )

    response = client.post("/process", json=envelope.model_dump(mode='json'))

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "FAILURE"
    assert "error" in report["results"]


def test_stats_endpoint():
    """Test the stats endpoint."""
    response = client.get("/stats")
    assert response.status_code == 200
    stats = response.json()
    assert "total_cached_analyses" in stats


@pytest.mark.asyncio
async def test_ltm_caching():
    """Test LTM caching functionality."""
    from agents.presentation_feedback_agent.ltm import LongTermMemory

    ltm = LongTermMemory(db_path="./test_ltm_cache.db")
    await ltm.initialize()

    test_transcript = "This is a test presentation transcript."
    test_presentation_id = "TEST-001"
    test_result = {
        "presentation_id": test_presentation_id,
        "summary": {
            "overall_score": 8.0,
            "strengths": ["Test strength"],
            "weaknesses": ["Test weakness"]
        }
    }

    # Ensure it's not cached initially
    assert await ltm.lookup(test_transcript) is None

    # Save to cache
    await ltm.save(test_transcript, test_presentation_id, test_result)

    # Should be cached now
    cached = await ltm.lookup(test_transcript)
    assert cached is not None
    assert cached["presentation_id"] == test_presentation_id

    # Clean up
    await ltm.clear_cache()

    import os
    if os.path.exists("./test_ltm_cache.db"):
        os.remove("./test_ltm_cache.db")


def test_pydantic_models():
    """Test Pydantic model validation."""
    from agents.presentation_feedback_agent.models import (
        PresentationInput,
        PresentationOutput,
        PresentationSummary,
        OptimizationSuggestion,
        OverallRecommendations
    )

    # Test valid input
    valid_input = PresentationInput(
        presentation_id="TEST-001",
        title="Test Presentation",
        presenter_name="John Doe",
        transcript="This is a test transcript."
    )
    assert valid_input.presentation_id == "TEST-001"

    # Test valid output
    valid_output = PresentationOutput(
        presentation_id="TEST-001",
        summary=PresentationSummary(
            overall_score=7.5,
            strengths=["Good structure"],
            weaknesses=["Needs more examples"]
        ),
        optimizations=[
            OptimizationSuggestion(
                category="clarity",
                issue="Too complex",
                suggestion="Simplify language",
                impact_score=0.8
            )
        ],
        overall_recommendations=OverallRecommendations(
            estimated_improvement="15-20%",
            action_priority=["clarity", "engagement"]
        )
    )
    assert valid_output.presentation_id == "TEST-001"
    assert valid_output.version == "1.0.0"
