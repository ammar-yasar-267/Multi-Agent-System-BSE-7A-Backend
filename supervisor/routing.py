"""Supervisor routing helpers.

Provides functions used by supervisor.main to decide which agent(s)
should handle a user request and to build agent-specific payloads.
"""
import logging
from typing import List, Dict, Any, Optional

from supervisor.intent_identifier import get_intent_identifier
from supervisor import registry

_logger = logging.getLogger(__name__)


async def decide_agent(payload: Any, available_agents: List[Any], conversation_history: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """Decide which agent(s) should handle the given payload.

    Args:
        payload: object or dict containing at least a `.request` string and
                 optionally an `.agentId` override.
        available_agents: list of Agent objects (from registry.list_agents())
        conversation_history: optional recent conversation for context

    Returns a dict with keys:
        - agent_ids: ordered list of candidate agent ids (primary first)
        - intent_info: raw intent identifier result
        - needs_clarification: bool
        - clarifying_questions: list
    """
    # Extract user query and optional explicit agent override
    if hasattr(payload, 'request'):
        user_query = getattr(payload, 'request')
        explicit_agent = getattr(payload, 'agentId', None) if hasattr(payload, 'agentId') else None
    elif isinstance(payload, dict):
        user_query = payload.get('request', '')
        explicit_agent = payload.get('agentId')
    else:
        user_query = str(payload)
        explicit_agent = None

    # If caller supplied an explicit agentId, try to use it (if registered)
    if explicit_agent:
        a = registry.get_agent(explicit_agent)
        if a:
            _logger.info(f"Explicit agentId provided: {explicit_agent}")
            return {
                "agent_ids": [explicit_agent],
                "intent_info": {"agent_id": explicit_agent, "confidence": 1.0, "reasoning": "Explicit agent requested by caller.", "extracted_params": {}},
                "needs_clarification": False,
                "clarifying_questions": []
            }
        else:
            _logger.warning(f"Explicit agentId {explicit_agent} not found in registry; falling back to intent identification")

    # Use the intent identifier (LLM-backed) to pick an agent
    try:
        intent_identifier = get_intent_identifier()
        intent_result = await intent_identifier.identify_intent(user_query, conversation_history)
    except Exception as e:
        _logger.error(f"Error running intent identifier: {e}")
        # Fallback: return no agents so caller can handle
        return {
            "agent_ids": [],
            "intent_info": {},
            "needs_clarification": False,
            "clarifying_questions": []
        }

    # Ensure agent id returned is normalized to registry entries
    primary_agent = intent_result.get('agent_id')
    alternative_agents = intent_result.get('alternative_agents', []) or []

    # Convert known alias 'gemini-wrapper' to registry id if present
    if primary_agent == 'gemini-wrapper':
        # prefer registry naming with _agent suffix if exists
        if registry.get_agent('gemini_wrapper_agent'):
            primary_agent = 'gemini_wrapper_agent'

    normalized_alternatives = []
    for a in alternative_agents:
        if a == 'gemini-wrapper' and registry.get_agent('gemini_wrapper_agent'):
            normalized_alternatives.append('gemini_wrapper_agent')
        else:
            normalized_alternatives.append(a)

    agent_candidates = [primary_agent] + [x for x in normalized_alternatives if x and x != primary_agent]

    needs_clarification = bool(intent_result.get('is_ambiguous', False))
    clarifying_questions = intent_result.get('clarifying_questions', []) or []

    return {
        "agent_ids": agent_candidates,
        "intent_info": intent_result,
        "needs_clarification": needs_clarification,
        "clarifying_questions": clarifying_questions
    }


def build_agent_payload(agent_id: str, user_request: str, intent_info: Dict[str, Any]) -> Dict[str, Any]:
    """Construct an agent-specific payload fragment from the user request and extracted params.

    This returns a dict that will be added as `agent_specific_data` to the
    RequestPayload forwarded to the worker.
    """
    extracted = intent_info.get('extracted_params', {}) if intent_info else {}

    # Standard default payload: put the original request under `request`
    payload = {"request": user_request}

    # Agent-specific shaping
    if agent_id in ("research_scout_agent", "research-scout-agent", "research_scout"):
        # research_scout expects a `data` object with topic/keywords/year_range/max_results
        data = {}
        if extracted.get('topic'):
            data['topic'] = extracted.get('topic')
        if extracted.get('keywords'):
            data['keywords'] = extracted.get('keywords')
        # Support multiple year_range / date formats from the intent extractor
        yr = extracted.get('year_range') or extracted.get('yearRange')
        if not yr:
            # Common alternate extracted keys
            if extracted.get('start_year') and extracted.get('end_year'):
                yr = {'from': extracted.get('start_year'), 'to': extracted.get('end_year')}
            elif extracted.get('from_year') and extracted.get('to_year'):
                yr = {'from': extracted.get('from_year'), 'to': extracted.get('to_year')}
            elif extracted.get('date_range') and isinstance(extracted.get('date_range'), str):
                # e.g. '2019-2023' or '2019 to 2023'
                dr = extracted.get('date_range')
                import re
                parts = re.findall(r"(\d{4})", dr)
                if len(parts) >= 2:
                    yr = {'from': parts[0], 'to': parts[1]}

        if isinstance(yr, dict):
            # Expect keys named 'from'/'to' or 'from_year'/'to_year'
            if 'from' in yr and 'to' in yr:
                data['year_range'] = {'from': yr['from'], 'to': yr['to']}
            elif 'from_year' in yr and 'to_year' in yr:
                data['year_range'] = {'from': yr['from_year'], 'to': yr['to_year']}
        if extracted.get('max_results'):
            data['max_results'] = extracted.get('max_results')
        # Fallbacks
        if 'keywords' not in data:
            data['keywords'] = []
        if 'topic' not in data:
            data['topic'] = user_request
        payload['data'] = data

    elif agent_id in ("gemini_wrapper_agent", "gemini-wrapper", "gemini_wrapper"):
        # General assistant expects `request` and optional model override
        if extracted.get('modelOverride'):
            payload['modelOverride'] = extracted.get('modelOverride')
        # pass-through any other extracted params
        payload.update({k: v for k, v in extracted.items() if k not in ('topic', 'keywords', 'year_range', 'max_results')})

    else:
        # Generic fallback: include extracted params under `params`
        if extracted:
            payload['parameters'] = extracted

    return payload
