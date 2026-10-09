import os
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("order_assistant.llm")

class LLMProvider:
    """Isolated LLM Provider wrapper around google-genai SDK.
    To swap LLM provider (e.g. to OpenAI, Anthropic, or local model), edit this class or substitute another implementation of LLMProvider.
    """
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.client = None
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize google-genai client: {e}")

    def is_configured(self) -> bool:
        return self.client is not None or bool(self.api_key)

    def generate(
        self,
        contents: List[Any],
        system_instruction: str,
        tools: Optional[List[Any]] = None,
        temperature: float = 0.1
    ) -> Any:
        """Call Gemini model using google-genai SDK.
        Returns the raw model response object or raises a clean RuntimeError on failure.
        """
        if not self.client:
            if not self.api_key:
                raise RuntimeError("GEMINI_API_KEY environment variable is not set.")
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
                raise RuntimeError("Failed to initialize LLM provider client.")

        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
        )
        if tools:
            config.tools = tools

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config
            )
            return response
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Gemini API error: {err_msg}")
            # Sanitize error message so API key is never leaked
            if self.api_key and self.api_key in err_msg:
                err_msg = err_msg.replace(self.api_key, "[REDACTED_API_KEY]")
            raise RuntimeError(f"LLM Provider call failed: {err_msg}")
