import uuid
import logging
from fastapi import FastAPI, Request, HTTPException
from shared.models import TaskEnvelope, CompletionReport

from .models import ResearchInput, ResearchOutput, YearRange
from .search import search_papers
from .summarize import generate_summary
import re

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "ResearchFinderAgent"}

@app.post("/process", response_model=CompletionReport)
async def process_task(req: Request):
    try:
        body = await req.json()
        task_envelope = TaskEnvelope(**body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")

    # Extract parameters and support free-form `request` in task.parameters
    params = task_envelope.task.parameters or {}
    data = params.get("data") or {}

    # fallback to raw user request text for extraction (supervisor puts it in task.parameters.request)
    raw_request = (params.get("request") or "").strip()

    # Inspect raw input fields and only construct Pydantic models after
    # validating presence and basic types. This avoids raising Pydantic
    # ValidationError for common user inputs like "I want to find research papers".
    clarifying_questions = []

    topic = data.get("topic") if isinstance(data, dict) else None
    keywords = data.get("keywords") if isinstance(data, dict) else None
    max_results = data.get("max_results") if isinstance(data, dict) else None

    # Helper: extract year range and keywords from free-form text
    def _extract_year_range(text: str):
        if not text:
            return None
        m = re.search(r"(\d{4})\s*(?:-|to|\sto\s|and)\s*(\d{4})", text)
        if m:
            try:
                y1 = int(m.group(1))
                y2 = int(m.group(2))
                return {"from_year": min(y1, y2), "to_year": max(y1, y2)}
            except Exception:
                return None
        return None

    def _extract_keywords(text: str):
        if not text:
            return None
        m = re.search(r"keywords?[:]?>?\s*([^\n\r]+?)(?:$|from|max results|max_results)", text, flags=re.I)
        if m:
            kw_text = m.group(1).strip()
            parts = re.split(r",| and |\band\b", kw_text)
            cleaned = []
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                p = p.strip("[]()\"' ")
                if p:
                    cleaned.append(p)
            parts = cleaned
            return parts if parts else None
        m2 = re.search(r"with\s+([^\n\r]+?)\s+(?:from|max results|max_results|$)", text, flags=re.I)
        if m2:
            kw_text = m2.group(1).strip()
            parts = re.split(r",| and |\band\b", kw_text)
            parts = [p.strip().strip("[]()\"' ") for p in parts if p.strip()]
            return parts if parts else None
        return None

    # normalize keywords
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    if not keywords:
        keywords = _extract_keywords(raw_request) or []

    # normalize year_range
    year_range_raw = data.get("year_range")
    year_range_parsed = None
    if isinstance(year_range_raw, dict):
        if "from" in year_range_raw and "to" in year_range_raw:
            try:
                year_range_parsed = {"from_year": int(year_range_raw["from"]), "to_year": int(year_range_raw["to"]) }
            except Exception:
                year_range_parsed = None
        elif "from_year" in year_range_raw and "to_year" in year_range_raw:
            try:
                year_range_parsed = {"from_year": int(year_range_raw["from_year"]), "to_year": int(year_range_raw["to_year"])}
            except Exception:
                year_range_parsed = None
    elif isinstance(year_range_raw, str):
        year_range_parsed = _extract_year_range(year_range_raw)
    else:
        year_range_parsed = _extract_year_range(raw_request)

    # max_results
    if not max_results:
        m = re.search(r"max\s*results?\s*[:]?\s*(\d+)", raw_request, flags=re.I)
        if m:
            try:
                max_results = int(m.group(1))
            except Exception:
                max_results = 5

    # Basic clarifications
    if not topic:
        clarifying_questions.append({"field": "topic", "question": "What topic or subject are you researching?"})
    if not keywords:
        clarifying_questions.append({"field": "keywords", "question": "Do you have any specific keywords or phrases to search for?"})
    if year_range_parsed is None:
        clarifying_questions.append({"field": "year_range", "question": "Do you want papers from a specific year range (e.g. 2018-2023)?"})

    if clarifying_questions:
        # Build a targeted message describing what's missing and an example
        missing = []
        if not topic:
            missing.append("topic")
        if not keywords:
            missing.append("keywords")
        if year_range_parsed is None:
            missing.append("year_range")

        if len(missing) == 1:
            why = f"I need the {missing[0]} to narrow down the search."
        else:
            why = f"I need the following information: {', '.join(missing)}."

        ex_topic = topic or "machine learning"
        ex_keywords = ", ".join(keywords) if keywords else "deep learning, transformers"
        if year_range_parsed:
            ex_range = f"{year_range_parsed['from_year']}-{year_range_parsed['to_year']}"
        else:
            ex_range = "2018-2023"

        example_request = f"Find research papers about '{ex_topic}' with keywords [{ex_keywords}] from {ex_range} (max_results: 5)"

        return CompletionReport(
            message_id=str(uuid.uuid4()),
            sender="ResearchFinderAgent",
            recipient=task_envelope.sender,
            related_message_id=task_envelope.message_id,
            status="FAILURE",
            results={
                "clarification_needed": True,
                "clarifying_questions": clarifying_questions,
                "message": why + " Please provide the missing details in one message.",
                "example": example_request,
                "required_format": {
                    "topic": "string (optional)",
                    "keywords": "list[string] or comma-separated string",
                    "year_range": {"from_year": "int", "to_year": "int"},
                    "max_results": "int (optional, default 5)"
                },
                "parameters_snapshot": {
                    "provided_keys": list(params.keys()),
                    "request_preview": (raw_request[:200] if raw_request else None),
                    "data_keys": list(data.keys()) if isinstance(data, dict) else None
                }
            }
        )

    # All required fields are present in a basic form; now safely construct models
    try:
        from agents.research_scout_agent.models import YearRange

        research_input = ResearchInput(
            topic=topic,
            keywords=keywords,
            year_range=YearRange(from_year=year_range_parsed['from_year'], to_year=year_range_parsed['to_year']) if year_range_parsed else None,
            max_results=int(max_results) if max_results is not None else 5
        )
    except Exception as e:
        return CompletionReport(
            message_id=str(uuid.uuid4()),
            sender="ResearchFinderAgent",
            recipient=task_envelope.sender,
            related_message_id=task_envelope.message_id,
            status="FAILURE",
            results={"error": f"Invalid data format: {e}"}
        )

    # Search Papers
    papers = await search_papers(research_input)

    # Generate summary
    summary = generate_summary(papers, research_input.topic)

    # Prepare structured output
    output = {
        "summary": summary,
        "papers": [p.dict() for p in papers]
    }

    return CompletionReport(
        message_id=str(uuid.uuid4()),
        sender="ResearchFinderAgent",
        recipient=task_envelope.sender,
        related_message_id=task_envelope.message_id,
        status="SUCCESS",
        results=output
    )
