import os
import time
import random
import logging
from typing import List, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("order_assistant.llm")

# Request timeout in milliseconds for every LLM call
LLM_REQUEST_TIMEOUT_MS = 30000

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

    # Non-retryable HTTP status codes or keywords — fail immediately
    non_retryable = ["400", "401", "403", "404", "invalid_argument",
                     "unauthorized", "forbidden", "not_found"]
    for code in non_retryable:
        if (f"status_code={code}" in err_str
                or f"status code {code}" in err_str
                or f" {code} " in err_str
                or err_str.startswith(code + " ")):
            return False

    # Transient error indicators
    transient_indicators = [
        "503", "429", "500", "502", "504",
        "unavailable", "high demand", "busy", "quota", "rate limit",
        "timeout", "timed out", "connection", "overloaded", "resource_exhausted",
    ]
    for indicator in transient_indicators:
        if indicator in err_str:
            return True

    # Inspect numeric status_code attribute if present
    for attr in ("status_code", "code"):
        val = getattr(error, attr, None)
        if val is not None:
            try:
                code_int = int(val)
                if code_int in (400, 401, 403, 404):
                    return False
                if code_int in (429, 500, 502, 503, 504):
                    return True
            except (ValueError, TypeError):
                pass

    # Default: treat unknown runtime errors as transient
    return True


class LLMProvider:
    """Isolated LLM Provider wrapper around google-genai SDK.

    To swap providers (e.g. OpenAI, Anthropic, local model), replace the body
    of ``_call_model_with_retries`` and ``__init__`` in this single class.

    Reliability features:
    - Explicit 30-second per-request timeout via ``httpx_client_timeout``.
    - Up to 3 retries with exponential backoff + jitter (1s, 2s, 4s) for
      transient errors (503, 429, 500, timeouts). Non-retryable client errors
      (400, 401, 403, 404) fail immediately.
    - Automatic fallback to ``GEMINI_FALLBACK_MODEL`` when the primary model
      exhausts retries.
    - SDK automatic function calling is explicitly disabled so that only our
      controlled agent loop (app/agent.py, max 5 iterations) executes tools.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        fallback_model: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        # gemini-3.8-flash is confirmed working (gemini-2.0-flash is retired)
        self.primary_model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.fallback_model = (
            fallback_model
            or os.getenv("GEMINI_FALLBACK_MODEL", "gemini-flash-latest")
        )
        self.client = None

        if self.api_key:
            self._init_client()

    def _init_client(self):
        try:
            from google import genai
            from google.genai import types

            # Set 30s timeout via supported SDK http_options
            http_opts = types.HttpOptions(timeout=LLM_REQUEST_TIMEOUT_MS)
            self.client = genai.Client(api_key=self.api_key, http_options=http_opts)
            logger.info("Successfully initialized google-genai client with 30s timeout.")
        except Exception as e:
            logger.error(f"Failed to initialize google-genai client: {e}")
            self.client = None

    def is_configured(self) -> bool:
        return self.client is not None

    def _call_model_with_retries(
        self,
        model_name: str,
        contents: List[Any],
        system_instruction: str,
        tools: Optional[List[Any]] = None,
        temperature: float = 0.1,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> Any:
        """Execute a model call with exponential backoff and jitter for transient errors."""
        if not self.client:
            if not self.api_key:
                raise LLMNonRetryableError(
                    "GEMINI_API_KEY environment variable is not set."
                )
            self._init_client()
            if not self.client:
                raise LLMNonRetryableError("Failed to initialize LLM provider client.")

        from google.genai import types

        # Disable SDK automatic function calling — our agent loop handles tools
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        )
        if tools:
            config.tools = tools

        last_exception = None

        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
                return response

            except Exception as e:
                last_exception = e
                err_msg = str(e)
                # Scrub API key from logs before writing
                if self.api_key and self.api_key in err_msg:
                    err_msg = err_msg.replace(self.api_key, "[REDACTED_API_KEY]")

                if not is_transient_error(e):
                    logger.error(
                        f"Non-retryable LLM error on model {model_name}: {err_msg}"
                    )
                    raise LLMNonRetryableError(
                        f"Non-retryable error: {err_msg}"
                    ) from e

                if attempt < max_retries:
                    # Exponential back-off: 1s, 2s, 4s + up to 0.5s jitter
                    delay = (base_delay * (2 ** (attempt - 1))) + random.uniform(
                        0.0, 0.5
                    )
                    logger.warning(
                        f"Transient error calling {model_name} "
                        f"(attempt {attempt}/{max_retries}): {err_msg}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.warning(
                        f"Model {model_name} failed all {max_retries} attempts."
                    )

        raise last_exception  # re-raise final exception for caller to handle

    def generate(
        self,
        contents: List[Any],
        system_instruction: str,
        tools: Optional[List[Any]] = None,
        temperature: float = 0.1,
    ) -> Any:
        """Generate content, retrying on the primary model then falling back if needed."""
        # 1. Try primary model with up to 3 retries
        try:
            return self._call_model_with_retries(
                model_name=self.primary_model,
                contents=contents,
                system_instruction=system_instruction,
                tools=tools,
                temperature=temperature,
                max_retries=3,
            )
        except LLMNonRetryableError:
            raise
        except Exception as primary_err:
            if not is_transient_error(primary_err):
                raise LLMNonRetryableError(str(primary_err)) from primary_err

            # 2. Primary exhausted — try fallback model
            logger.warning(
                f"Primary model '{self.primary_model}' exhausted retries "
                f"({primary_err}). Switching to fallback '{self.fallback_model}'..."
            )
            try:
                return self._call_model_with_retries(
                    model_name=self.fallback_model,
                    contents=contents,
                    system_instruction=system_instruction,
                    tools=tools,
                    temperature=temperature,
                    max_retries=2,
                )
            except LLMNonRetryableError:
                raise
            except Exception as fallback_err:
                logger.error(
                    f"Fallback model '{self.fallback_model}' also failed: {fallback_err}"
                )
                raise LLMServiceUnavailableError(
                    "The AI service is busy right now. Please try again in a few seconds."
                ) from fallback_err
