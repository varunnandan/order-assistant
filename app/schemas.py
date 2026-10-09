from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=2000)

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    history: Optional[List[ChatMessage]] = Field(default_factory=list)

class ToolCallInfo(BaseModel):
    name: str
    arguments: Dict[str, Any]
    ok: bool
    summary: str

class ChatResponse(BaseModel):
    reply: str
    tool_calls: List[ToolCallInfo] = Field(default_factory=list)

class HealthResponse(BaseModel):
    status: str = "ok"
    orders_loaded: int

class ErrorResponse(BaseModel):
    error: str
