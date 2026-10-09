import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.schemas import ChatMessage
from app.agent import OrderAgent
from app.guardrails import rate_limiter

client = TestClient(app)

class MockPart:
    def __init__(self, text=None, function_call=None):
        self.text = text
        self.function_call = function_call

class MockContent:
    def __init__(self, parts=None):
        self.parts = parts or []

class MockCandidate:
    def __init__(self, content=None):
        self.content = content

class MockLLMResponse:
    def __init__(self, text=None, function_calls=None, candidates=None):
        if candidates is not None:
            self.candidates = candidates
        else:
            parts = []
            if text:
                parts.append(MockPart(text=text))
            if function_calls:
                for fc in function_calls:
                    parts.append(MockPart(function_call=fc))
            self.candidates = [MockCandidate(MockContent(parts))] if parts else []

class MockFunctionCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args

class MockLLMProvider:
    def __init__(self, script=None):
        self.script = script or []
        self.call_count = 0

    def generate(self, contents, system_instruction, tools=None, temperature=0.1):
        if self.call_count < len(self.script):
            res = self.script[self.call_count]
            self.call_count += 1
            return res
        return MockLLMResponse(text="Default mock answer.")

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["orders_loaded"] == 60
    assert "llm_ready" in data

def test_api_validation_errors():
    # Empty message
    res = client.post("/api/chat", json={"message": "   "})
    assert res.status_code == 422
    assert "error" in res.json()

    # Exceed 1000 chars
    res = client.post("/api/chat", json={"message": "a" * 1001})
    assert res.status_code == 422
    assert "error" in res.json()

    # Invalid history role
    res = client.post("/api/chat", json={
        "message": "Hello",
        "history": [{"role": "system", "content": "bad role"}]
    })
    assert res.status_code == 422
    assert "error" in res.json()

def test_rate_limiter():
    test_ip = "192.168.1.100"
    # Reset history
    rate_limiter.ip_history[test_ip] = []

    # Send 20 requests
    for i in range(20):
        assert rate_limiter.is_rate_limited(test_ip) is False

    # 21st request triggers rate limit
    assert rate_limiter.is_rate_limited(test_ip) is True

def test_agent_tool_loop_and_trace():
    # Mock LLM scripts:
    # Turn 1: Model returns tool call get_order(order_id='ORD-1025')
    # Turn 2: Model returns final answer based on tool result
    mock_llm = MockLLMProvider(script=[
        MockLLMResponse(function_calls=[MockFunctionCall("get_order", {"order_id": "ORD-1025"})]),
        MockLLMResponse(text="Order ORD-1025 was placed by Karthik Rao for a Wireless Mouse (INR 2397) and status is delivered.")
    ])

    agent = OrderAgent(llm_provider=mock_llm)
    reply, tool_calls = agent.run("What is order ORD-1025?", [])

    assert "Karthik Rao" in reply
    assert len(tool_calls) == 1
    assert tool_calls[0]["name"] == "get_order"
    assert tool_calls[0]["ok"] is True
    assert tool_calls[0]["arguments"] == {"order_id": "ORD-1025"}

def test_agent_tool_failure_recovery():
    # Mock LLM scripts:
    # Turn 1: Tool call that returns no results / error
    # Turn 2: Model recovers and gives clear response
    mock_llm = MockLLMProvider(script=[
        MockLLMResponse(function_calls=[MockFunctionCall("get_order", {"order_id": "ORD-9999"})]),
        MockLLMResponse(text="No order found with ID ORD-9999. Valid IDs range from ORD-1001 to ORD-1060.")
    ])

    agent = OrderAgent(llm_provider=mock_llm)
    reply, tool_calls = agent.run("Check ORD-9999", [])

    assert "ORD-9999" in reply
    assert len(tool_calls) == 1
    assert tool_calls[0]["ok"] is False

def test_agent_max_iterations_cutoff():
    # Mock LLM that endlessly returns tool calls
    mock_llm = MockLLMProvider(script=[
        MockLLMResponse(function_calls=[MockFunctionCall("get_dataset_info", {})])
        for _ in range(10)
    ])

    agent = OrderAgent(llm_provider=mock_llm)
    reply, tool_calls = agent.run("Loop test", [])

    assert "unable to complete the request" in reply
    assert len(tool_calls) == 5

def test_offtopic_refusal():
    agent = OrderAgent(llm_provider=MockLLMProvider())
    reply, tool_calls = agent.run("Tell me a recipe for chocolate cake and write a code", [])
    assert "Order Assistant" in reply
    assert len(tool_calls) == 0
