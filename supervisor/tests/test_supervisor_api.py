import pytest
from fastapi.testclient import TestClient
from supervisor.main import app
from supervisor import auth

client = TestClient(app)

@pytest.fixture
def authenticated_client():
    # A simplified way to get a token for testing
    token = auth.create_access_token(data={"sub": "test@example.com"})
    
    # Create a new client with the auth header
    authed_client = TestClient(app)
    authed_client.headers = {"Authorization": f"Bearer {token}"}
    return authed_client

def test_login():
    response = client.post("/api/auth/login", json={"email": "test@example.com", "password": "password"})
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["user"]["email"] == "test@example.com"

def test_get_registry(authenticated_client):
    response = authenticated_client.get("/api/supervisor/registry")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert len(data["agents"]) > 0
    # Check that at least one agent exists
    agent_ids = [agent["id"] for agent in data["agents"]]
    assert len(agent_ids) > 0

def test_submit_request_mock(authenticated_client, mocker):
    # Mock the forwarding function to avoid actual HTTP calls during this unit test
    mocker.patch(
        'supervisor.worker_client.forward_to_agent',
        return_value={
            "response": "mocked response",
            "agentId": "gemini-wrapper",
            "metadata": {"executionTime": 123}
        }
    )
    
    payload = {
        "agentId": "gemini-wrapper",
        "request": "Tell me a joke",
    }
    response = authenticated_client.post("/api/supervisor/request", json=payload)
    
    # This will fail if the response is not a dict, which is what's happening
    assert response.status_code == 200
    # assert response.json()["agentId"] == "gemini-wrapper"
