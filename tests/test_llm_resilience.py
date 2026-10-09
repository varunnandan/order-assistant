import pytest
from unittest.mock import MagicMock, patch
from app.llm import LLMProvider, LLMNonRetryableError, LLMServiceUnavailableError, is_transient_error

from app.agent import OrderAgent

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

class MockGeminiResponse:
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

    @property
    def text(self):
        if self.candidates and getattr(self.candidates[0], "content", None):
            parts = getattr(self.candidates[0].content, "parts", [])
            texts = [getattr(p, "text", "") for p in parts if getattr(p, "text", None)]
            return "\n".join(texts)
        return ""

class MockFnCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args

def test_extract_response_parts_edge_cases():
    agent = OrderAgent(llm_provider=MagicMock())

    # Case 1: function_call part and no text
    fc_part = MockPart(function_call=MockFnCall("get_order", {"order_id": "ORD-1025"}))
    resp_fc_only = MockGeminiResponse(candidates=[MockCandidate(MockContent([fc_part]))])
    calls, text = agent._extract_response_parts(resp_fc_only)
    assert len(calls) == 1
    assert calls[0] == ("get_order", {"order_id": "ORD-1025"})
    assert text == ""

    # Case 2: text only
    text_part = MockPart(text="Order ORD-1025 is delivered.")
    resp_text_only = MockGeminiResponse(candidates=[MockCandidate(MockContent([text_part]))])
    calls, text = agent._extract_response_parts(resp_text_only)
    assert len(calls) == 0
    assert text == "Order ORD-1025 is delivered."

    # Case 3: no candidates (empty response / safety block)
    resp_empty = MockGeminiResponse(candidates=[])
    calls, text = agent._extract_response_parts(resp_empty)
    assert len(calls) == 0
    assert text == ""

    # Case 4: multiple function calls
    fc1 = MockPart(function_call=MockFnCall("get_order", {"order_id": "ORD-1001"}))
    fc2 = MockPart(function_call=MockFnCall("search_orders", {"status": "cancelled"}))
    resp_multi_fc = MockGeminiResponse(candidates=[MockCandidate(MockContent([fc1, fc2]))])
    calls, text = agent._extract_response_parts(resp_multi_fc)
    assert len(calls) == 2
    assert calls[0][0] == "get_order"
    assert calls[1][0] == "search_orders"

def test_real_genai_client_constructor_signature():
    """Construct real LLMProvider with dummy key to verify SDK Client signature options."""
    provider = LLMProvider(api_key="dummy_api_key_for_signature_test")
    assert provider.client is not None
    assert provider.is_configured() is True

def test_is_transient_error_classification():
    assert is_transient_error(Exception("503 Service Unavailable - high demand")) is True
    assert is_transient_error(Exception("429 Too Many Requests")) is True
    assert is_transient_error(Exception("500 Internal Server Error")) is True
    assert is_transient_error(Exception("Connection timed out")) is True
    
    # Non-retryable
    assert is_transient_error(Exception("404 Not Found")) is False
    assert is_transient_error(Exception("400 Invalid Argument")) is False
    assert is_transient_error(Exception("401 Unauthorized")) is False
    assert is_transient_error(Exception("403 Forbidden")) is False

@patch("time.sleep", return_value=None)
def test_primary_model_retry_success(mock_sleep):
    provider = LLMProvider(api_key="test_key", model="gemini-3.8-flash", fallback_model="gemini-flash-latest")
    
    mock_client = MagicMock()
    # Attempt 1: 503 error, Attempt 2: Success
    mock_client.models.generate_content.side_effect = [
        Exception("503 Service Unavailable high demand"),
        MockGeminiResponse("Recovered text answer")
    ]
    provider.client = mock_client

    response = provider.generate(
        contents=["Hello"],
        system_instruction="Test prompt"
    )
    assert response.text == "Recovered text answer"
    assert mock_client.models.generate_content.call_count == 2
    assert mock_sleep.call_count == 1

@patch("time.sleep", return_value=None)
def test_fallback_model_success(mock_sleep):
    provider = LLMProvider(api_key="test_key", model="gemini-3.8-flash", fallback_model="gemini-flash-latest")
    
    mock_client = MagicMock()
    # Primary model fails 3 times with 503, Fallback model succeeds on 1st try
    mock_client.models.generate_content.side_effect = [
        Exception("503 Service Unavailable"),
        Exception("503 Service Unavailable"),
        Exception("503 Service Unavailable"),
        MockGeminiResponse("Fallback model response")
    ]
    provider.client = mock_client

    response = provider.generate(
        contents=["Hello"],
        system_instruction="Test prompt"
    )
    assert response.text == "Fallback model response"
    # Primary tried 3 times, fallback tried 1 time => total 4 calls
    assert mock_client.models.generate_content.call_count == 4

@patch("time.sleep", return_value=None)
def test_non_retryable_error_fails_immediately(mock_sleep):
    provider = LLMProvider(api_key="test_key", model="gemini-3.8-flash", fallback_model="gemini-flash-latest")
    
    mock_client = MagicMock()
    # 404 Not Found error
    mock_client.models.generate_content.side_effect = Exception("404 Not Found")
    provider.client = mock_client

    with pytest.raises(LLMNonRetryableError):
        provider.generate(
            contents=["Hello"],
            system_instruction="Test prompt"
        )
    
    # Non-retryable error fails immediately without retrying or fallback
    assert mock_client.models.generate_content.call_count == 1
    assert mock_sleep.call_count == 0

@patch("time.sleep", return_value=None)
def test_all_models_transient_exhaustion(mock_sleep):
    provider = LLMProvider(api_key="test_key", model="gemini-3.8-flash", fallback_model="gemini-flash-latest")
    
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("503 Service Unavailable")
    provider.client = mock_client

    with pytest.raises(LLMServiceUnavailableError):
        provider.generate(
            contents=["Hello"],
            system_instruction="Test prompt"
        )
