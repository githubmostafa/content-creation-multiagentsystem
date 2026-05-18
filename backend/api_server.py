"""FastAPI server to expose the content creation agent via Gemini Enterprise Agent Runtime."""

import os
import asyncio
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import json
from pathlib import Path

load_dotenv()

from vertexai import agent_engines

AGENT_RESOURCE_NAME = os.environ.get("AGENT_RESOURCE_NAME") or os.environ.get("AGENT_ENGINE_RESOURCE_NAME")
AGENT_NAME = "orchestrator_agent"

CHANNEL_MAP = {
    "blog_post_writer_agent": "blog_post",
    "social_media_creator_agent": "social_media",
    "email_newsletter_writer_agent": "email_newsletter",
    "seo_metadata_agent": "seo_metadata",
}

remote_agent = None
if AGENT_RESOURCE_NAME:
    try:
        remote_agent = agent_engines.get(AGENT_RESOURCE_NAME)
    except Exception as e:
        print(f"Warning: Failed to connect to Agent Runtime: {e}")

app = FastAPI(title="Content Creation Studio API")

allowed_origins = ["http://localhost:3000", "http://localhost:5173"]
if os.environ.get("FRONTEND_URL"):
    allowed_origins.append(os.environ.get("FRONTEND_URL"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")


# =========================
# MODELS
# =========================

class ContentRequest(BaseModel):
    topic: str
    target_audience: str
    tone: str
    keywords: str
    session_id: Optional[str] = None


class AnalyzeRequest(BaseModel):
    text: str


class ChatRequest(BaseModel):
    message: str


# =========================
# HEALTH
# =========================

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "message": "Content Creation Studio API is running",
        "agent": AGENT_NAME,
        "agent_resource": AGENT_RESOURCE_NAME if AGENT_RESOURCE_NAME else "Not configured",
        "agent_connected": remote_agent is not None
    }


# =========================
# CHAT (CHATGPT STREAMING)
# =========================

@app.post("/api/chat")
async def chat(request: ChatRequest):

    if not remote_agent:
        raise HTTPException(status_code=503, detail="Agent not configured")

    user_id = "web_user_001"
    session = await remote_agent.async_create_session(user_id=user_id)

    async def generate():
        try:
            async for event in remote_agent.async_stream_query(
                user_id=user_id,
                session_id=session["id"],
                message=request.message
            ):

                if not isinstance(event, dict):
                    continue

                text = ""

                if "text" in event:
                    text += event["text"]

                content = event.get("content", {})
                if isinstance(content, dict):
                    for part in content.get("parts", []):
                        if part.get("text"):
                            text += part["text"]

                if text:
                    yield f"data: {json.dumps({'type': 'chunk', 'content': text})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


# =========================
# FRONTEND
# =========================

@app.get("/")
async def serve_frontend():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "status": "ok",
        "mode": "development",
        "agent_connected": remote_agent is not None
    }


# =========================
# CREATE CONTENT
# =========================

@app.post("/api/create-content")
async def create_content(request: ContentRequest):

    if not remote_agent:
        raise HTTPException(status_code=503, detail="Agent not configured")

    user_id = "web_user_001"
    session = await remote_agent.async_create_session(user_id=user_id)

    query = f"""
Create content:
Topic: {request.topic}
Audience: {request.target_audience}
Tone: {request.tone}
Keywords: {request.keywords}
"""

    async def generate():
        async for event in remote_agent.async_stream_query(
            user_id=user_id,
            session_id=session["id"],
            message=query
        ):

            if not isinstance(event, dict):
                continue

            author = event.get("author", "")
            channel = CHANNEL_MAP.get(author)

            text = ""

            if "text" in event:
                text += event["text"]

            content = event.get("content", {})
            if isinstance(content, dict):
                for part in content.get("parts", []):
                    if part.get("text"):
                        text += part["text"]

            if channel and text:
                yield f"data: {json.dumps({'type': 'content_piece', 'channel': channel, 'content': text})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# =========================
# ANALYZE TEXT
# =========================

@app.post("/api/analyze-text")
async def analyze_text(request: AnalyzeRequest):

    if not remote_agent:
        raise HTTPException(status_code=503, detail="Agent not configured")

    user_id = "web_user_001"
    session = await remote_agent.async_create_session(user_id=user_id)

    response_text = ""

    async for event in remote_agent.async_stream_query(
        user_id=user_id,
        session_id=session["id"],
        message=f"Analyze: {request.text}"
    ):

        if isinstance(event, dict) and "text" in event:
            response_text += event["text"]

    return {
        "status": "success",
        "analysis": response_text
    }


# =========================
# RUN SERVER
# =========================

if __name__ == "__main__":
    import uvicorn

    if AGENT_RESOURCE_NAME:
        print(f"Connected: {AGENT_RESOURCE_NAME}")
    else:
        print("WARNING: No agent configured")

    uvicorn.run(app, host="0.0.0.0", port=8000)