import os
from typing import AsyncGenerator, List
from openai import AsyncOpenAI, OpenAI
from dotenv import load_dotenv
from core.retrieval import hybrid_search

load_dotenv()

#Load the list of models from .env
chat_env = os.getenv("CHAT_MODEL")
condenser_env = os.getenv("CONDENSER_MODEL")

CHAT_MODELS = [m.strip() for m in chat_env.split(",")]
CONDENSER_MODELS = [m.strip() for m in condenser_env.split(",")]

#Check available and load the primary models
async_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)
SYSTEM_PROMPT = """You are the official De Anza College AI Assistant.

RULES:
1. GREETINGS & CASUAL CHAT: If the student sends a greeting or pleasantry (e.g. "hi", "hello", "helu", "hey", "how are you"), reply warmly, naturally, and concisely in 1-2 friendly sentences (e.g., "Hello! How can I help you today with your De Anza courses, schedules, or campus policies?"). Avoid robotic or overly long canned introductions.
2. Answer factual questions based ONLY on the provided context below.
3. If prerequisites are listed as "None" for a course, clearly state that no prior experience, courses, or auditions are required.
4. If schedule sections are provided in context, confirm whether the course is offered and list the relevant CRN, days, times, and instructor.
5. MISSING OR LIVE SCHEDULE DATA: If specific instructor names, live section availability, or current quarterly schedules are not found in the context:
    - State clearly that live quarterly section details for that course are not in the database.
    - Provide the direct official links immediately on the first attempt:
      * [De Anza Schedule of Classes](https://www.deanza.edu/schedule/) (for live instructors, days, times, and open seats).
      * [De Anza Course Catalog](https://www.deanza.edu/catalog/) (for course outlines and prerequisites).
    - Do NOT fabricate names or dates.
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
async def stream_chat(
    message: str, 
    history: List[dict] = None
) -> AsyncGenerator[str, None]:

    # Rewrite the query if follow-up context is present
    search_query = condense_query_with_history(message, history)

    # Search database using rewritten query
    chunks = hybrid_search(search_query, top_k=5)
    context_text = build_prompt_context(chunks)

    # Assemble prompt with system prompt, recent history, and current turn
    messages = [{
        "role": "system",
        "content": SYSTEM_PROMPT,
    }]
    if history:
        for h in history[-6:]:
            messages.append({
                "role": h.get("role", "user"),
                "content": h.get("content", ""),
            })

    # Add the current user message with retrieved context
    user_prompt = f"""Context from official De Anza sources: {context_text}
    
    Student Question: {message}"""


    messages.append({
        "role": "user",
        "content": user_prompt,
    })

    for model_name in CHAT_MODELS:
        try: 
            response = await async_client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.3,
                stream=True,
            )
            async for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
            break

        except Exception as e:
            print(f"The primary chat model {model_name} is not available. Error: {e}")
            print(f"Switching to fallback model...")
            continue


client = OpenAI(
    base_url = "https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

CONDENSE_PROMPT = """Given the chat history follow-up question, rewrite the follow-up question into a standalone question that contains all necessary context(course codes, program names, policies) for a search engine

Chat History: 
{history_text}

Follow-up Question: {question}

Standalone Search Query:"""

def condense_query_with_history (
    message: str,
    history: List[dict] = None
): 
    #If no history exists, the message is already standalone
    if not history or len (history) == 0:
        return message

    #Format the last 4 messages (2 turns) for context
    history_lines = []
    for h in history[-4:]:
        role = "Student" if h.get("role") == "user" else "Assistant"
        content = h.get("content", "")

        #Truncate assistant response to 200 chars to save tokens & latency
        if role == "Assistant" and len(content) > 200:
            content = content[:200] + "..."
        history_lines.append(f"{role}: {content}")

    history_text = "\n".join (history_lines)

    #in case all condenser models are unavailable, we assign condensed text to be user's message
    condense_text = message
    for model_name in CONDENSER_MODELS:
        try: 
            response = client.chat.completions.create(
                model = model_name,
                messages = [{
                    "role": "user",
                    "content": CONDENSE_PROMPT.format(
                        history_text = history_text, 
                        question = message,
                    )
                }],
                max_tokens = 60,
                temperature=0.1,
            )
            condense_text = response.choices[0].message.content
            break
        
        except Exception as e:
            print(f"Condenser model {model_name} is currently not available. Error: {e}")
            print("Switching to the next model...")

    return condense_text