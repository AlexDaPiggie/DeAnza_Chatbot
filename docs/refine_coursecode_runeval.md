# Sub-Plan: Refine Course Codes & Evaluation Runner

This sub-plan guides the step-by-step upgrade of Course Code Normalization (`core/course_codes.py`), Retrieval Integration (`core/retrieval.py`), and the 2-Step Evaluation Runner (`run_eval.py`).

---

## 1. Section 1: Course Code Alias Indexer (`core/course_codes.py`)

### 1. Purpose
* Build an in-memory index from `catalog_courses_full.json`.
* Automatically map student abbreviations (`"cis 22a"`, `"math 1b"`, `"ewrt 1a"`) to official catalog codes (`"CIS D022A"`, `"MATH D001B"`).
* Guarantee instant canonical code resolution without manual regex lists.

### 2. Inputs & Outputs
* **`resolve_code(query: str) -> Optional[str]`**
  * **Input:** Student query string (e.g. `"What is the prerequisite for cis 22a?"`).
  * **Output:** Canonical catalog code string (e.g. `"CIS D022A"`), or `None` if no course mentioned.

### 3. Developer Code Draft
```python
"""Course code normalization: map student-style codes to catalog codes."""
import json
import os
import re
from typing import Optional, List, Dict

DATA_PATH = "catalog_courses_full.json"

# Manual overrides for well-known renames and edge cases
ALIAS_OVERRIDES = {
    "ewrt1a": "EWRT D001A",
    "math1a": "MATH D001A",
    "math1b": "MATH D001B",
    "cis22a": "CIS D022A",
    "cis22b": "CIS D022B",
    "cis22c": "CIS D022C",
}


class CourseIndex:
    """In-memory alias index for De Anza catalog courses."""

    def __init__(self, path: str = DATA_PATH):
        self.by_code: Dict[str, dict] = {}
        self.by_alias: Dict[str, str] = {}
        
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                courses = json.load(f)
            
            for c in courses:
                if not isinstance(c, dict) or "error" in c:
                    continue
                code = (c.get("code") or c.get("Course ID (CB01A and CB01B)") or "").strip()
                if not code:
                    continue
                
                self.by_code[code] = c
                for alias in self._generate_aliases(code):
                    self.by_alias[alias] = code

    @staticmethod
    def _generate_aliases(code: str) -> List[str]:
        """Generate common user variations for a catalog code like 'CIS D022A'."""
        aliases = []
        compact = re.sub(r"\s+", "", code).lower()
        aliases.append(compact)  # 'cisd022a'

        # Convert 'CIS D022A' -> 'CIS 22A' (remove 'D' and leading zeros)
        m = re.match(r"^\s*([A-Za-z]+)\s*D0*(\d+[A-Za-z]?)\s*$", code)
        if m:
            prefix, num = m.group(1).lower(), m.group(2).lower()
            aliases.append(f"{prefix}{num}")         # 'cis22a'
            aliases.append(f"{prefix} {num}")        # 'cis 22a'
            aliases.append(f"{prefix}-{num}")       # 'cis-22a'
        
        return aliases

    def normalize(self, text: str) -> Optional[str]:
        """Lookup canonical code for a given course token."""
        clean = re.sub(r"[\s\-_]+", "", text).lower()
        if clean in ALIAS_OVERRIDES:
            return ALIAS_OVERRIDES[clean]
        return self.by_alias.get(clean)

    def find_in_text(self, text: str) -> Optional[str]:
        """Extract course code mention from natural language user query."""
        # Check standard course pattern (e.g. CIS 22A, MATH-1A, PHYS4A)
        tokens = re.findall(r"\b([A-Za-z]{2,5}[\s\-_]?D?0*\d{1,4}[A-Za-z]?)\b", text)
        for token in tokens:
            resolved = self.normalize(token)
            if resolved:
                return resolved
        return None


_INDEX = None


def get_index() -> CourseIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = CourseIndex()
    return _INDEX


def resolve_code(query: str) -> Optional[str]:
    """Public helper: returns canonical code if query mentions a course, else None."""
    return get_index().find_in_text(query)
```

### 4. Verification
```powershell
python -c "from core.course_codes import resolve_code; print('CIS 22A ->', resolve_code('what is prereq for cis22a?')); print('MATH 1A ->', resolve_code('can I take math-1a?'))"
```
* **Expected Output:**
  `CIS 22A -> CIS D022A`
  `MATH 1A -> MATH D001A`

