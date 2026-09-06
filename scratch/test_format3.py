import os
import asyncio
from openai import AsyncOpenAI
import dotenv
from core.chat import SYSTEM_PROMPT

dotenv.load_dotenv()

context = """[Document 1] (Source: https://deanza.edu/calendar):
Fall Quarter 2024 Deadlines: The last day to drop classes without a W is October 6th. The final exam week is December 9-13.
[Document 2] (Source: https://deanza.edu/fees):
Tuition fees for international students are $234 per unit."""

question = "What is the deadline to drop a class without a W, and how much is international tuition?"

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
