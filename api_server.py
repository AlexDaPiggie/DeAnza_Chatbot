import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from core.schemas import ChatRequest, FeedbackRequest
from core.chat import stream_chat
from core.db import get_db

#Initialize the api
app = FastAPI(title="De Anza AI Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "https://de-anza-chatbot.vercel.app",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    with get_db() as conn: 
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    return {
        "status": "ok",
        "db": "connected",
    }

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    async def event_generator():
        async for token in stream_chat(
            req.message,
            [h.model_dump() for h in req.history]
        ):
            yield f"data: {json.dumps({'text': token})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )

@app.post("/api/feedback")
def submit_feedback(req: FeedbackRequest):
    with get_db() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback (query_text, answer_text, rating, model_used)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    req.query_text,
                    req.answer_text,
                    req.rating,
                    req.model_used,
                )
            )
    return {"status": "recorded"}

app.mount("/", StaticFiles(
    directory="public",
    html=True,
), name="public")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api_server:app", 
        host="127.0.0.1", 
        port=8000, 
        reload=True,
    )
