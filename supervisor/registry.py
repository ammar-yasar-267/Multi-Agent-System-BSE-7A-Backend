import json
import logging
from typing import List
import httpx
import yaml

from shared.models import Agent

with open("config/settings.yaml", "r") as f:
    config = yaml.safe_load(f)

REGISTRY_FILE = config['supervisor']['registry_file']
_agents = []
_logger = logging.getLogger(__name__)

def load_registry():
    global _agents
    try:
        with open(REGISTRY_FILE, 'r') as f:
            agents_data = json.load(f)
            # Normalize agents and do not treat the file 'status' field as authoritative.
            _agents = []
            for data in agents_data:
                # Ensure required fields exist
                if 'id' not in data or 'url' not in data:
                    _logger.warning(f"Skipping invalid registry entry: {data}")
                    continue
                # Use status from file as initial value but it will be overwritten by health checks
                agent = Agent(**data)
                _agents.append(agent)
            _logger.info(f"Loaded {len(_agents)} agents from {REGISTRY_FILE}")
    except FileNotFoundError:
        _logger.error(f"Registry file not found at {REGISTRY_FILE}")
        _agents = []

async def health_check_agents():
    global _agents
    async with httpx.AsyncClient() as client:
        for agent in _agents:
            try:
                url = agent.url.rstrip('/') + '/health'
                _logger.debug(f"Checking health for {agent.id} at {url}")
                response = await client.get(url, timeout=3.0)
                # Consider healthy only if agent returns JSON with status 'healthy'
                is_healthy = False
                try:
                    json_body = response.json()
                    is_healthy = response.status_code == 200 and json_body.get('status') == 'healthy'
                except Exception:
                    is_healthy = response.status_code == 200

                agent.status = 'healthy' if is_healthy else 'offline'
            except Exception as exc:
                _logger.debug(f"Health check failed for {agent.id}: {exc}")
                agent.status = 'offline'

    # Persist updated statuses back to registry file so they are visible on restart
    try:
        save_registry_statuses()
    except Exception as e:
        _logger.warning(f"Failed to persist registry statuses: {e}")

    _logger.info("Agent health checks complete.")


def save_registry_statuses():
    """Write current agent statuses back to the registry file.

    Only the `status` field is updated to avoid changing other registry metadata.
    """
    try:
        # Load the original file to preserve ordering and extra fields
        with open(REGISTRY_FILE, 'r') as f:
            disk_agents = json.load(f)

        # Build a map of id->status from in-memory agents
        status_map = {a.id: a.status for a in _agents}

        for entry in disk_agents:
            aid = entry.get('id')
            if aid in status_map:
                entry['status'] = status_map[aid]

        with open(REGISTRY_FILE, 'w') as f:
            json.dump(disk_agents, f, indent=2)
        _logger.info(f"Persisted agent statuses to {REGISTRY_FILE}")
    except Exception as e:
        _logger.error(f"Error saving registry statuses: {e}")

def list_agents() -> List[Agent]:
    return _agents

def get_agent(agent_id: str) -> Agent | None:
    for agent in _agents:
        if agent.id == agent_id:
            return agent
    return None


async def check_agent_live_status(agent_id: str) -> str:
    """Perform a live HTTP health check for the given agent id and return status string."""
    agent = get_agent(agent_id)
    if not agent:
        return 'not_found'

    async with httpx.AsyncClient() as client:
        try:
            url = agent.url.rstrip('/') + '/health'
            resp = await client.get(url, timeout=3.0)
            try:
                j = resp.json()
                if resp.status_code == 200 and j.get('status') == 'healthy':
                    agent.status = 'healthy'
                else:
                    agent.status = 'offline'
            except Exception:
                agent.status = 'healthy' if resp.status_code == 200 else 'offline'
        except Exception as e:
            _logger.debug(f"Live health check error for {agent_id}: {e}")
            agent.status = 'offline'

    # Persist status change
    try:
        save_registry_statuses()
    except Exception:
        pass

    return agent.status
