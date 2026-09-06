import os
import asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """You are the official De Anza College AI Assistant.

RULES:
1. GREETINGS & CASUAL CHAT: If the student sends a greeting or pleasantry, reply warmly.
2. Answer factual questions based ONLY on the provided context below.
3. If prerequisites are listed as "None" for a course, clearly state that no prior experience, courses, or auditions are required.
4. If schedule sections are provided in context, confirm whether the course is offered and list the relevant CRN, days, times, and instructor.
5. MISSING OR LIVE SCHEDULE DATA: Provide the direct official links immediately.
6. FORMATTING REQUIREMENTS:
    - Always insert TWO blank lines before every ### header and before bullet lists.
    - Use clear markdown with short paragraphs (2-3 sentences max).
    - Use bullet points (*) on separate lines for requirements, prerequisites, steps, fees, or dates.
    - Use bold text for key terms, course codes, deadlines, and requirements.
    - Separate distinct topics with ### headers.
7. CITATIONS: Always leave TWO blank lines and end with a separate "### Sources" header. Format each source as a clean clickable bullet markdown link on its own line: `* [Source Title](URL)`. Never attach ### to preceding text.
"""

context = """[Document 1] (Source: https://deanza.edu/cis22a):
CIS 22A Beginning Programming Methodologies in C++. Units: 4.5. Prerequisites: None. Advisory: EWRT 1A."""

question = "What are the prerequisites for CIS 22A?"

async def test_model(model_name):
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY")
    )
    user_prompt = f"Context from official De Anza sources: {context}\n\nStudent Question: {question}"
    
    print(f"\n{'='*40}\nTesting Model: {model_name}\n{'='*40}")
    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
        )
        print(repr(response.choices[0].message.content))
    except Exception as e:
        print(f"Error: {e}")

async def main():
    await test_model("openai/gpt-4o-mini")
    await test_model("microsoft/phi-4")
    await test_model("google/gemini-2.5-flash-lite")
    await test_model("meta-llama/llama-3.3-70b-instruct")

asyncio.run(main())
