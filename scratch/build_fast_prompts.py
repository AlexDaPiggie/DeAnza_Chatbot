import os
from core.retrieval import hybrid_search
from core.chat import build_prompt_context

prompts = [
    "How does the Transfer Admission Guarantee (TAG) program work at De Anza?",
    "How do I apply for financial aid, FAFSA, or fee waivers at De Anza?",
    "How do I schedule an appointment with a general or academic counselor?",
    "What are the add, drop, and refund deadlines for standard 12-week classes this quarter?"
]

cache = {}
for p in prompts:
    print(f"Retrieving context for: {p}")
    chunks = hybrid_search(p, top_k=5)
    cache[p] = build_prompt_context(chunks)

output_file = os.path.join("core", "fast_prompts.py")
with open(output_file, "w", encoding="utf-8") as f:
    f.write('"""Pre-cached RAG contexts for home screen fast prompts to bypass search."""\n\n')
    f.write("FAST_PROMPT_CONTEXTS = {\n")
    for k, v in cache.items():
        f.write(f"    {repr(k)}: {repr(v)},\n")
    f.write("}\n")

print(f"Successfully wrote {len(cache)} prompt contexts to {output_file}")
