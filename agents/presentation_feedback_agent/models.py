"""
Pydantic models for Presentation Feedback Agent.
Defines input/output structures for presentation analysis.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class PresentationMetadata(BaseModel):
    """Metadata about the presentation."""
    language: str = "en"
    duration_minutes: Optional[int] = None
    target_audience: Optional[str] = None
    presentation_type: Optional[str] = None
    visuals_used: Optional[bool] = None
    slides_count: Optional[int] = None
    recording_quality: Optional[str] = None


class AnalysisParameters(BaseModel):
    """Parameters for controlling analysis behavior."""
    focus_areas: List[str] = Field(
        default=["clarity", "pacing", "engagement", "material_relevance", "structure"]
    )
    detail_level: Literal["low", "medium", "high"] = "high"


class PresentationInput(BaseModel):
    """Input model for presentation feedback request."""
    presentation_id: str
    title: str
    presenter_name: str
    transcript: str
    metadata: PresentationMetadata = Field(default_factory=PresentationMetadata)
    analysis_parameters: AnalysisParameters = Field(default_factory=AnalysisParameters)


class OptimizationSuggestion(BaseModel):
    """A single optimization suggestion."""
    category: str
    issue: str
    suggestion: str
    example_before: Optional[str] = None
    example_after: Optional[str] = None
    impact_score: float = Field(ge=0.0, le=1.0)


class PresentationSummary(BaseModel):
    """Summary of presentation analysis."""
    overall_score: float = Field(ge=0.0, le=10.0)
    strengths: List[str]
    weaknesses: List[str]


class OverallRecommendations(BaseModel):
    """Overall recommendations for improvement."""
    estimated_improvement: str
    action_priority: List[str]


class PresentationOutput(BaseModel):
    """Output model for presentation feedback response."""
    presentation_id: str
    summary: PresentationSummary
    optimizations: List[OptimizationSuggestion]
    overall_recommendations: OverallRecommendations
    version: str = "1.0.0"