---

## 2. Section 2: Retrieval Exact Match Hookup (`core/retrieval.py`)

### 1. Purpose
* Connect canonical course codes directly to `exact_course_lookup`.
* Pin authoritative course chunks to the **#1 spot** in search results.
* Ensure bug-free RRF fusion and list-based sparse search.

### 2. Inputs & Outputs
* **`hybrid_search(query: str, top_k: int = 5) -> List[SearchResult]`**
  * **Input:** Natural language student query.
  * **Output:** Top-ranked list of `SearchResult` objects.

### 3. Developer Code Draft
```python
"""Hybrid RRF retrieval engine with exact course code pinning."""
from typing import Dict, List, Optional
from core.db import get_db
from core.embed import embed_text
from core.course_codes import resolve_code
from core.schemas import SearchResult


def _rrf_fuse(dense: List[dict], sparse: List[dict], k: int = 60) -> List[dict]:
    """Merge dense and sparse rankings using Reciprocal Rank Fusion."""
    scores: Dict[int, float] = {}
    docs: Dict[int, dict] = {}

    for ranked_list in (dense, sparse):
        for rank, item in enumerate(ranked_list):
            doc_id = item["id"]
            docs[doc_id] = item
            scores[doc_id] = scores.get(doc_id, 0.0) + (1.0 / (k + rank + 1))

    sorted_ids = sorted(scores.keys(), key=lambda did: scores[did], reverse=True)
    out = []
    for did in sorted_ids:
        row = docs[did]
        row["score"] = scores[did]
        out.append(row)
    return out


def exact_course_lookup(code: str) -> Optional[dict]:
    """Fetch authoritative chunk for a canonical course code (e.g. 'CIS D022A')."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, chunk_text, metadata, source_url
                FROM chunks
                WHERE source_type = 'course' AND (
                    metadata->>'code' = %s OR
                    doc_id = %s
                )
                ORDER BY id LIMIT 1
                """,
                (code, code.lower().replace(" ", "-"))
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "text": row["chunk_text"],
                    "meta": row["metadata"],
                    "url": row["source_url"],
                    "score": 1.0
                }
    return None


def dense_search(query_vec: List[float], limit: int = 30) -> List[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, chunk_text, metadata, source_url,
                       1 - (embedding <=> %s::vector) AS sim
                FROM chunks
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_vec, query_vec, limit)
            )
            return [
                {"id": r["id"], "text": r["chunk_text"], "meta": r["metadata"], "url": r["source_url"]}
                for r in cur.fetchall()
            ]


def sparse_search(query: str, limit: int = 30) -> List[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, chunk_text, metadata, source_url
                FROM chunks
                WHERE tsv @@ plainto_tsquery('english', %s)
                ORDER BY ts_rank_cd(tsv, plainto_tsquery('english', %s)) DESC
                LIMIT %s
                """,
                (query, query, limit)
            )
            return [
                {"id": r["id"], "text": r["chunk_text"], "meta": r["metadata"], "url": r["source_url"]}
                for r in cur.fetchall()
            ]


def hybrid_search(query: str, top_k: int = 5) -> List[SearchResult]:
    query_vec = embed_text(query)
    dense_results = dense_search(query_vec, limit=30)
    sparse_results = sparse_search(query, limit=30)

    fused = _rrf_fuse(dense_results, sparse_results)

    # Pin exact course match if user mentioned a specific course
    code = resolve_code(query)
    if code:
        exact = exact_course_lookup(code)
        if exact:
            fused = [r for r in fused if r["id"] != exact["id"]]
            fused.insert(0, exact)

    return [
        SearchResult(
            id=r["id"],
            text=r["text"],
            meta=r.get("meta") or {},
            url=r.get("url"),
            score=r.get("score", 0.0)
        )
        for r in fused[:top_k]
    ]
```

### 4. Verification
```powershell
python -c "from core.retrieval import hybrid_search; res = hybrid_search('What are prereqs for CIS 22A?'); print('Top Result ID:', res[0].id if res else 'None')"
```

---

## 3. Section 3: 2-Step Judge & Checkpointed Eval Runner (`run_eval.py`)

### 1. Purpose
* Evaluate accuracy and latency on the 150-question golden set.
* Implement a **2-step judge**:
  1. Determine if the question is answerable from catalog data.
  2. Grade honest refusals (*"I don't have that official information"*) on unanswerable edge cases as **`PASS` (`correct=1`)**.
