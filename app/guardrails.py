import time
import re
from typing import Dict, List, Tuple
from fastapi import Request, HTTPException, status
from app.schemas import ChatMessage

OFFTOPIC_PATTERNS = [
    r"ignore (all )?(previous )?instructions",
    r"system prompt",
    r"api[ _]?key",
    r"write (a )?code",
    r"tell me a story",
    r"recipe for",
    r"who is the president",
    r"what is the capital of"
]

class RateLimiter:
    """In-memory sliding window rate limiter per IP."""
    def __init__(self, requests_per_minute: int = 20):
        self.rate_limit = requests_per_minute
        self.ip_history: Dict[str, List[float]] = {}

    def is_rate_limited(self, ip: str) -> bool:
        now = time.time()
        window_start = now - 60.0
        
        # Clean up old timestamps
        history = [ts for ts in self.ip_history.get(ip, []) if ts > window_start]
        self.ip_history[ip] = history

        if len(history) >= self.rate_limit:
            return True
        
        history.append(now)
        return False

rate_limiter = RateLimiter(requests_per_minute=20)

def validate_chat_input(message: str, history: List[ChatMessage]) -> Tuple[str, List[ChatMessage]]:
    """Validate and sanitize chat request message and history."""
    trimmed_msg = message.strip()
    if not trimmed_msg:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "Message cannot be empty or whitespace only."}
        )
    if len(trimmed_msg) > 1000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "Message exceeds maximum length of 1000 characters."}
        )

    # Validate and cap history to last 10 turns
    sanitized_history = []
    if history:
        for msg in history:
            if msg.role not in ["user", "assistant"]:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"error": f"Invalid history role '{msg.role}'. Must be 'user' or 'assistant'."}
                )
            sanitized_history.append(msg)

    # Keep last 10 turns (20 messages max)
    truncated_history = sanitized_history[-20:]
    return trimmed_msg, truncated_history

def check_offtopic_or_injection(message: str) -> bool:
    """Detect if message is trying prompt injection or asking off-topic non-order questions."""
    msg_low = message.lower()
    for pattern in OFFTOPIC_PATTERNS:
        if re.search(pattern, msg_low):
            return True
    return False
