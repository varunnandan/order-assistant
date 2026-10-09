# 📦 Order Assistant - E-Commerce AI Web App

An end-to-end, production-grade AI-powered **Order Assistant** chat web application built for an e-commerce platform screening task. Users ask natural-language questions about customer orders, sales metrics, and inventory, and the AI agent retrieves facts by calling structured python tools over `orders.csv`.

**Live Demo**: `<PASTE_LIVE_URL_HERE>` *(Note: Render free tier services may experience a ~30–60 second cold start on the initial request)*.

---

## 🛠️ Tech Stack

- **Backend Framework**: Python 3.11+, FastAPI, Pydantic v2, Uvicorn
- **AI / LLM Integration**: Official Google Gemini SDK (`google-genai`), native function calling (`gemini-2.5-flash`)
- **Dataset / Data Layer**: In-memory Python standard library CSV parsing (`data/orders.csv`)
- **Frontend**: Lightweight vanilla HTML5, CSS3, and JavaScript (served directly by FastAPI)
- **Testing**: `pytest` + FastAPI `TestClient` (100% offline runnable tests with mock LLM)
- **Deployment**: Render Free Web Service (`render.yaml`)

---

## 🚀 Quick Local Setup (2 Commands)

### 1. Clone & Install Dependencies
```bash
pip install -r requirements.txt && cp .env.example .env
```

### 2. Configure Environment Variables & Run
Add your free Google Gemini API key to `.env` (Get a free key from [Google AI Studio](https://aistudio.google.com/)):
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

Then start the server:
```bash
uvicorn app.main:app --reload
```
*Or using Python directly: `python run.py`, or `make run`.*

Open `http://localhost:8000` in your web browser to interact with the Chat UI.

---

## 🧪 Running Tests

All unit, integration, and guardrail tests run completely **offline** without requiring a live Gemini API key:

```bash
pytest -q
```

---

## 📊 Dataset & Revenue Convention

The dataset consists of 60 verified order records spanning **2026-06-01 to 2026-09-28**.

> **Revenue Convention**: By default, **revenue and spend calculations EXCLUDE orders with status `cancelled` (7 orders) or `returned` (3 orders)** because they were not completed sales. The tools support an optional `include_statuses` parameter, and the assistant explicitly states which statuses were included in every response.

---

## 💬 Example Questions to Try

1. **Order Lookup**: *"What is the status of order ORD-1025?"*
2. **Status Count**: *"How many orders were cancelled?"*
3. **Revenue Metric**: *"What was the total revenue from Electronics in August?"*
4. **Top Customer**: *"Which customer has spent the most?"*

---

## 🔌 API Reference

### `GET /api/health`
Health check endpoint returning dataset status.
```json
{
  "status": "ok",
  "orders_loaded": 60
}
```

### `POST /api/chat`
Sends a natural language query with conversation history.

**Request Body**:
```json
{
  "message": "What is the status of order ORD-1025?",
  "history": [
    { "role": "user", "content": "Hi" },
    { "role": "assistant", "content": "Hello! How can I help you with orders today?" }
  ]
}
```

**Response**:
```json
{
  "reply": "Order ORD-1025 was placed by Karthik Rao in Kochi for a Wireless Mouse (3 units, Total: ₹2,397). Its current status is delivered.",
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

---

## 📁 Project Structure

```
.
├── app/
│   ├── main.py          # FastAPI app, routes, error handlers, static file mounting
│   ├── schemas.py       # Pydantic v2 request/response models
│   ├── data.py          # CSV loader, city aliases, and dataset helpers
│   ├── tools.py         # 4 tool implementations with schemas & validation
│   ├── agent.py         # OrderAgent loop (tool calling, iteration control, traces)
│   ├── llm.py           # Isolated Google Gemini LLM provider wrapper
│   └── guardrails.py    # Input validation, rate limiting, and off-topic guard
├── data/
│   └── orders.csv       # Standard order dataset (60 rows)
├── static/
│   ├── index.html       # Single-page chat UI
│   ├── styles.css       # Clean, mobile-responsive styling
│   └── app.js           # Frontend interactivity & tool steps UI
├── tests/
│   ├── test_tools.py    # Dataset & tools unit tests
│   ├── test_api.py      # API validation, rate limiting & mock agent tests
│   └── test_frontend_mount.py # Static file delivery tests
├── .env.example         # Template for environment variables
├── .gitignore            # Git exclusion rules (includes .env)
├── render.yaml          # Render web service deployment spec
├── requirements.txt     # Python dependencies
├── Makefile             # Convenience Makefile
├── run.py               # Server entry point
├── WRITEUP.md           # Architecture & design write-up
└── README.md            # Project documentation
```
