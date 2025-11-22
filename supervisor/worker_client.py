import uuid
import time
import logging
import httpx
import json
from datetime import datetime
import asyncio

from pydantic import ValidationError
from shared.models import RequestPayload, RequestResponse, RequestResponseMetadata, ErrorInfo, Task, TaskEnvelope, CompletionReport, Agent
from supervisor.registry import get_agent

_logger = logging.getLogger(__name__)

# In-memory store for debugging malformed agent responses. Keyed by agent id.
# Structure: { agent_id: { 'raw_text': str or None, 'raw_json': obj or None, 'status': int, 'timestamp': iso, 'context': str }}
LAST_RAW_AGENT_RESPONSES: dict = {}

async def _check_agent_health(agent: Agent):
    """Helper to perform a single agent health check."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{agent.url}/health", timeout=2.0)
            if response.status_code == 200 and response.json().get("status") == "healthy":
                agent.status = "healthy"
                return True
    except httpx.RequestError:
        pass
    agent.status = "offline"
    return False

async def forward_to_agent(agent_id: str, payload: RequestPayload, agent_specific: dict | None = None) -> RequestResponse:
    agent = get_agent(agent_id)
    if not agent:
        msg = f"Agent {agent_id} not found in registry."
        _logger.warning(msg)
        return RequestResponse(
            response=msg,
            agentId=None,
            error=ErrorInfo(code="AGENT_NOT_FOUND", message=msg),
            metadata=RequestResponseMetadata(executionTime=0.0, agentTrace=[], participatingAgents=[], cached=False)
        )

    # If agent is not healthy, perform a quick re-check before failing.
    if agent.status != "healthy":
        _logger.warning(f"Agent {agent_id} is not healthy. Re-checking health before request.")
        if not await _check_agent_health(agent):
            _logger.error(f"Agent {agent_id} is confirmed offline.")
            msg = f"Agent {agent_id} is currently offline and cannot process requests."
            return RequestResponse(
                response=msg,
                agentId=agent.id if agent else agent_id,
                error=ErrorInfo(code="AGENT_UNAVAILABLE", message=msg),
                metadata=RequestResponseMetadata(executionTime=0.0, agentTrace=[agent.id] if agent else [], participatingAgents=[agent.id] if agent else [], cached=False)
            )
        _logger.info(f"Agent {agent_id} is now healthy. Proceeding with request.")

    # Build task parameters by combining the validated RequestPayload fields
    # with any agent-specific fields (e.g., 'data' expected by research_scout).
    task_parameters = payload.dict()
    if agent_specific and isinstance(agent_specific, dict):
        # Merge agent-specific keys, but don't overwrite non-empty existing keys
        for k, v in agent_specific.items():
            if k not in task_parameters or task_parameters.get(k) in (None, ""):
                task_parameters[k] = v

    task_envelope = TaskEnvelope(
        message_id=str(uuid.uuid4()),
        sender="SupervisorAgent_Main",
        recipient=agent.id,
        task=Task(name="process_request", parameters=task_parameters)
    )

    start_time = time.time()
    last_exception = None
    # Try up to 2 attempts to handle flaky/warm-up first responses
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient() as client:
                # Log the outgoing envelope for debugging agent payload issues
                try:
                    params = task_envelope.task.parameters
                    _logger.info(f"Sending task to {agent.id}; attempt={attempt}; parameter keys={list(params.keys())}; has_data={'data' in params}")
                except Exception:
                    _logger.info(f"Sending task to {agent.id}; attempt={attempt}; parameter summary unavailable")

                response = await client.post(
                    f"{agent.url}/process",
                    content=task_envelope.json(),
                    headers={"Content-Type": "application/json"},
                    timeout=15.0,
                )
            response.raise_for_status()

            # Try to parse JSON, but if the agent returned non-JSON, capture
            # the raw text so we can log it for debugging.
            try:
                completion_report_data = response.json()
            except Exception as je:
                raw_text = None
                try:
                    raw_text = response.text
                except Exception:
                    raw_text = f"<unreadable response; status={response.status_code}>"
                _logger.warning(f"Failed to parse JSON from agent {agent_id} (status={response.status_code}): {je}")
                _logger.warning(f"Raw response text: {raw_text}")
                # Persist raw response for debugging
                try:
                    LAST_RAW_AGENT_RESPONSES[agent_id] = {
                        "raw_text": raw_text,
                        "raw_json": None,
                        "status": response.status_code,
                        "timestamp": datetime.utcnow().isoformat(),
                        "context": "non-json response"
                    }
                except Exception:
                    pass
                # Treat raw text as a single output value
                completion_report_data = {"results": {"output": raw_text}, "status": "SUCCESS" if response.status_code == 200 else "FAILURE"}

            try:
                completion_report = CompletionReport(**completion_report_data)
            except ValidationError as ve:
                _logger.warning(f"CompletionReport validation failed for agent {agent_id}: {ve}")
                try:
                    _logger.warning(f"Raw completion report data: {completion_report_data}")
                    LAST_RAW_AGENT_RESPONSES[agent_id] = {
                        "raw_text": None,
                        "raw_json": completion_report_data,
                        "status": response.status_code,
                        "timestamp": datetime.utcnow().isoformat(),
                        "context": "validation_error"
                    }
                except Exception:
                    _logger.warning("Raw completion report data unavailable for logging")

                # Build a fallback CompletionReport structure
                try:
                    status = completion_report_data.get("status") if isinstance(completion_report_data, dict) else None
                except Exception:
                    status = None

                if not status:
                    status = "SUCCESS" if response.status_code == 200 else "FAILURE"

                results = None
                if isinstance(completion_report_data, dict):
                    results = completion_report_data.get("results") or completion_report_data
                else:
                    results = {"output": str(completion_report_data)}

                completion_report = CompletionReport(
                    message_id=completion_report_data.get("message_id") if isinstance(completion_report_data, dict) and completion_report_data.get("message_id") else str(uuid.uuid4()),
                    sender=completion_report_data.get("sender") if isinstance(completion_report_data, dict) and completion_report_data.get("sender") else agent.id if agent else "unknown",
                    recipient=completion_report_data.get("recipient") if isinstance(completion_report_data, dict) and completion_report_data.get("recipient") else "Supervisor",
                    related_message_id=completion_report_data.get("related_message_id") if isinstance(completion_report_data, dict) and completion_report_data.get("related_message_id") else task_envelope.message_id,
                    status=status,
                    results=results or {},
                )

            execution_time = (time.time() - start_time) * 1000

            # If this attempt produced a SUCCESS, or if it's the second attempt,
            # proceed to normalize and return. If first attempt failed (non-SUCCESS),
            # wait briefly and retry once.
            if completion_report.status == "SUCCESS" or attempt == 2:
                if completion_report.status == "SUCCESS":
                    results = completion_report.results or {}
                    output_candidate = None
                    if isinstance(results, dict):
                        output_candidate = results.get("output") or results.get("summary")

                    if output_candidate is None:
                        try:
                            response_text = json.dumps(results)
                        except Exception:
                            response_text = str(results)
                    else:
                        response_text = output_candidate if isinstance(output_candidate, str) else json.dumps(output_candidate)

                    # If the agent returned structured papers, append a readable list
                    # so the frontend (which displays `response`) shows the actual papers.
                    try:
                        if isinstance(results, dict) and isinstance(results.get("papers"), list):
                            papers = results.get("papers")
                            lines = ["", "Papers:"]
                            for p in papers:
                                # p may be a dict or object; try dict access
                                if isinstance(p, dict):
                                    title = p.get("title")
                                    authors = p.get("authors")
                                    year = p.get("year")
                                    source = p.get("source")
                                    link = p.get("link")
                                    key_points = p.get("key_points") or p.get("keyPoints") or p.get("keypoints") or []
                                else:
                                    # fallback if it's a model instance
                                    title = getattr(p, 'title', None)
                                    authors = getattr(p, 'authors', None)
                                    year = getattr(p, 'year', None)
                                    source = getattr(p, 'source', None)
                                    link = getattr(p, 'link', None)
                                    key_points = getattr(p, 'key_points', None) or getattr(p, 'keyPoints', None) or []

                                meta = f"{title or 'Untitled'}"
                                if authors:
                                    meta += f" — {authors}"
                                if year:
                                    meta += f" ({year})"
                                if source:
                                    meta += f" [{source}]"
                                if link:
                                    meta += f" — {link}"

                                lines.append(f"- {meta}")
                                if key_points:
                                    for kp in key_points:
                                        lines.append(f"    • {kp}")

                            response_text = response_text + "\n" + "\n".join(lines)
                    except Exception:
                        # Don't fail the whole flow if formatting papers fails
                        pass

                    response_dict = {
                        "response": response_text,
                        "agentId": agent.id,
                        "timestamp": datetime.utcnow(),
                        "metadata": {
                            "executionTime": execution_time,
                            "agentTrace": [agent.id],
                            "participatingAgents": [agent.id],
                            "cached": bool(results.get("cached")) if isinstance(results, dict) else False
                        }
                    }
                    return RequestResponse.model_validate(response_dict)
                else:
                    # If the agent indicates it needs clarification, return a
                    # structured error that the supervisor can turn into a
                    # clarification request to the user.
                    results_obj = completion_report.results or {}
                    if isinstance(results_obj, dict) and results_obj.get("clarification_needed"):
                        # Include full results in details so supervisor can craft
                        # a precise clarification prompt including examples.
                        msg = results_obj.get("message") or "I need more information to proceed."
                        try:
                            details_payload = json.dumps(results_obj)
                        except Exception:
                            details_payload = json.dumps({"clarifying_questions": results_obj.get("clarifying_questions", [])})
                        return RequestResponse(
                            response=msg,
                            agentId=agent.id,
                            timestamp=datetime.utcnow(),
                            error=ErrorInfo(code="CLARIFICATION_NEEDED", message=msg, details=details_payload),
                            metadata=RequestResponseMetadata(executionTime=execution_time, agentTrace=[agent.id], participatingAgents=[agent.id], cached=False)
                        )

                    response_dict = {
                        "agentId": agent.id,
                        "timestamp": datetime.utcnow(),
                        "error": {
                            "code": "AGENT_EXECUTION_ERROR",
                            "message": completion_report.results.get("error", "Agent failed to process the request.")
                        },
                        "metadata": {
                            "executionTime": execution_time,
                            "agentTrace": [agent.id],
                            "participatingAgents": [agent.id],
                            "cached": False
                        }
                    }
                    return RequestResponse.model_validate(response_dict)
            else:
                # first attempt failed but not an exception; retry once after short delay
                _logger.info(f"Attempt {attempt} to agent {agent_id} did not succeed; retrying after short delay")
                await asyncio.sleep(0.5)
                continue
        except Exception as e:
            last_exception = e
            # if network-level error, break and return handled below
            _logger.exception(f"Exception during attempt {attempt} forwarding to agent {agent_id}: {e}")
            # if this was first attempt, try one more; else break
            if attempt == 1:
                await asyncio.sleep(0.5)
                continue
            else:
                break

    # If we exit loop without returning, handle the last exception or return a communication error
    if last_exception:
        _logger.error(f"Final failure forwarding to agent {agent_id}: {last_exception}")
        if agent:
            agent.status = "offline"
        msg = f"Failed to communicate with agent {agent_id}. Please try again later."
        return RequestResponse(
            response=msg,
            agentId=agent.id if agent else agent_id,
            error=ErrorInfo(code="COMMUNICATION_ERROR", message=msg, details=str(last_exception)),
            metadata=RequestResponseMetadata(executionTime=0.0, agentTrace=[agent.id] if agent else [], participatingAgents=[agent.id] if agent else [], cached=False)
        )

    # Fallback unexpected error
    msg = f"An unexpected error occurred while processing the response from agent {agent_id}."
    return RequestResponse(
        response=msg,
        agentId=agent.id if agent else agent_id,
        error=ErrorInfo(code="UNEXPECTED_ERROR", message=msg),
        metadata=RequestResponseMetadata(executionTime=0.0, agentTrace=[agent.id] if agent else [], participatingAgents=[agent.id] if agent else [], cached=False)
    )
