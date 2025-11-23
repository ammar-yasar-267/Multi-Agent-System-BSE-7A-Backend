"""
Core presentation analysis logic using LLM for intelligent feedback.
"""

import json
import logging
from typing import Dict, Any
import google.generativeai as genai
from .models import (
    PresentationInput,
    PresentationOutput,
    PresentationSummary,
    OptimizationSuggestion,
    OverallRecommendations
)

logger = logging.getLogger(__name__)


class PresentationAnalyzer:
    """Analyzes presentation transcripts and provides structured feedback."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash-exp"):
        """
        Initialize the analyzer with Gemini API.

        Args:
            api_key: Google Gemini API key
            model_name: Model to use for analysis
        """
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        logger.info(f"Initialized PresentationAnalyzer with model: {model_name}")

    def analyze_presentation(self, presentation_data: PresentationInput) -> PresentationOutput:
        """
        Analyze a presentation transcript and generate structured feedback.

        Args:
            presentation_data: Input presentation data

        Returns:
            PresentationOutput with detailed feedback
        """
        logger.info(f"Analyzing presentation: {presentation_data.presentation_id}")

        # Build the analysis prompt
        prompt = self._build_analysis_prompt(presentation_data)

        # Call Gemini API with retry logic
        try:
            response = self.model.generate_content(prompt)
            analysis_text = response.text

            # Parse the JSON response
            analysis_data = self._parse_analysis_response(analysis_text)

            # Structure the output
            output = self._structure_output(presentation_data.presentation_id, analysis_data)

            logger.info(f"Successfully analyzed presentation: {presentation_data.presentation_id}")
            return output

        except Exception as e:
            error_str = str(e)

            # Check if it's a quota error
            if "429" in error_str or "quota" in error_str.lower() or "exceeded" in error_str.lower():
                logger.warning(f"Rate limit exceeded: {error_str}")
                return self._create_rate_limit_response(presentation_data.presentation_id, error_str)

            # Check if it's a 404 model not found error
            elif "404" in error_str:
                logger.error(f"Model not found: {error_str}")
                return self._create_model_error_response(presentation_data.presentation_id)

            # Other errors
            else:
                logger.error(f"Error analyzing presentation: {error_str}")
                return self._create_fallback_response(presentation_data.presentation_id)

    def _build_analysis_prompt(self, data: PresentationInput) -> str:
        """Build the prompt for LLM analysis."""

        focus_areas_str = ", ".join(data.analysis_parameters.focus_areas)

        prompt = f"""You are an expert presentation coach analyzing a presentation transcript.

**Presentation Details:**
- Title: {data.title}
- Presenter: {data.presenter_name}
- Duration: {data.metadata.duration_minutes} minutes
- Target Audience: {data.metadata.target_audience}
- Presentation Type: {data.metadata.presentation_type}
- Slides Count: {data.metadata.slides_count}

**Transcript:**
{data.transcript}

**Analysis Task:**
Analyze this presentation focusing on: {focus_areas_str}

Provide detailed feedback in the following JSON format:

{{
  "overall_score": <float between 0-10>,
  "strengths": [<list of 2-4 key strengths>],
  "weaknesses": [<list of 2-4 key weaknesses>],
  "optimizations": [
    {{
      "category": "<one of: clarity, pacing, engagement, material_relevance, structure>",
      "issue": "<specific issue identified>",
      "suggestion": "<actionable improvement suggestion>",
      "example_before": "<quote from transcript showing the issue>",
      "example_after": "<improved version>",
      "impact_score": <float 0-1 indicating impact of fixing this>
    }}
  ],
  "estimated_improvement": "<percentage or range like '15-20%'>",
  "action_priority": [<ordered list of categories to address first>]
}}

**Guidelines:**
1. Be specific and constructive in your feedback
2. Provide 3-5 optimization suggestions covering different categories
3. Use actual quotes from the transcript in example_before
4. Score based on effectiveness for the stated audience and presentation type
5. Prioritize high-impact improvements
6. Consider confidence indicators (filler words, hedging language)
7. Evaluate material depth and relevance
8. Assess logical flow and structure

