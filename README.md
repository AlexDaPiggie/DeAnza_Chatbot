# [De Anza AI Chatbot (Click to see the Website)](https://dachatbot.com)
# [Youtube Demo (Click here)](https://www.youtube.com/watch?v=mpQfb1aBXPA)

## Authors

| **Phong Nguyen (Alex)** | **Huy Phan (Hertzy)** |
|:---|:---|
| **AI Engineering & Backend Architecture** | **Frontend Engineering & UI/UX Design** |
| Engineered the end-to-end RAG retrieval pipeline (BM25 + ChromaDB semantic search), multi-model OpenRouter LLM orchestration and fallback engine, automated benchmark harness, query condenser, rate limiter, and FastAPI backend services. | Designed and developed the responsive single-page chat interface (HTML5, CSS3, Vanilla ES6+ JavaScript), real-time SSE stream renderer, dynamic markdown formatter, citation groupers, light/dark theme system, and local conversation persistence. |
| GitHub: [@AlexDaPiggie](https://github.com/AlexDaPiggie)<br>LinkedIn: [Hoai Phong Nguyen](https://www.linkedin.com/in/hoai-phong-nguyen-9367a4384/)<br>Portfolio: [Phong Nguyen](https://phongnguyen.vercel.app/) | GitHub: [@hertzy-da-poet](https://github.com/hertzy-da-poet)<br>Portfolio: [Huy Phan Portfolio](https://hertzy-da-poet.github.io/Hugo-Portfolio/) |

---


## About
- **Student-Focused AI Assistant**: Delivers instant, accurate answers for De Anza College students on courses, prerequisites, financial aid, and transfer planning.
- **Grounded Hybrid RAG**: Combines BM25 keyword matching and pgvector semantic search strictly grounded in official De Anza catalogs, schedules, and policies to prevent hallucinations.
- **Fast, Reliable Delivery**: Streams responses in real time with verified source citations, multi-model fallback, and an automated 12-model benchmarking harness.

---

## Architecture Pipeline

```mermaid
flowchart LR
    User["Student User"] --> UI["Frontend Web App<br/>(HTML / CSS / JS)"]
    UI -->|"POST /api/chat"| API["FastAPI Backend<br/>(main.py)"]
    API <-->|"Hybrid Retrieval"| DB[("Neon PostgreSQL<br/>(pgvector + GIN)")]
    API <-->|"LLM Stream"| LLM["OpenRouter<br/>(Gemini + Fallback Models)"]
    API -->|"SSE Tokens"| UI
```

1. **Intake & Rate Limiting ([`main.py`](main.py) + [`rate_limiter.py`](core/rate_limiter.py))**: Receives request payload, checks device ID and client IP against the sliding window rate limiter.
2. **Context Resolution ([`chat.py`](core/chat.py) + [`fast_prompts.py`](core/fast_prompts.py))**: Checks if the query matches curated fast prompts to serve verified context instantly; otherwise triggers query condensation.
3. **Hybrid Search ([`retrieval.py`](core/retrieval.py))**: Searches the indexed De Anza knowledge base using PostgreSQL full-text search for keyword accuracy and pgvector for semantic intent, fusing results into a prompt context.
4. **Prompt Assembly & Guardrails ([`chat.py`](core/chat.py))**: Injects strict formatting rules, recent conversation turns, and verified context with source URLs.
5. **Model Orchestration & Fallback**: Dispatches streaming chat completion to OpenRouter. If the primary model fails or times out, the system automatically falls back to secondary models.
6. **Live Streaming & Rendering ([`app.js`](public/js/app.js) + [`config.js`](public/js/config.js))**: Streams tokens to the client over SSE, sanitizes headings and lists, and groups citation links.

---

## Database Management

How data is scraped, stored, and indexed. Code lives in [`core/db.py`](core/db.py), [`core/chunking.py`](core/chunking.py), and [`scrapers/`](scrapers/).

### 1. Storage & Schema
- **Database Engine**: Hosted PostgreSQL instance on Neon with the `pgvector` extension.
- **Connection Pool**: `psycopg2.pool.ThreadedConnectionPool` (2–10 connections) in [`core/db.py`](core/db.py).
- **Primary Table (`chunks`)**: Single table storing all document types to keep retrieval unified:
  - `id`: Unique serial ID.
  - `source_type`: Data source category (`course`, `catalog`, `schedule`, `web`).
  - `source_url`: Verifiable link for student citations.
  - `doc_id`: Unique document slug (e.g., `cis-22a`).
  - `chunk_text`: Formatted markdown text injected into LLM context.
  - `embedding`: 1536-dimensional vector (`text-embedding-3-small`).
  - `tsv`: `tsvector` generated column (`to_tsvector('english', chunk_text)`).
  - `metadata`: JSONB storing structured fields (`code`, `units`, `crn`, `dept`).
- **Cache Table (`crawl_cache`)**: Stores `(source_type, doc_id, content_hash)`. Uses SHA-256 to skip unchanged pages during re-indexing and save OpenAI embedding API costs.

### 2. Indexes
Three distinct indexes support different retrieval paths:
- **`idx_chunks_hnsw`**: HNSW index on `embedding` (`vector_cosine_ops`) for sub-10ms semantic cosine search.
- **`idx_chunks_tsv`**: GIN index on `tsv` for English full-text keyword search.
- **`idx_chunks_source_code`**: B-Tree index on `(metadata->>'code')` for instant exact course lookups (e.g., `CIS 22A`).

### 3. Data Sources & Update Frequency
- **Course Catalog ([deanza.elumenapp.com](https://deanza.elumenapp.com/catalog))**:
  - Scraped by [`scrapers/catalog.py`](scrapers/catalog.py).
  - *Cadence*: **Static (Annual)**. Updated once per academic year.
- **Academic Policies & Degree Guides**:
  - Scraped by [`scrapers/pages.py`](scrapers/pages.py).
  - *Cadence*: **Static (Annual)**. Degree requirements, transfer rules, grading policies.
- **Class Schedule ([deanza.edu/schedule](https://www.deanza.edu/schedule/))**:
  - Scraped by [`scrapers/schedule.py`](scrapers/schedule.py).
  - *Cadence*: **Dynamic (Quarterly/Weekly)**. Active sections, CRNs, meeting times, instructors.
- **Campus Service Pages ([deanza.edu](https://www.deanza.edu))**:
  - Scraped by [`scrapers/deanza_web.py`](scrapers/deanza_web.py).
  - *Cadence*: **Semi-Static (Quarterly)**. Academic calendar deadlines, financial aid, cashier fees, counseling.

### 4. Contributor Guide: Re-indexing & Adding Sources
- **Run full ingestion pipeline**:
  ```bash
  python scrapers/pipeline.py
  ```
- **Add a new data source**:
  1. Add scraper function in [`scrapers/`](scrapers/) that returns structured dicts.
  2. Add chunking logic in [`core/chunking.py`](core/chunking.py) to convert pages into `Chunk` objects.
  3. Register the scraper in [`scrapers/pipeline.py`](scrapers/pipeline.py).
  4. Run `python scrapers/pipeline.py`. Hashes prevent re-embedding unchanged documents.

```mermaid
flowchart LR
    subgraph Scraping["Scrapers (scrapers/)"]
        S1["Catalog"]
        S2["Schedule"]
        S3["Web Hubs"]
    end

    subgraph Pipeline["Ingestion (scrapers/pipeline.py)"]
        S1 --> P["Parser & Sanitizer"]
        S2 --> P
        S3 --> P
        P --> H{"SHA-256 Changed?"}
        H -->|"No"| Skip["Skip (crawl_cache)"]
        H -->|"Yes"| Chunks["Chunking & Embedding"]
    end

    subgraph DB["PostgreSQL Database (core/db.py)"]
        Chunks --> T[("chunks Table")]
        T --> HNSW["HNSW Vector Index"]
        T --> GIN["GIN Full-Text Index"]
        T --> BTree["B-Tree Code Index"]
    end
```

---

## RAG Pipeline

How queries are processed, retrieved, ranked, and streamed. Code lives in [`core/retrieval.py`](core/retrieval.py) and [`core/chat.py`](core/chat.py).

### 1. Step-by-Step Flow
- **1. Query Condensation & Fast Cache ([`core/chat.py`](core/chat.py) + [`core/fast_prompts.py`](core/fast_prompts.py))**:
  - Conversational follow-ups with history are rewritten into standalone questions by an LLM condenser.
  - Frequent campus topics (financial aid, TAG, Promise) hit pre-cached context and return immediately without querying PostgreSQL.
- **2. Course Code Extraction & Normalization ([`core/course_codes.py`](core/course_codes.py))**:
  - Regex detects course codes (`CIS D022A` -> `CIS 22A`).
  - Direct B-Tree lookup via `exact_course_lookup()`. If matched, pins chunk directly to rank #1.
- **3. Parallel Hybrid Search ([`core/retrieval.py`](core/retrieval.py))**:
  - **Dense Semantic Search**: Converts query into a 1536-dimensional vector using OpenAI `text-embedding-3-small`. Uses PostgreSQL `pgvector` cosine operator (`<=>`) over the HNSW index to retrieve the top 30 closest chunks by meaning.
  - **Sparse Lexical Search**: Runs PostgreSQL full-text search (`plainto_tsquery`) over the GIN index. Uses `ts_rank_cd` to retrieve the top 30 keyword matches ranked by word frequency and proximity.
- **4. Reciprocal Rank Fusion (RRF)**:
  - Merges dense and sparse lists using the custom RRF function in [`_rrf_fuse()`](core/retrieval.py):
    $$\text{RRF}(d) = \sum_{m \in \{\text{dense}, \text{sparse}\}} \frac{1}{k + r_m(d)}$$
    Where $k = 60$ is a smoothing constant, and $r_m(d) \in [1, 30]$ is the rank of chunk $d$ in retrieval list $m$.
  - If an exact course code was matched in Step 2, it receives an override score of `1.0` (pinned to rank #1).
  - Selects the top 5 highest-ranked chunks for final context.
- **5. Context Assembly & Guardrails ([`core/chat.py`](core/chat.py))**:
  - Formats top 5 chunks into context blocks labeled with `(Source: <url>)`.
  - System prompt enforces strict anti-hallucination rules: answer only from provided context, and format links under `### Sources`.
- **6. Streaming & Model Fallback Cascade ([`core/chat.py`](core/chat.py))**:
  - Dispatches assembled prompt to OpenRouter using Server-Sent Events (SSE).
  - Fallback loop: primary model (`gemini-2.5-flash`) -> secondary models (`gpt-4o-mini`, `mistral-small`) if primary times out or returns an error.


### 3. End-to-End RAG Lifecycle
High-level view from student query to streaming response:

```mermaid
flowchart TD
    UserQ["Student Query"] --> History{"History Present?"}
    History -->|"Yes"| Condense["Condense Query (LLM)"]
    History -->|"No"| RawQ["Direct Query"]

    Condense --> FastCheck{"Fast Prompt Match?"}
    RawQ --> FastCheck

    FastCheck -->|"Yes"| Cached["Pre-Cached Context"]
    FastCheck -->|"No"| HybridSearch["Hybrid Search Engine<br/>(core/retrieval.py)"]

    HybridSearch --> TopChunks["Top 5 Fused Chunks"]
    Cached --> Assembly["Context Assembly<br/>(core/chat.py)"]
    TopChunks --> Assembly

    Assembly --> LLM{"Primary Model: Gemini 2.5 Flash"}
    LLM -->|"Fail / Timeout"| Fallback["Fallback Cascade: GPT-4o-mini"]
    LLM -->|"Success"| Stream["SSE Token Stream"]
    Fallback -->|"Success"| Stream
    Stream --> Client["Frontend UI"]
```

### 4. Contributor Guide: Tuning & Extending RAG
- **Adjust search weights or top results**: Edit `top_k` in `hybrid_search()` in [`core/retrieval.py`](core/retrieval.py).
- **Add pre-cached fast answers**: Add question and context to `FAST_PROMPT_CONTEXTS` in [`core/fast_prompts.py`](core/fast_prompts.py).
- **Change models or fallback sequence**: Edit `CHAT_MODEL` and fallback list in [`core/chat.py`](core/chat.py).
- **Modify prompt rules or citation style**: Edit `SYSTEM_PROMPT` in [`core/chat.py`](core/chat.py).

---

## How to Run this on Local?

### Prerequisites
- Python 3.11+
- PostgreSQL database (Local or hosted e.g. Neon, Supabase)
- OpenRouter API key (`OPENROUTER_API_KEY`)

### 1. Environment Setup

```bash
# Clone repository
git clone https://github.com/AlexDaPiggie/DeAnza_Chatbot.git
cd DeAnza_Chatbot

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the root directory:

```env
OPENROUTER_API_KEY=your_openrouter_api_key
DATABASE_URL=postgresql://user:password@localhost:5432/deanza_chatbot
CHAT_MODEL=google/gemini-2.5-flash,openai/gpt-4o-mini,mistralai/mistral-small-24b-instruct-2501
CONDENSER_MODEL=google/gemini-2.5-flash-lite
DEBUG_LOGS=true
```

### 3. Start the Server

```bash
# Start FastAPI application
python main.py
```

- Web Interface: `http://127.0.0.1:8000`
- Interactive API Docs (Swagger): `http://127.0.0.1:8000/docs`

---

## Model Evaluation & Benchmarking

The project contains a comprehensive evaluation pipeline ([eval/benchmark.py](eval/benchmark.py)) and analysis notebook ([output/model_analysis.ipynb](output/model_analysis.ipynb)) testing 12 leading LLMs against a 150-question golden dataset curated from real student inquiries.

### Running the Benchmark

```powershell
# Run benchmark across all models
python eval/benchmark.py

# Test a specific model on a subset of questions
python eval/benchmark.py --model openai/gpt-4o-mini --limit 10

# Regenerate summary CSV directly from JSON without calling APIs
python eval/benchmark.py --summary-only
```

### 1. Accuracy & Hallucination Rate

Measures model response correctness against context reference facts using an LLM Judge (`openai/gpt-4o-mini`).

<p align="center">
  <img src="output/accuracy_score_rate.png" alt="Accuracy Score and Hallucination Rate across Models" width="90%"/>
</p>

* **Top Performers**: `google/gemini-2.5-flash` (94.7% accuracy, 5.3% hallucination) and `deepseek/deepseek-r1-distill-llama-70b` (94.0% accuracy, 6.0% hallucination) led the benchmark in factual precision.
* **Instruction Following**: Small-to-mid models (`ministral-8b`, `gemini-2.5-flash-lite`, `gpt-4o-mini`) maintained >87% accuracy while strictly adhering to formatting constraints.

### 2. Cost & Token Efficiency

Compares total token consumption and API expenditures across all 150 benchmark test cases.

<p align="center">
  <img src="output/estimated_cost_avg_tokens.png" alt="Estimated Cost and Token Usage across Models" width="90%"/>
</p>

* **Cost Leaders**: `meta-llama/llama-3.2-3b-instruct` ($0.011 for 150 queries) and `mistralai/mistral-small-24b-instruct-2501` ($0.022 for 150 queries) proved exceptionally economical.
* **Production Balance**: `gemini-2.5-flash-lite` ($0.038 total) and `gpt-4o-mini` ($0.062 total) delivered ideal balances between sub-second TTFT and low operational costs.

### 3. Latency & Markdown Formatting Quality

Evaluates Time To First Token (TTFT), total response latency, and markdown formatting adherence across all models.

<p align="center">
  <img src="output/estimated_md_pass_tfft_latency.png" alt="Markdown Pass Rate, TTFT, and Latency across Models" width="90%"/>
</p>

* **Speed Champions**: `google/gemini-2.5-flash` (925ms TTFT, 1.89s latency) and `gemini-2.5-flash-lite` (1001ms TTFT, 1.59s latency) yielded the fastest real-time streaming experiences.
* **Formatting Reliability**: `mistralai/ministral-8b-2512` (100% pass rate) and `openai/gpt-4o-mini` (97.3% pass rate) excelled in AST markdown structure compliance.
* **Reasoning Latency Tradeoff**: Deep reasoning models like `deepseek-r1-distill-llama-70b` produced high token volumes and reasoning chains, resulting in substantially higher latency unsuitable for interactive chat.

---

## Model Sequencing & Fallback Architecture

Based on extensive empirical benchmarking across accuracy, markdown pass rate, TTFT, and cost:

* **Primary Chat Model: `google/gemini-2.5-flash`**
  * **94.7% accuracy**, 925ms average TTFT, low token cost, and outstanding synthesis of complex campus policy documents.
* **Secondary Fallback: `openai/gpt-4o-mini`**
  * **97.3% markdown pass rate**, solid 87.3% accuracy, and high API stability under heavy loads.
* **Tertiary Fallbacks**:
  * `mistralai/mistral-small-24b-instruct-2501` (cost efficiency and high compliance)
  * `meta-llama/llama-3.3-70b-instruct` (high reasoning capability on ambiguous questions)

---

## Repository Structure

```
DeAnza_Chatbot/
├── core/                       # Core backend business logic and RAG engine
│   ├── chat.py                 # Chat streaming orchestrator, system prompts, model loop
│   ├── chunking.py             # Document segmentation and metadata enrichment
│   ├── course_codes.py         # Course code normalizer and regex matcher
│   ├── db.py                   # PostgreSQL database pool connector
│   ├── embed.py                # Embedding vector generation interface
│   ├── fast_prompts.py         # Curated pre-cached context for instant answers
│   ├── rate_limiter.py         # In-memory sliding window rate limiter
│   ├── retrieval.py            # Hybrid retrieval (BM25 keyword + ChromaDB vector)
│   └── schemas.py              # Pydantic request / response validation models
├── eval/                       # Benchmarking and model evaluation suite
│   └── benchmark.py            # Automated evaluation runner with background LLM judge
├── eval_results/               # Benchmark data outputs
│   ├── benchmark_results.json  # Comprehensive per-question raw evaluation JSON
│   ├── benchmark_summary.csv   # Aggregated performance metrics per model
│   └── model_comparison.csv    # Flattened question-by-question comparative CSV
├── output/                     # Analysis artifacts and data visualizations
│   ├── accuracy_score_rate.png # Visual comparison of accuracy and hallucination rates
│   ├── benchmark_summary.csv   # Summary metrics consumed by visualization notebook
│   ├── estimated_cost_avg_tokens.png # Visual comparison of token usage and costs
│   └── model_analysis.ipynb    # Jupyter notebook for benchmark analytics and plotting
├── public/                     # Frontend client web application
│   ├── css/                    # Modular stylesheets (theme, components, layout)
│   ├── js/                     # Frontend logic
│   │   ├── api.js              # API client and SSE stream reader
│   │   ├── app.js              # Main application controller, state, event listeners
│   │   ├── config.js           # Configuration, endpoints, markdown formatting rules
│   │   └── ui.js               # DOM manipulation, message rows, citation links
│   └── index.html              # Main single-page application markup
├── scrapers/                   # Campus document collectors and scrapers
├── tests/                      # Automated unit and integration tests
├── golden_set.json             # 150 curated golden benchmark evaluation questions
├── main.py                     # FastAPI application entrypoint and static file server
├── requirements.txt            # Python production dependencies
└── README.md                   # Project documentation and architecture guide
```