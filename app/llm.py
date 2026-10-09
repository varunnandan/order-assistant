import os
import time
import random
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("order_assistant.llm")

class LLMServiceUnavailableError(RuntimeError):
    """Raised when LLM service is busy or unavailable after retries and fallback."""
    pass

class LLMNonRetryableError(RuntimeError):
    """Raised when LLM service encounters a non-retryable error (e.g. 400, 401, 403, 404)."""
    pass

def is_transient_error(error: Exception) -> bool:
    """Determine if an error is transient (e.g., 503, 429, 500, timeout, connection drop).
    Returns False for non-retryable client errors (400, 401, 403, 404).
    """
    err_str = str(error).lower()
    
    # Non-retryable HTTP status codes or keywords
    non_retryable_codes = ["400", "401", "403", "404", "invalid_argument", "unauthorized", "forbidden", "not_found"]
    for code in non_retryable_codes:
        if f"status_code={code}" in err_str or f"status code {code}" in err_str or f"{code} " in err_str:
            return False

    # Transient error indicators
    transient_indicators = [
        "503", "429", "500", "502", "504",
        "unavailable", "high demand", "busy", "quota", "rate limit",
        "timeout", "timed out", "connection", "overloaded", "resource_exhausted"
    ]
    for indicator in transient_indicators:
        if indicator in err_str:
            return True

    # Check exception attributes if available (e.g., HTTP status code attributes)
    status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if status_code is not None:
        try:
            code_int = int(status_code)
            if code_int in [400, 401, 403, 404]:
                return False
            if code_int in [429, 500, 502, 503, 504]:
                return True
        except (ValueError, TypeError):
            pass

    # Default to transient for unexpected runtime API errors unless explicitly non-retryable
    return True

class LLMProvider:
    """Isolated LLM Provider wrapper with exponential backoff retries and model fallback."""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, fallback_model: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.primary_model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.fallback_model = fallback_model or os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.0-flash")
        self.client = None
        
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize google-genai client: {e}")

    def is_configured(self) -> bool:
        return self.client is not None or bool(self.api_key)

    def _call_model_with_retries(
        self,
        model_name: str,
        contents: List[Any],
        system_instruction: str,
        tools: Optional[List[Any]] = None,
        temperature: float = 0.1,
        max_retries: int = 3,
        base_delay: float = 1.0
    ) -> Any:
        """Execute model call with exponential backoff and jitter for transient errors."""
        if not self.client:
            if not self.api_key:
                raise LLMNonRetryableError("GEMINI_API_KEY environment variable is not set.")
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
                raise LLMNonRetryableError("Failed to initialize LLM provider client.")

        from google.genai import types

        # Build config with automatic function calling disabled
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        )
        if tools:
            config.tools = tools

        last_exception = None

        for attempt in range(1, max_retries + 1):
            try:
                # Execute API call
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )
                return response
            except Exception as e:
                last_exception = e
                err_msg = str(e)
                if self.api_key and self.api_key in err_msg:
                    err_msg = err_msg.replace(self.api_key, "[REDACTED_API_KEY]")

                if not is_transient_error(e):
                    logger.error(f"Non-retryable LLM error on model {model_name}: {err_msg}")
                    raise LLMNonRetryableError(f"Non-retryable error: {err_msg}") from e

                if attempt < max_retries:
                    # Exponential backoff with jitter: 1s, 2s, 4s + jitter
                    delay = (base_delay * (2 ** (attempt - 1))) + random.uniform(0.0, 0.5)
                    logger.warning(
                        f"Transient error calling {model_name} (attempt {attempt}/{max_retries}): {err_msg}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.warning(f"Model {model_name} failed all {max_retries} attempts.")

        raise last_exception

    def generate(
        self,
        contents: List[Any],
        system_instruction: str,
        tools: Optional[List[Any]] = None,
        temperature: float = 0.1
    ) -> Any:
        """Generate content trying primary model first (with retries), falling back to fallback model if transient error persists."""
        # 1. Try Primary Model
        try:
            return self._call_model_with_retries(
                model_name=self.primary_model,
                contents=contents,
                system_instruction=system_instruction,
                tools=tools,
                temperature=temperature,
                max_retries=3
            )
        except LLMNonRetryableError:
            raise
        except Exception as primary_err:
            if not is_transient_error(primary_err):
                raise LLMNonRetryableError(str(primary_err)) from primary_err

            # 2. Try Fallback Model if primary failed due to transient error
            logger.warning(
                f"Primary model '{self.primary_model}' exhausted retries with transient error: {primary_err}. "
                f"Switching to fallback model '{self.fallback_model}'..."
            )
            try:
                return self._call_model_with_retries(
                    model_name=self.fallback_model,
                    contents=contents,
                    system_instruction=system_instruction,
                    tools=tools,
                    temperature=temperature,
                    max_retries=2
                )
            except LLMNonRetryableError:
                raise
            except Exception as fallback_err:
                logger.error(f"Fallback model '{self.fallback_model}' also failed: {fallback_err}")
                raise LLMServiceUnavailableError(
                    "The AI service is busy right now. Please try again in a few seconds."
                ) from fallback_err
