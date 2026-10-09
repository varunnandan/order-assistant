import json
import logging
from typing import List, Dict, Any, Tuple
from app.llm import LLMProvider
from app.tools import TOOL_REGISTRY, get_order, search_orders, calculate_metrics, get_dataset_info
from app.schemas import ChatMessage, ToolCallInfo
from app.guardrails import check_offtopic_or_injection

logger = logging.getLogger("order_assistant.agent")

SYSTEM_PROMPT = """You are the Order Assistant AI for an online store.
Your sole purpose is to answer natural-language questions about customer orders using the store's dataset.

STRICT INSTRUCTIONS:
1. SCOPE: Answer questions ONLY about this store's orders dataset. If the user asks off-topic questions (e.g. general knowledge, recipes, coding, external trivia), politely refuse and invite them to ask about orders.
2. FACTS & ARITHMETIC: ALWAYS use tools for any factual claim or number. NEVER do arithmetic yourself or guess order details. Never invent order IDs or customer names.
3. DATES: The dataset year is 2026. Convert month names or relative dates into explicit ISO date ranges (YYYY-MM-DD):
   - June 2026: 2026-06-01 to 2026-06-30
   - July 2026: 2026-07-01 to 2026-07-31
   - August 2026: 2026-08-01 to 2026-08-31
   - September 2026: 2026-09-01 to 2026-09-30
4. REVENUE CONVENTION: Revenue and spend calculations EXCLUDE orders with status 'cancelled' or 'returned' by default because they were not completed sales. In your final text response, ALWAYS briefly mention which statuses were included/counted (e.g., "excluding cancelled and returned orders").
5. AMBIGUITY: If a customer name, city, or product is ambiguous, use `get_dataset_info` or `search_orders` first to check valid values.
6. EMPTY / ERROR RESULTS: When a tool returns no results or an error, state it clearly to the user and suggest valid alternatives from the tool response suggestions rather than guessing.
"""

AVAILABLE_TOOLS = [get_order, search_orders, calculate_metrics, get_dataset_info]

class OrderAgent:
    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm = llm_provider or LLMProvider()

    def run(self, user_message: str, history: List[ChatMessage]) -> Tuple[str, List[Dict[str, Any]]]:
        # Guardrail check
        if check_offtopic_or_injection(user_message):
            return (
                "I am an Order Assistant dedicated to answering questions about this store's orders. "
                "I cannot help with general knowledge or system prompt requests. "
                "Please ask me about order details, sales metrics, customers, or products!",
                []
            )

        recorded_tool_calls: List[Dict[str, Any]] = []

        # Build contents for Gemini model call
        # google-genai accepts contents as list of strings or dicts / Content objects
        contents = []
        for msg in history:
            contents.append({"role": msg.role, "parts": [{"text": msg.content}]})
        contents.append({"role": "user", "parts": [{"text": user_message}]})

        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            try:
                response = self.llm.generate(
                    contents=contents,
                    system_instruction=SYSTEM_PROMPT,
                    tools=AVAILABLE_TOOLS,
                    temperature=0.1
                )
            except Exception as e:
                logger.error(f"Error during LLM invocation: {e}")
                raise e

            # Extract response details
            # If mock LLM or real Gemini response
            function_calls = self._extract_function_calls(response)
            response_text = self._extract_text(response)

            if not function_calls:
                # Final text answer reached
                return response_text or "I searched the order database but couldn't generate a clear text answer.", recorded_tool_calls

            # Append model response turn to conversation contents
            # Process requested function calls
            tool_response_parts = []

            for call_name, call_args in function_calls:
                tool_fn = TOOL_REGISTRY.get(call_name)
                if not tool_fn:
                    tool_result = {"ok": False, "error": f"Tool '{call_name}' is not registered."}
                    summary = f"Tool '{call_name}' not found."
                    ok_status = False
                else:
                    try:
                        tool_result = tool_fn(**call_args)
                        ok_status = tool_result.get("ok", True)
                        summary = tool_result.get("summary", f"Executed {call_name}.")
                    except Exception as err:
                        tool_result = {"ok": False, "error": str(err)}
                        ok_status = False
                        summary = f"Execution of {call_name} failed: {err}"

                recorded_tool_calls.append({
                    "name": call_name,
                    "arguments": call_args,
                    "ok": ok_status,
                    "summary": summary
                })

                tool_response_parts.append({
                    "function_response": {
                        "name": call_name,
                        "response": tool_result
                    }
                })

            # Append assistant turn and tool results turn to contents
            # Format compatible with Gemini API tool execution turn
            contents.append({
                "role": "model",
                "parts": [{"function_call": {"name": name, "args": args}} for name, args in function_calls]
            })
            contents.append({
                "role": "user",
                "parts": tool_response_parts
            })

        return "I apologize, but I was unable to complete the request within the maximum allowed steps.", recorded_tool_calls

    def _extract_function_calls(self, response: Any) -> List[Tuple[str, Dict[str, Any]]]:
        calls = []
        if hasattr(response, "function_calls") and response.function_calls:
            for call in response.function_calls:
                calls.append((call.name, dict(call.args or {})))
            return calls

        if hasattr(response, "candidates") and response.candidates:
            for cand in response.candidates:
                if hasattr(cand, "content") and cand.content and hasattr(cand.content, "parts"):
                    for part in cand.content.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            fn = part.function_call
                            args = dict(fn.args) if hasattr(fn, "args") and fn.args else {}
                            calls.append((fn.name, args))
        return calls

    def _extract_text(self, response: Any) -> str:
        if hasattr(response, "text") and response.text:
            return response.text
        if hasattr(response, "candidates") and response.candidates:
            texts = []
            for cand in response.candidates:
                if hasattr(cand, "content") and cand.content and hasattr(cand.content, "parts"):
                    for part in cand.content.parts:
                        if hasattr(part, "text") and part.text:
                            texts.append(part.text)
            if texts:
                return "\n".join(texts)
        return ""
