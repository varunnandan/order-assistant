# Order Assistant

A production-grade AI-powered web chat application for querying an online store's orders dataset using FastAPI, Google Gemini tool calling, and a responsive vanilla frontend.

**Live Demo**: [https://order-assistant-0gww.onrender.com](https://order-assistant-0gww.onrender.com)  
*(Note: Render free tier services cold-start on idle; the initial request may take 30–60 seconds).*

---

## Features

- **Tool-Calling Agent**: Executes 4 deterministic Python tools (`get_order`, `search_orders`, `calculate_metrics`, `get_dataset_info`) to answer factual order and metric questions.
- **UI Tool Execution Steps**: Collapsible "Steps" panel under each assistant response displaying tool names, formatted JSON arguments, execution status, and summaries.
- **Input Validation**: Strict message length limits (1–1000 chars), history windowing (last 10 turns), and Pydantic v2 schema enforcement.
- **Rate Limiting**: Sliding-window rate limiter restricting requests to 20 per minute per IP address.
- **Resilience & Fallback**: Up to 3 retries with exponential backoff and jitter for transient errors (503, 429, 500, timeouts), automatic fallback from primary (`gemini-3.8-flash`) to fallback model (`gemini-flash-latest`), and 30-second per-request timeout.
- **Guardrails**: Prompt-injection awareness and off-topic request refusal protecting system integrity.

---

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, Pydantic v2, Uvicorn
- **AI / LLM**: Official Google Gemini SDK (`google-genai==2.29.0`) with native function calling
- **Frontend**: Vanilla HTML5, CSS3, JavaScript (served static via FastAPI)
- **Testing**: `pytest` + FastAPI `TestClient` (100% offline runnable with mock LLM)
- **Deployment**: Render Web Service (`render.yaml`)

---

## Quick Start

### Prerequisites
- Python 3.11 or higher
- A free Google Gemini API Key from [Google AI Studio](https://aistudio.google.com)

### Installation & Execution

#### macOS / Linux
```bash
# 1. Clone repository
git clone https://github.com/varunnandan/order-assistant.git
cd order-assistant

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env and paste your GEMINI_API_KEY

# 5. Start development server
uvicorn app.main:app --reload
```

#### Windows (PowerShell)
```powershell
# 1. Clone repository
git clone https://github.com/varunnandan/order-assistant.git
cd order-assistant

# 2. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
Copy-Item .env.example .env
# Edit .env and paste your GEMINI_API_KEY

# 5. Start development server
uvicorn app.main:app --reload
```

Open `http://localhost:8000` in your browser.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | Yes | — | Google Gemini API key from Google AI Studio |
| `GEMINI_MODEL` | No | `gemini-3.8-flash` | Primary Gemini model for agent function calling |
| `GEMINI_FALLBACK_MODEL` | No | `gemini-flash-latest` | Fallback model if primary model fails with transient errors |
| `HOST` | No | `0.0.0.0` | Host interface for server binding |
| `PORT` | No | `8000` | Port for server binding |

---

## Running Tests

All unit, integration, and guardrail tests run offline using a mock LLM client and require no API key:

```bash
pytest -q
```

---

## Example Questions to Try

1. **Order Lookup**: *"What is the status of order ORD-1025?"*
2. **Status Metrics**: *"How many orders were cancelled?"*
3. **Revenue Calculation**: *"What was the total revenue from Electronics in August?"*
4. **Top Customer**: *"Which customer has spent the most?"*
5. **Non-Existent Order**: *"What is the status of order ORD-9999?"*
6. **City Alias / Typo**: *"Show orders from Trivandrum"*
7. **Follow-Up Question**: *"What about Kochi?"*

---

## API Reference

### Health Check
`GET /api/health`

**Response (`200 OK`)**:
```json
{
  "status": "ok",
  "orders_loaded": 60,
  "llm_ready": true
}
```

### Chat Endpoint
`POST /api/chat`

**Request (`200 OK`)**:
```json
{
  "message": "What is the status of order ORD-1025?",
  "history": [
    { "role": "user", "content": "Hi" },
    { "role": "assistant", "content": "Hello! How can I help you with orders today?" }
  ]
}
```

**Response (`200 OK`)**:
```json
{
  "reply": "The status of order ORD-1025 is Delivered.\n\nOrder Details:\n- Customer: Karthik Rao\n- Product: Wireless Mouse (Quantity: 3)\n- Total Amount: ₹2,397\n- City: Kochi\n- Payment Method: Credit Card",
  "tool_calls": [
    {
      "name": "get_order",
      "arguments": { "order_id": "ORD-1025" },
      "ok": true,
      "summary": "Found order ORD-1025 for Karthik Rao (Wireless Mouse, total INR 2397, status: delivered)."
    }
  ]
}
```

### Error Responses
- **`422 Unprocessable Entity`**: Input validation failure (empty message, >1000 characters, invalid history role).
- **`429 Too Many Requests`**: Rate limit exceeded (>20 requests per minute).
- **`503 Service Unavailable`**: AI service unconfigured or temporarily busy (`{"error": "The AI service is busy right now. Please try again in a few seconds."}`).

---

## Data and Assumptions

- Dataset: 60 order rows stored in `data/orders.csv` spanning dates 2026-06-01 to 2026-09-28.
- Revenue & Spend Convention: By default, revenue and spend calculations **exclude orders with status `cancelled` (7 orders) or `returned` (3 orders)** as they represent uncompleted sales. The assistant explicitly states which statuses were counted in every reply.

---

## Deployment

The application is deployed as a single Web Service on **Render**:
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Health Check Path**: `/api/health`
- **Environment Variables**: Set in the Render Dashboard (`GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL`).

---

## Project Structure

```
.
├── app/
│   ├── main.py          # FastAPI application, routing, error handlers, static file mounting
│   ├── schemas.py       # Pydantic v2 schemas for requests, responses, and tool traces
│   ├── data.py          # CSV loading, normalization, city alias handling
│   ├── tools.py         # 4 tool implementations with parameters and revenue rules
│   ├── agent.py         # OrderAgent loop (max 5 iterations, tool trace collection)
│   ├── llm.py           # LLMProvider wrapper with backoff retries and fallback
│   └── guardrails.py    # Input validation, sliding-window rate limiter, off-topic filter
├── data/
│   └── orders.csv       # Order dataset (60 rows)
├── static/
│   ├── index.html       # Single-page chat UI
│   ├── styles.css       # Mobile-responsive CSS styling
│   └── app.js           # Frontend client, chat history, and collapsible tool steps UI
├── tests/
│   ├── test_tools.py    # Unit tests for tool logic and dataset queries
│   ├── test_api.py      # API validation, rate limiting, and mock agent tests
│   ├── test_frontend_mount.py  # Static file delivery tests
│   └── test_llm_resilience.py # Retry, fallback model, signature, and error tests
├── .env.example         # Template for local environment variables
├── .gitignore           # Git ignore rules
├── Makefile             # Run and test shortcuts
├── README.md            # Project documentation
├── WRITEUP.md           # Architecture and design write-up
├── render.yaml          # Render service deployment blueprint
├── requirements.txt     # Pinned Python dependencies
└── run.py               # Local launcher entry point
```

---

## Architecture Write-Up

See [WRITEUP.md](WRITEUP.md) for detailed architecture decisions, tool-calling loop design, guardrails, deployment, and future improvements.
