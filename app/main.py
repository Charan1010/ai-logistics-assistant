"""
AI Logistics Assistant - Feature 1: Basic Chat
A stateless AI chatbot with logistics domain expertise.
"""
import httpx
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.models import ChatRequest, ChatResponse
from app.llm_client import llm_client
from app.config import settings

app = FastAPI(
    title=settings.app_name,
    description="Intelligent AI assistant for logistics and supply chain operations",
    version="0.1.0"
)

# CORS middleware for web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get UI directory path
UI_DIR = Path(__file__).parent.parent / "ui"

# Mount static files if UI directory exists
if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")


# System prompt for logistics domain
SYSTEM_PROMPT = """You are an expert AI assistant for logistics and supply chain operations.

Your expertise includes:
- Supply chain optimization and efficiency metrics
- Transportation and fleet management
- Warehouse operations and inventory control
- Last-mile delivery strategies
- International shipping and customs
- Real-time tracking and visibility
- Risk management and disruption handling

Respond in a professional, executive-level tone. Provide actionable insights with specific recommendations when possible. If you don't know something, be honest and suggest where the user might find that information.

Keep responses concise but comprehensive."""


@app.get("/")
async def root():
    """Serve the web UI."""
    ui_file = UI_DIR / "index.html"
    if ui_file.exists():
        return FileResponse(ui_file)
    return {
        "status": "online",
        "app": settings.app_name,
        "version": "0.1.0",
        "features": ["basic_chat"],
        "model": llm_client.model
    }


@app.get("/api/status")
async def status():
    """API status endpoint."""
    return {
        "status": "online",
        "app": settings.app_name,
        "version": "0.1.0",
        "features": ["basic_chat"],
        "model": llm_client.model
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Basic chat endpoint - stateless conversation.
    
    Each request is independent with no memory of previous interactions.
    """
    try:
        # Build messages with system prompt
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": request.message}
        ]
        
        # Get LLM response
        response_text = await llm_client.chat(messages)
        
        return ChatResponse(
            response=response_text,
            model=llm_client.model
        )
    
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503,
            detail=f"LLM service unavailable: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
