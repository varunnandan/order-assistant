# 📝 Order Assistant - Design Write-Up

## Architecture

The application follows a clean, decoupled **Single-Service Monolith** architecture:
- **Presentation Layer**: Vanilla HTML5, CSS3, and JavaScript served statically from `/static` via FastAPI. No heavy frontend framework or node build step was required, keeping startup latency sub-second.
- **API & Routing**: FastAPI endpoint (`POST /api/chat`) handles client requests, input validation, history windowing, and rate limiting.
- **LLM Abstraction Layer (`app/llm.py`)**: All Google Gemini SDK logic is strictly isolated in `LLMProvider`. Primary model: `gemini-3.8-flash`; fallback: `gemini-flash-latest` (both confirmed working — `gemini-2.0-flash` was retired). Swapping out Gemini for OpenAI, Anthropic, or an open-weight model requires changing only this module.
- **Agent Loop (`app/agent.py`)**: Executes an iterative tool-calling loop (capped at 5 iterations). If the LLM requests function calls, the agent executes them against Python functions, appends structured tool responses to conversation history, and iterates until a final text answer is generated.
- **Tool & Data Layer (`app/tools.py`, `app/data.py`)**: Standardized Python tools (`get_order`, `search_orders`, `calculate_metrics`, `get_dataset_info`) execute arithmetic, filtering, and city alias resolution deterministically in Python code.

---

## How the Agent Decides When to Use Tools

1. **System Prompt Instruction**: The system prompt strictly instructs the agent that it must **NEVER calculate metrics or recall order details from memory**. Every factual assertion must be backed by a tool execution.
2. **Native Function Calling**: We declare python tool signatures directly with `google-genai`. Gemini evaluates the user's intent against tool parameters and emits `FunctionCall` objects when database lookups or metric calculations are needed.
3. **Ambiguity Resolution**: When a request contains vague entity names (e.g. "Karthik" or "headphones"), the prompt directs the model to call `get_dataset_info` or `search_orders` first to inspect valid values before finalizing metrics.
4. **Resilience**: If a tool returns no records or an error (e.g., non-existent ID `ORD-9999`), the failure is fed back into the tool-calling loop as `{"ok": false, "error": "..."}` so the model can gracefully inform the user and suggest valid inputs.

---

## Guardrails & Reliability

- **LLM Resilience & Transient Fault Handling**:
  - **Exponential Backoff Retries**: Transient API errors (e.g., 503 UNAVAILABLE, 429 Rate Limit, 500, timeouts) are automatically retried up to 3 times with exponential backoff and randomized jitter (1s, 2s, 4s). Non-retryable client errors (400, 401, 403, 404) fail immediately without retrying.
  - **Explicit 30-second Timeout**: Every LLM call is made through an `httpx.Client` configured with a 30-second read timeout and 10-second connect timeout, preventing hanging requests.
  - **Secondary Model Fallback**: If the primary model (`gemini-3.8-flash`) exhausts retries due to persistent high demand, the system automatically falls back to `gemini-flash-latest`. Note: `gemini-2.0-flash` is retired (returns 404) and was never used as a fallback.
  - **Disabled SDK Auto-Calling**: SDK automatic function calling (`AutomaticFunctionCallingConfig(disable=True)`) is explicitly disabled so only our controlled agent loop executes tools and traces steps accurately.
  - **Graceful HTTP 503 Surface**: If all retries and fallback models fail, the server returns a clean HTTP 503 with `"The AI service is busy right now. Please try again in a few seconds."`, enabling the UI Retry button.
- **Scope & Prompt Injection Guard**: Pre-scans incoming user messages for prompt-injection keywords (`ignore previous instructions`, `system prompt`, `api key`) or off-topic prompts (general knowledge, coding, recipes) and returns an instant polite refusal.
- **Tool-Argument Validation**: All tool parameters are typed and validated. Unsupported fields or invalid metrics are rejected with structured error messages.
- **Strict Read-Only Access**: Data mutate operations are omitted entirely. The loaded dataset is immutable.
- **Hard Bounds**:
  - Max input message length: 1,000 characters.
  - History windowing: capped at the 10 most recent conversation turns.
  - Max tool loop iterations: 5 per request.
  - In-memory rate limiting: 20 requests per minute per IP address.
  - No secret leakage: Server exception handlers scrub stack traces and keys, returning sanitized `{"error": "..."}` JSON payloads.

---

## Deployment

The application is configured for single-service deployment on **Render**:
- `render.yaml` defines a Python web service running `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Environment variables (`GEMINI_API_KEY`, `GEMINI_MODEL`) are passed via Render's dashboard.
- The health check endpoint `GET /api/health` validates dataset readiness before serving traffic.

---

## What I Would Improve With More Time

1. **Server-Sent Events (SSE) / Streaming**: Stream model response tokens in real-time for improved user perception of speed.
2. **Persistent Sessions & Database**: Replace in-memory CSV parsing with PostgreSQL/SQLite and store chat histories persistently per user session.
3. **Automated Evaluation (Eval Set)**: Build an offline evaluation test suite checking model accuracy across 50+ benchmark questions.
4. **Caching**: Cache frequent tool query results (e.g., monthly category totals) to save LLM tokens and reduce latency.
5. **Observability**: Integrate OpenTelemetry / LangSmith tracing to monitor tool execution latency, model cost, and failure rates.

---

## AI Tools Used

- **Google Anti Gravity**: Primary agentic coding assistant used to scaffold, code, test, and write documentation.
- **Google Gemini 2.5 Flash**: Runtime LLM powering the agent's function calling and natural language reasoning.
