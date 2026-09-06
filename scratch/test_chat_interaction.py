"""
End-to-End Chat Interaction Test Runner
Tests:
  1. Factual retrieval + streaming.
  2. History condensation on follow-up turn.
  3. Live schedule fallback link behavior.
  4. Inspection of output/retrieval_data.md and output/model_output.md.
"""

import asyncio
import os
import time
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv(override=True)
os.environ["DEBUG_LOGS"] = "true"

from core.chat import stream_chat


async def run_test_turn(label: str, message: str, history: Optional[List[dict]] = None) -> dict:
    print(f"\n{'=' * 60}")
    print(f"RUNNING : {label}")
    print(f"PROMPT  : {message}")
    print(f"{'=' * 60}\nSTREAMED RESPONSE:\n")

    start_time = time.perf_counter()
    chunks: List[str] = []

    async for token in stream_chat(message=message, history=history):
        print(token, end="", flush=True)
        chunks.append(token)

    elapsed = round(time.perf_counter() - start_time, 2)
    full_text = "".join(chunks)

    print(f"\n\n[DONE in {elapsed}s | Length: {len(full_text)} chars]")
    return {
        "label": label,
        "message": message,
        "full_text": full_text,
        "latency_sec": elapsed,
    }


def inspect_debug_logs() -> dict:
    retrieval_path = os.path.join("output", "retrieval_data.md")
    model_path = os.path.join("output", "model_output.md")

    retrieval_exists = os.path.exists(retrieval_path)
    model_exists = os.path.exists(model_path)

    print(f"\n--- LOG AUDIT ---")
    print(f"File output/retrieval_data.md : {'FOUND' if retrieval_exists else 'MISSING'}")
    print(f"File output/model_output.md    : {'FOUND' if model_exists else 'MISSING'}")

    model_used = "UNKNOWN"
    has_sources = False

    if model_exists:
        try:
            with open(model_path, "r", encoding="utf-8") as f:
                content = f.read()

            if "## 1. Model Used" in content:
                part = content.split("## 1. Model Used")[1]
                model_used = part.split("## 2.")[0].strip()

            if "* [" in content and "](http" in content:
                has_sources = True

            print(f"Active Model Logged           : {model_used}")
            print(f"Formatted Markdown Link Found : {has_sources}")
        except Exception as e:
            print(f"Error reading model_output.md : {e}")

    return {
        "retrieval_exists": retrieval_exists,
        "model_output_exists": model_exists,
        "model_used": model_used,
        "has_sources": has_sources,
    }


async def main():
    print("=" * 60)
    print("STARTING CHATBOT INTERACTION TEST SUITE")
    print(f"Working Directory: {os.getcwd()}")
    print("=" * 60)

    # 1. Single-turn factual query
    s1 = await run_test_turn(
        label="Scenario 1: Factual Course Query",
        message="What are the prerequisites and units for CIS 22A?",
        history=None,
    )
    inspect_debug_logs()

    # 2. Multi-turn follow-up turn (requires condensing "it")
    s1_history = [
        {"role": "user", "content": "What are the prerequisites and units for CIS 22A?"},
        {"role": "assistant", "content": s1["full_text"][:250]},
    ]
    s2 = await run_test_turn(
        label="Scenario 2: Multi-turn Follow-up (Condenser Test)",
        message="Is it offered online this quarter and who teaches it?",
        history=s1_history,
    )
    inspect_debug_logs()

    # 3. Missing live data query (checks mandatory link output)
    s3 = await run_test_turn(
        label="Scenario 3: Missing Live Data (Link Fallback Test)",
        message="Give me the CRN and open seats for John Doe's MATH 1A class.",
        history=None,
    )
    inspect_debug_logs()

    print("\n" + "=" * 60)
    print("TEST SUITE EXECUTION COMPLETE")
    print(f"  S1: {s1['latency_sec']}s | {len(s1['full_text'])} chars")
    print(f"  S2: {s2['latency_sec']}s | {len(s2['full_text'])} chars")
    print(f"  S3: {s3['latency_sec']}s | {len(s3['full_text'])} chars")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