Return ONLY valid JSON, no additional text."""

        return prompt

    def _parse_analysis_response(self, response_text: str) -> Dict[str, Any]:
        """Parse the LLM response into structured data."""
        try:
            # Clean up response (remove markdown code blocks if present)
            cleaned = response_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            # Parse JSON
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {str(e)}")
            logger.debug(f"Response text: {response_text}")
            raise

    def _structure_output(self, presentation_id: str, data: Dict[str, Any]) -> PresentationOutput:
        """Convert parsed data into PresentationOutput model."""

        summary = PresentationSummary(
            overall_score=data.get("overall_score", 5.0),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", [])
        )

        optimizations = [
            OptimizationSuggestion(**opt)
            for opt in data.get("optimizations", [])
        ]

        recommendations = OverallRecommendations(
            estimated_improvement=data.get("estimated_improvement", "10-15%"),
            action_priority=data.get("action_priority", ["clarity", "structure", "engagement"])
        )

        return PresentationOutput(
            presentation_id=presentation_id,
            summary=summary,
            optimizations=optimizations,
            overall_recommendations=recommendations
        )

    def _create_rate_limit_response(self, presentation_id: str, error_message: str) -> PresentationOutput:
        """Create a response when rate limit is exceeded."""
        # Try to extract retry time from error message
        retry_info = "Please wait a few minutes before trying again"
        if "retry" in error_message.lower() and "seconds" in error_message.lower():
            import re
            match = re.search(r'(\d+\.\d+)s', error_message)
            if match:
                retry_seconds = float(match.group(1))
                retry_minutes = int(retry_seconds / 60) + 1
                retry_info = f"Please wait approximately {retry_minutes} minute(s) before trying again"

        return PresentationOutput(
            presentation_id=presentation_id,
            summary=PresentationSummary(
                overall_score=5.0,
                strengths=["Presentation received successfully"],
                weaknesses=["Free tier API rate limit reached"]
            ),
            optimizations=[
                OptimizationSuggestion(
                    category="system",
                    issue="Gemini API rate limit exceeded",
                    suggestion=f"The free tier has a limited number of requests per minute. {retry_info}, or upgrade to a paid tier for unlimited access.",
                    impact_score=0.0
                )
            ],
            overall_recommendations=OverallRecommendations(
                estimated_improvement="Analysis pending",
                action_priority=["wait_and_retry"]
            )
        )

    def _create_model_error_response(self, presentation_id: str) -> PresentationOutput:
        """Create a response when model is not found."""
        return PresentationOutput(
            presentation_id=presentation_id,
            summary=PresentationSummary(
                overall_score=5.0,
                strengths=["Presentation received successfully"],
                weaknesses=["Configured AI model is not available"]
            ),
            optimizations=[
                OptimizationSuggestion(
                    category="configuration",
                    issue="AI model not found",
                    suggestion="The configured model is not available. Please update GEMINI_MODEL in .env to 'gemini-2.5-flash' or another available model.",
                    impact_score=0.0
                )
            ],
            overall_recommendations=OverallRecommendations(
                estimated_improvement="Configuration needed",
                action_priority=["update_model_config"]
            )
        )

    def _create_fallback_response(self, presentation_id: str) -> PresentationOutput:
        """Create a fallback response when analysis fails."""
        return PresentationOutput(
            presentation_id=presentation_id,
            summary=PresentationSummary(
                overall_score=5.0,
                strengths=["Presentation submitted for analysis"],
                weaknesses=["Analysis could not be completed due to technical issues"]
            ),
            optimizations=[
                OptimizationSuggestion(
                    category="general",
                    issue="Analysis temporarily unavailable",
                    suggestion="Please try again or contact support",
                    impact_score=0.0
                )
            ],
            overall_recommendations=OverallRecommendations(
                estimated_improvement="Unknown",
                action_priority=["general"]
            )
        )
