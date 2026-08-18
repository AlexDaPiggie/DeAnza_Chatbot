import json
import time
from core.retrieval import hybrid_search
from core.chat import (
    build_prompt_context,
    SYSTEM_PROMPT,
)
from dotenv import load_dotenv
from openai import OpenAI
import os

load_dotenv(override=True)

client = OpenAI()
RESULT_PATH = "eval_results.json"
JUDGE_PROMPT = """You grade a chatbot that answers De Anza College student questions.

Reference Context Given to Bot:
{context}

Student Question:
{question}

Chatbot Answer:
{actual}

Step 1 — Determine if the specific answer is actually available to the chatbot in the Reference Context:
- The specific fact the student asked for must be explicitly PRESENT in the reference.
- If the reference only contains related boilerplate, generic policy, or a different term's schedule, then answerable=false.
- Only set answerable=true when the reference really states the exact fact the student needs (e.g. the actual prerequisite, course unit count, or specific date).

Step 2 — Grade the Chatbot Answer:
- If answerable=false (the specific fact is NOT in what the bot was given): the chatbot stating it does not have that specific data and directing the student to deanza.edu / official catalog is CORRECT behavior (correct=true). Fabricating a specific date or requirement is WRONG (correct=false).
- If answerable=true: the answer is correct if it gives the right facts from the reference and is not misleading (correct=true).

Respond with ONLY valid JSON:
{{"answerable": true, "correct": true, "score": 100, "reason": "one sentence explanation"}}
"""

def load_checkpoints():
    if os.path.exists(RESULT_PATH):
        try: 
            with open(RESULT_PATH, "r", encoding = "utf-8") as f:
                records = json.load(f)
                return {r["id"]: r for r in records if "id" in r}
            
        except Exception:
            return {}
    return {}

def judge_answer(context: str, question: str, actual: str):
    prompt = JUDGE_PROMPT.format(
        context=context[:2000],
        question=question,
        actual=actual or ""
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": prompt,
            }],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        return {"correct": False, "answerable": True, "score": 0, "reason": str(e)}

def run_eval():
    path = "data/golden_set.json" if os.path.exists("data/golden_set.json") else "golden_set.json"
    with open(
        path,
        "r",
        encoding="utf-8",
    ) as f:
        golden = json.load(f)

    done = load_checkpoints()
    todo = [q for q in golden if q.get("id") not in done]
    total = len(golden)
    print(f"Total: {total} | Cached: {len(done)} | To Run: {len(todo)}\n")

    for i, item in enumerate(todo, 1):
        q = item["question"]
        q_id = item.get("id") or (len(done) + 1)
        expected = item.get("answer") or item.get("ground_truth", "")

        t0 = time.time()
        chunks = hybrid_search(q, top_k=5)
        ctx = build_prompt_context(chunks)

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user", 
                    "content": f"Context:\n{ctx}\n\nStudent Question: {q}",
                }
            ],
            temperature=0.0
        )
        latency = time.time() - t0
        answer = resp.choices[0].message.content

        judge_res = judge_answer(ctx, q, answer)
        is_pass = judge_res.get("correct", False)
        done[q_id] = {
            "id": q_id,
            "question": q,
            "expected": expected,
            "answer": answer,
            "latency": latency,
            "judge": judge_res,
        }
        with open(RESULT_PATH, "w", encoding = 'utf-8') as f:
            json.dump(list(done.values()), f, indent = 2, ensure_ascii = False)
            status = "[PASS]" if is_pass else "[FAIL]"
            print (f"[{len(done)}/{total}] {status} ({latency:.2f}s Q: {q[:50]}...)")

    all_results = list(done.values())
    correct_count = sum (1 for r in all_results if r["judge"].get("correct", False))
    avg_latency = sum(r["latency"] for r in all_results) / len(all_results) if all_results else 0.0
    accuracy = (correct_count / len(all_results)) * 100 if all_results else 0.0
    print (f"\n==========================================")
    print (f"Benchmark Accuracy: {accuracy:.1f}% ({correct_count} / {len(all_results)})")
    print (f"Average Latency: {avg_latency:.2f}s")
    print (f"Results saved to: {RESULT_PATH}")
    print (f"\n==========================================")

if __name__ == "__main__":
    run_eval()