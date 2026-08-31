import os 
from dotenv import load_dotenv
import time 
import json 
from openai import OpenAI
import csv 
from core.retrieval import hybrid_search
from core.chat import build_prompt_context

load_dotenv(override=True) #use the api key from .env or global environment

#Initialize client to use models
client = OpenAI(
    base_url = "https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

BENCHMARK_MODELS = [
    #openai 
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/gpt-4-turbo",
    "openai/o3-mini",

    #anthropic
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3.5-haiku",
    "anthropic/claude-3-opus",

    #gemini
    "google/gemini-2.0-flash-001",
    "google/gemini-pro-1.5",
    "google/gemini-flash-1.5",

    #llama
    "meta-llama/llama-3.3-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "meta-llama/llama-3.1-405b-instruct",

    #chinese + cohere + microsoft
    "deepseek/deepseek-chat",
    "deepseek/deepseek-r1",
    "mistralai/mistral-large",
    "mistralai/mistral-small",
    "qwen/qwen-2.5-72b-instruct",
    "cohere/command-r-plus",
    "microsoft/phi-3-medium-128k-instruct",
]

def run_model_inference(
    model: str, 
    question: str,
    context: str,
):
    """This function is to send the student's question, and the retrieved context to openrourter and evaluates the response text"""

    prompt = f"""Context from offical De Anza sources: 
    {context}

    Student Questions: {question}"""

    messages = [
        {
            "role": "system",
            "content": "You are the De Anza College assistant. Answer based only on the provided context. If data is missing, direct to deanza.edu."
        },
        {
            "role": "user",
            "content": prompt
        }
    ]

    start_time = time.perf_counter()
    try: 
        response = client.chat.completions.create(
            model = model, 
            messages = messages,
            temperature=0.2,
            max_tokens = 500,
        )
        latency_ms = (time.perf_counter() - start_time) * 1000 
        answer = response.choices[0].message.content.strip()
        usage = response.usage

        return {
            "answer": answer,
            "latency_ms": round(latency_ms, 2),
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens":usage.completion_tokens if usage else 0,
            "error": None,
        }

    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        return {
            "answer": "",
            "latency_ms": round(latency_ms, 2),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "error": str(e),
        }

#LLM As Judge
"""We use a strong model as a judge to evaluate the quality of the generated answer on different categories"""

JUDGE_PROMPT = """Grade a chatbot answer against the reference context. 

Context:
{context}

Question:
{question}

Answer:
{answer}

Respond ONLY in valid json format: 
{{
    "is_correct": true,
    "score": 100,
    "hallucinated": false,
    "reason": "brief explanation"
}}
"""

def  judge_model_answer(
    question: str,
    context: str,
    answer: str,
):
    """In case the model's output is empty"""
    if not answer:
        return {
            "is_correct": False,
            "score": 0,
            "hallucinated": False,
            "reason": "Model returned empty response or error"
        }

    try:
        resp = client.chat.completions.create(
            model = "gpt-4o",
            messages =  [{
                "role": "user",
                "content": JUDGE_PROMPT.format(
                    context = context[:2000],
                    question = question,
                    answer = answer,
                )
            }],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        return json.loads(resp.choices[0].message.content)

    except Exception as e:
        return{
            "is_correct": False,
            "score": 0,
            "hallucinated": False,
            "reason": f"Judge error: {e}"
        }

"""This function is to run the entire benchmark pipeline"""
def run_full_benchmark(
    models: list = BENCHMARK_MODELS,
    test_case_path: str = "golden.json",
):
    with open(test_case_path, "r", encoding = "utf-8") as f:
        test_cases = json.load(f)

    print(f"Loading {len(test_cases)} test cases and retrieving RAG contexts...")
    test_data = []
    for case in test_cases:
        q = case["question"]
        chunks = hybrid_search(q, top_k=5)
        ctx = build_prompt_context(chunks)
        test_data.append({
            "id": case.get("id"),
            "question": q,
            "context": ctx,
        })

        #Create a dictionary of empty list where ids are the models' names
        results_by_model = {m: [] for m in models}

        len_model = len(models)
        for m_idx, model in enumerate(models, 1): 
            #Showing the progress of benchmarking
            print (f"[\n{m_idx}/{len_model}] Evaluating model: {model}")
            for q_idx, item in enumerate(test_data, 1):
                inf = run_model_inference(
                    model, 
                    item["question"],
                    item["context"],
                )

                #In case there's an error when gernerating the output
                if inf["error"]:
                    print(f" Q{q_idx}: Error ({inf["error"]})")
                    results_by_model[model].append({
                        **item,
                        **inf,
                        "grade": {
                            "is_correct": False,
                            "score": 0,
                            "hallucinated": False,
                            "reason": inf["error"],
                        }
                    })
                    continue

                grade = judge_model_answer(
                    item["question"],
                    item["context"],
                    inf["answer"],
                )

                print(f" Q{q_idx}: Score = {grade.get('score', 0)} | Correct = {grade.get("is_correct")} | Latency={inf['latency_ms']} ms")

                results_by_model[model].append({
                    **item,
                    **inf,
                    "grade": grade
                })

                with open("benchmark_results.json", "w", encoding = 'utf-8') as f:
                    json.dump(results_by_model, f, indent = 2)

    return results_by_model

"""This function is to convert the json benchmark into a .csv table"""
def export_benchmark_summary(
    json_path: str = "benchmark_results.json",
    output_csv_path: str = "output/benchmark_summary.csv",
):
    """In case the json evaluation file doesn't exist"""
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        return 

    with open(json_path, "r", encoding="utf-8") as f:
        results_by_model = json.load(f)

    os.makedirs(os.path.dirname(output_csv_path), exist_ok= True)
    summary = []

    for model, records in results_by_model.items():
        if not records:
            continue

        total = len(records)
        correct_count = sum(1 for r in records if r.get("grade", {}).get("is_correct"))
        halluc_count = sum(1 for r in records if r.get("grade", {}).get("hallucinated"))
        avg_score = sum(r.get("grade", {}).get("score", 0) for r in records) / total
        avg_latency = sum(r.get("latency_ms", {}) for r in records) / total
        total_prompt_tok = sum(r.get("prompt_tokens", 0) for r in records)
        total_comp_tok = sum(r.get("completion_tokens", 0) for r in records)

        summary.append({
            "model": model,
            "total_questions": total,
            "accuracy_pct": round((correct_count / total)* 100, 2),
            "avg_score": round(avg_score, 2),
            "hallucination_pct": round((halluc_count / total) * 100, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "total_prompt_tokens": total_prompt_tok,
            "total_completion_tokens": total_comp_tok,
        })

    summary_headers = [
        "model", "total_questions", "accuracy_pct", "avg_score",
        "hallucination_pct", "avg_latency_ms", "total_prompt_tokens", "total_completion_tokens"
    ]

    with open(output_csv_path, "w", newline = "", encoding = 'utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=summary_headers)
        writer.writeheader()
        writer.writerows(summary)

    print(f"Summary csv file saved to: {output_csv_path}")


if __name__ == "__main__":
    print("Run the entire benchmark pipeline")
    run_full_benchmark()
    export_benchmark_summary()
    print("Finished! Benchmark is saved at output/benchmark_summary.csv")