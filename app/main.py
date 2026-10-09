import os
import logging
from typing import Dict, Any
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import ChatRequest, ChatResponse, HealthResponse, ErrorResponse, ToolCallInfo
from app.data import dataset
from app.guardrails import validate_chat_input, rate_limiter
from app.agent import OrderAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("order_assistant.main")

app = FastAPI(
    title="Order Assistant API",
    description="Natural language order lookup and metrics assistant powered by AI tools.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = OrderAgent()

from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    if errors:
        first_err = errors[0]
        msg = first_err.get("msg", "Invalid request parameters.")
        field = first_err.get("loc", [])[-1] if first_err.get("loc") else "field"
        clean_msg = f"Invalid input for {field}: {msg}"
    else:
        clean_msg = "Invalid request format."
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": clean_msg}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        error_msg = detail["error"]
    elif isinstance(detail, str):
        error_msg = detail
    else:
        error_msg = str(detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error_msg}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "An unexpected error occurred on the server. Please try again later."}
    )

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok", orders_loaded=len(dataset.orders))

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: Request, body: ChatRequest):
    # Rate limit check per IP
    client_ip = request.client.host if request.client else "127.0.0.1"
    if rate_limiter.is_rate_limited(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. You may make up to 20 requests per minute."
        )

    # Input validation
    clean_msg, clean_history = validate_chat_input(body.message, body.history or [])

    try:
        reply_text, tool_calls_raw = agent.run(clean_msg, clean_history)
        
        tool_calls = [
            ToolCallInfo(
                name=tc["name"],
                arguments=tc["arguments"],
                ok=tc["ok"],
                summary=tc["summary"]
            )
            for tc in tool_calls_raw
        ]
        return ChatResponse(reply=reply_text, tool_calls=tool_calls)
    except RuntimeError as rerr:
        logger.error(f"LLM Runtime error: {rerr}")
        err_str = str(rerr)
        if "quota" in err_str.lower() or "429" in err_str:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="The AI service rate limit or quota has been reached. Please wait a moment and try again."
            )
        elif "api_key" in err_str.lower() or "not set" in err_str.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service is not configured properly (missing API key). Please configure GEMINI_API_KEY."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to communicate with AI model service. Please try again."
            )
    except Exception as exc:
        logger.error(f"Chat processing failure: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your question."
        )

# Mount static files and fallback index page
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"message": "Order Assistant API is running. Static UI files not found."})
