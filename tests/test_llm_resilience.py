import pytest
from unittest.mock import MagicMock, patch
from app.llm import LLMProvider, LLMNonRetryableError, LLMServiceUnavailableError, is_transient_error

class MockGeminiResponse:
    def __init__(self, text="Response OK"):
        self.text = text
        self.function_calls = []

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
