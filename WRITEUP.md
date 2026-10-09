# Order Assistant - Design Write-Up

## Architecture

The application follows a decoupled **Single-Service Monolith** architecture:
- **Presentation Layer**: Vanilla HTML5, CSS3, and JavaScript served statically from `/static` via FastAPI. No heavy frontend framework or Node build step is required.
- **API & Routing**: FastAPI endpoint (`POST /api/chat`) handles client requests, Pydantic v2 input validation, history windowing, and rate limiting.
- **LLM Abstraction Layer (`app/llm.py`)**: All Google Gemini SDK logic is strictly isolated in `LLMProvider`. Primary model is `gemini-3.8-flash`; fallback model is `gemini-flash-latest`. Swapping out Gemini for OpenAI, Anthropic, or an open-weight model requires editing only this module.
- **Agent Loop (`app/agent.py`)**: Executes an iterative tool-calling loop capped at 5 iterations. Automatic function calling in the SDK is explicitly disabled (`automatic_function_calling=AutomaticFunctionCallingConfig(disable=True)`), so our custom agent loop is the single authority executing tools, handling tool errors, and recording tool call traces.
- **Tool & Data Layer (`app/tools.py`, `app/data.py`)**: Standardized Python tools (`get_order`, `search_orders`, `calculate_metrics`, `get_dataset_info`) execute arithmetic, filtering, and city alias resolution deterministically in Python code over `data/orders.csv`.

---

## How the Agent Decides When to Use Tools

1. **System Prompt Instruction**: The system prompt strictly instructs the agent to **NEVER calculate metrics or recall order details from memory**. Every factual assertion must originate from a tool call.
2. **Native Function Calling**: Python tool signatures are passed to `google-genai`. Gemini evaluates user intent against tool declarations and returns function calls when data queries or aggregations are needed.
3. **Ambiguity Resolution**: When entity names (e.g., "Karthik" or "headphones") are ambiguous, the system prompt instructs the agent to invoke `get_dataset_info` or `search_orders` first to discover valid values before running metrics.
4. **Resilience**: If a tool returns no results or an error (e.g., nonexistent ID `ORD-9999`), the failure is fed back into the agent loop as `{"ok": false, "error": "..."}` so the model can explain the outcome and suggest valid alternatives.

---

## Guardrails

- **LLM Resilience & Retry Logic**:
  - **Exponential Backoff Retries**: Transient API errors (503, 429, 500, timeouts) are automatically retried up to 3 times per model with exponential backoff and randomized jitter (1s, 2s, 4s). Non-retryable client errors (400, 401, 403, 404) fail immediately without retrying.
  - **Fallback Model**: If `gemini-3.8-flash` exhausts retries due to persistent high demand, the system automatically falls back to `gemini-flash-latest`.
  - **Explicit Timeout**: LLM API calls use a 30-second timeout (`HttpOptions(timeout=30000)`).
  - **Graceful HTTP 503 Surface**: If all retries and fallback models fail, the server returns an HTTP 503 response (`"The AI service is busy right now. Please try again in a few seconds."`), triggering the UI Retry button.
- **Scope & Prompt Injection Filter**: Pre-scans incoming user messages for prompt-injection keywords (`ignore instructions`, `system prompt`, `api key`) or off-topic queries and returns an immediate refusal.
- **Tool-Argument Validation**: Tool parameters are typed and validated; invalid inputs return structured errors.
- **Read-Only Access**: Data mutation operations are omitted. The dataset is immutable.
- **Hard Bounds**:
  - Max input message length: 1,000 characters.
  - History windowing: capped at the 10 most recent conversation turns.
  - Max tool loop iterations: 5 per request.
  - In-memory rate limiting: 20 requests per minute per IP address.
  - Secret protection: Exception handlers scrub stack traces and keys from responses.

---

## Deployment

The application is deployed as a single Web Service on **Render**:
- `render.yaml` defines a Python web service running `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Environment variables (`GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL`) are set in the Render Dashboard.
- The health check path `/api/health` validates dataset readiness (`orders_loaded`) and LLM configuration (`llm_ready`).

---

## What I Would Improve With More Time

1. **Streaming (SSE)**: Stream response tokens to reduce perceived latency.
2. **Persistent Sessions & Database**: Replace CSV loading with PostgreSQL/SQLite and persist session histories.
3. **Automated Evaluation Set**: Build an offline benchmark suite of 50+ query variations to evaluate tool accuracy.
4. **Response Caching**: Cache common tool query results to reduce API calls and latency.
5. **Observability**: Integrate OpenTelemetry tracing to track tool execution duration and model performance.

---

## AI Tools Used

- **Google Anti Gravity**: Primary agentic coding assistant used to scaffold, implement, test, and document the application.
- **Google Gemini**: Runtime LLM powering function calling, model fallback, and natural-language responses.
