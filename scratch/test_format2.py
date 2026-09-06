import os
import asyncio
from openai import AsyncOpenAI
import dotenv
from core.chat import SYSTEM_PROMPT

dotenv.load_dotenv()

context = """[Document 1] (Source: https://deanza.edu/cis22a):
CIS 22A Beginning Programming Methodologies in C++. Units: 4.5. Prerequisites: None. Advisory: EWRT 1A."""

question = "What are the prerequisites for CIS 22A?"

async def test_model(model_name):
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY")
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
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"Error: {e}")

async def main():
    await test_model("microsoft/phi-4")
    await test_model("google/gemini-2.5-flash-lite")

asyncio.run(main())