* Save incremental checkpoints to `eval_results.json` so runs survive interruptions.

### 2. Inputs & Outputs
* **Inputs:** `golden_set.json` (list of Q&A objects).
* **Outputs:** Printed benchmark metrics and `eval_results.json` log.

### 3. Developer Code Draft
```python
"""Robust benchmark and evaluation runner with 2-step judge and checkpointing."""
import json
import os
import time
from dotenv import load_dotenv
from openai import OpenAI
from core.retrieval import hybrid_search
from core.chat import build_prompt_context, SYSTEM_PROMPT

load_dotenv(override=True)

client = OpenAI()
GOLDEN_PATH = "data/golden_set.json" if os.path.exists("data/golden_set.json") else "golden_set.json"
RESULTS_PATH = "eval_results.json"

JUDGE_PROMPT = """You are a strict grading judge for a college student assistant chatbot.

Reference Context Given to Bot:
{context}

Expected Answer:
{expected}

Chatbot Actual Answer:
{actual}

Grading Instructions:
1. Determine if the question is answerable from the Reference Context:
   - If the context does NOT contain the specific fact and the bot honestly states it does not have that information and points to deanza.edu, this is CORRECT behavior (correct=true, answerable=false).
   - If the context contains the answer and the bot answers factually without hallucination, this is CORRECT behavior (correct=true, answerable=true).
   - If the bot fabricates/hallucinates facts or gives incorrect requirements, it is INCORRECT (correct=false).

Respond with ONLY valid JSON:
{{"answerable": true, "correct": true, "score": 100, "reason": "brief explanation"}}
"""


def load_checkpoints() -> dict:
    if os.path.exists(RESULTS_PATH):
        try:
            with open(RESULTS_PATH, "r", encoding="utf-8") as f:
                records = json.load(f)
                return {r["id"]: r for r in records if "id" in r}
        except Exception:
            return {}
    return {}


def judge_answer(context: str, expected: str, actual: str) -> dict:
    prompt = JUDGE_PROMPT.format(
        context=context[:2000],
        expected=expected,
        actual=actual or ""
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        return {"correct": False, "answerable": True, "score": 0, "reason": str(e)}


def run_eval():
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        questions = json.load(f)

    done = load_checkpoints()
    todo = [q for q in questions if q.get("id") not in done]
    total = len(questions)

    print(f"Total: {total} | Already Completed: {len(done)} | Remaining: {len(todo)}\n")

    for i, item in enumerate(todo, 1):
        q_id = item.get("id", len(done) + 1)
        q = item["question"]
        expected = item.get("answer") or item.get("ground_truth", "")

        t0 = time.time()
        chunks = hybrid_search(q, top_k=5)
        ctx = build_prompt_context(chunks)

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{ctx}\n\nStudent Question: {q}"}
            ],
            temperature=0.0
        )
        latency = time.time() - t0
        answer = resp.choices[0].message.content

        judge_res = judge_answer(ctx, expected, answer)
        is_pass = judge_res.get("correct", False)

        record = {
            "id": q_id,
            "question": q,
            "expected": expected,
            "answer": answer,
            "latency": latency,
            "judge": judge_res
        }
        done[q_id] = record

        # Save checkpoint to disk
        with open(RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(list(done.values()), f, indent=2, ensure_ascii=False)

        status_tag = "[PASS]" if is_pass else "[FAIL]"
        print(f"[{len(done)}/{total}] {status_tag} ({latency:.2f}s) Q: {q[:50]}...")

    # Final Summary
    all_results = list(done.values())
    correct_count = sum(1 for r in all_results if r["judge"].get("correct", False))
    avg_latency = sum(r["latency"] for r in all_results) / len(all_results) if all_results else 0.0
    accuracy = (correct_count / len(all_results)) * 100 if all_results else 0.0

    print("\n==========================================")
    print(f"Benchmark Accuracy: {accuracy:.1f}% ({correct_count}/{len(all_results)})")
    print(f"Average Latency:    {avg_latency:.2f}s")
    print(f"Results saved to:   {RESULTS_PATH}")
    print("==========================================")


if __name__ == "__main__":
    run_eval()
```

### 4. Verification
```powershell
python run_eval.py
```
* **Expected Output:**
  - Evaluates questions with checkpointing.
  - Scores >90% accuracy on answerable + honest edge cases.
