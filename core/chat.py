import os
from typing import AsyncGenerator, List
from openai import AsyncOpenAI
from dotenv import load_dotenv
from core.retrieval import hybrid_search

load_dotenv()

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
CHAT_MODEL=os.getenv("CHAT_MODEL", "gpt-4o-mini")
SYSTEM_PROMPT = """You are the official De Anza College AI Assistant.

RULES:
1. GREETINGS & CASUAL CHAT: If the student sends a greeting or pleasantry (e.g. "hi", "hello", "helu", "hey", "how are you"), reply warmly, naturally, and concisely in 1-2 friendly sentences (e.g., "Hello! How can I help you today with your De Anza courses, schedules, or campus policies?"). Avoid robotic or overly long canned introductions.
2. Answer factual questions based ONLY on the provided context below.
3. If prerequisites are listed as "None" for a course, clearly state that no prior experience, courses, or auditions are required.
4. If schedule sections are provided in context, confirm whether the course is offered and list the relevant CRN, days, times, and instructor.
5. If the context does NOT contain the answer to a factual question, politely state: "I don't have that official information in my training data" and direct them to deanza.edu. Do NOT fabricate information.
6. FORMATTING REQUIREMENTS:
    - Always insert TWO blank lines before every ### header and before bullet lists.
    - Use clear markdown with short paragraphs (2-3 sentences max).
    - Use bullet points (*) on separate lines for requirements, prerequisites, steps, fees, or dates.
    - Use bold text for key terms, course codes, deadlines, and requirements.
    - Separate distinct topics with ### headers.
7. CITATIONS: Always leave TWO blank lines and end with a separate "### Sources" header. Format each source as a clean clickable bullet markdown link on its own line: `* [Source Title](URL)`. Never attach ### to preceding text.

Example response:
### CIS 22A - Beginning Programming Methodologies in C++
* **Units**: 4.5
* **Department**: Computer Information Systems

### Prerequisites
* **Prerequisites**: None (No prior programming experience required).
* **Advisory**: EWRT 1A or ESL 5, and MATH 114


### Sources
* [CIS 22A Catalog](https://deanza.elumenapp.com/catalog/course/CIS%2022A)
"""

def build_prompt_context(chunks: list) -> str:
    parts = []
    for idx, c in enumerate(chunks, 1):
        url = c.url or "https://deanza.edu"
        parts.append(f"[Document {idx}] (Source: {url}):\n{c.text}")
    return "\n\n---\n\n".join(parts)

# Function to create the streaming chat effect
async def stream_chat(message: str, history: List[dict] = None) -> AsyncGenerator[str, None]:
    chunks = hybrid_search(message, top_k=5)
    context_text = build_prompt_context(chunks)

    messages = [{
        "role": "system",
        "content": SYSTEM_PROMPT,
    }]
    if history:
        for h in history[-4:]:
            messages.append({
                "role": h["role"],
                "content": h["content"],
            })

    messages.append({
        "role": "user",
        "content": f"Context:\n{context_text}\n\nStudent Question: {message}"
    })

    response = await client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=0.0,
        stream=True,
    )

    async for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta

