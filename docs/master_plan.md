# De Anza College AI Chatbot — Production Redo Master Plan (v2)

A step-by-step implementation guide to rebuilding the De Anza AI Chatbot in a clean workspace with:
1. **Automated Quarterly Scraping Pipeline** (Dynamic term resolution, BeautifulSoup4 parsing, differential hash updates).
2. **High-Accuracy Hybrid Retrieval** (GIN-indexed Full-Text Search, pgvector HNSW, Course-Code Normalization, Reciprocal Rank Fusion).
3. **Sub-Second Streaming Response** (Database connection pooling, async SSE token generator).
4. **Structured Markdown Output** (Bullet points, bold text, short paragraphs, zero-hallucination citations).
5. **Automated GitHub Actions Cron** (Quarterly data refresh with zero manual intervention).

---

## 1. Migration Checklist (What to Copy Over)

When creating your new empty workspace, copy these baseline files:

### Benchmark & Baseline Data (`data/` folder)
* `data/golden_set.json` (150 verified Q&A test pairs for quality benchmarks)
* *(Optional)* Initial JSON snapshots if you want to test ingest before running the new live scraper:
  * `data/catalog_courses_full.json`
  * `data/catalog_pages_full.json`
  * `data/schedule_summer2026.json`

---

## 2. Target Clean Workspace Structure

```text
deanza-chatbot/
├── .github/
│   └── workflows/
│       └── quarterly_refresh.yml   # Automated quarterly scraper cron
├── data/                           # Scraped data snapshots & eval sets
│   ├── catalog_courses.json
│   ├── catalog_pages.json
│   ├── schedule.json
│   └── golden_set.json
├── scrapers/                       # High-reliability scraping suite
│   ├── __init__.py
│   ├── client.py                   # Session with auto-retries & user-agent
│   ├── terms.py                    # Dynamic term & quarter resolver
│   ├── catalog.py                  # eLumen API catalog scraper
│   ├── schedule.py                 # BeautifulSoup schedule table parser
│   ├── pages.py                    # Policy & deadlines parser
│   └── pipeline.py                 # Scrape -> Diff -> Embed -> DB orchestrator
├── core/                           # Production application core
│   ├── __init__.py
│   ├── schemas.py                  # Pydantic data models
│   ├── db.py                       # Postgres connection pool & schema
│   ├── embed.py                    # Fast embedding API client
│   ├── chunking.py                 # Structure-aware & text chunkers
│   ├── course_codes.py             # Course code regex normalizer
│   ├── retrieval.py                # Hybrid RRF (pgvector + GIN tsvector)
│   └── chat.py                     # Formatted prompt & SSE token stream
├── public/                         # Minimalist frontend
│   ├── index.html                  # Clean chat UI + live markdown rendering
│   └── app.js                      # SSE stream handler & feedback
├── api_server.py                   # FastAPI server
├── run_eval.py                     # Accuracy & latency benchmark runner
├── .env.example
└── requirements.txt
```

---

## 3. Step-by-Step Implementation Guide

---

### Step 1: Dependencies (`requirements.txt`)

#### 1. Purpose
Define the minimal set of production libraries for scraping, storage, search, and API.

#### 2. Code Draft
```text
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
pydantic>=2.6.0
psycopg2-binary>=2.9.9
openai>=1.30.0
requests>=2.31.0
beautifulsoup4>=4.12.0
lxml>=5.1.0
httpx>=0.27.0
python-dotenv>=1.0.1
pytest>=8.0.0
```

#### 3. Verification
```bash
pip install -r requirements.txt
```
Ensure all packages install without conflict.

---

### Step 2: Data Contracts (`core/schemas.py`)

#### 1. Purpose
Provide explicit, typed schemas for data flowing between scrapers, database, search, and API.

#### 2. Inputs & Outputs
* **Inputs**: Dictionaries from scrapers, DB queries, or API requests.
* **Outputs**: Validated Pydantic objects.

#### 3. Code Draft
```python
"""Data schemas for the De Anza RAG chatbot."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChunkMetadata(BaseModel):
    source_type: str = Field(..., description="'course', 'page', or 'section'")
    code: Optional[str] = Field(None, description="Course code e.g. 'CIS 22A'")
    title: Optional[str] = Field(None, description="Title of course or page")
    units: Optional[float] = Field(None, description="Course unit value")
    prereqs: Optional[str] = Field(None, description="Course prerequisite text")
    crn: Optional[str] = Field(None, description="Class CRN number")
    quarter: Optional[str] = Field(None, description="Academic quarter e.g. 'fall-2026'")
    extra: Dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    source_type: str
    source_url: str
    doc_id: str
    title: str
    chunk_text: str
    embedding: Optional[List[float]] = None
    metadata: ChunkMetadata


class SearchResult(BaseModel):
    id: int
    text: str
    meta: Dict[str, Any]
    url: Optional[str]
    score: float = 0.0


class ChatMessage(BaseModel):
    role: str  # "user", "assistant", or "system"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    query_text: str
    answer_text: str
    rating: int  # 1 for up, 0 for down
    model_used: str
```

#### 4. Verification
Create and run a quick check in python:
```python
from core.schemas import ChunkMetadata, Chunk

meta = ChunkMetadata(source_type="course", code="CIS 22A", title="Intro to C++")
chunk = Chunk(
    source_type="course",
    source_url="https://deanza.edu",
    doc_id="cis-22a",
    title="CIS 22A",
    chunk_text="Intro to programming in C++...",
    metadata=meta
)
assert chunk.metadata.code == "CIS 22A"
print("Schemas verified successfully.")
```

---

### Step 3: Database Engine with Pool & GIN Index (`core/db.py`)

#### 1. Purpose
Manage PostgreSQL connection pooling, create vector tables, GIN indexes for fast full-text search, and the `crawl_cache` table for differential hash tracking.

#### 2. Inputs & Outputs
* `get_db()`: Context manager checking out and returning connection to the pool.
* `init_db()`: Sets up database extensions, tables, and indexes.

#### 3. Code Draft
```python
"""Database connection pooling and schema management."""
import os
from contextlib import contextmanager
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://deanza:deanza@127.0.0.1:5432/deanza")

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id             SERIAL PRIMARY KEY,
    source_type    TEXT NOT NULL,
    source_url     TEXT,
    doc_id         TEXT,
    title          TEXT,
    chunk_text     TEXT NOT NULL,
    embedding      vector(1536),
    metadata       JSONB,
    tsv            tsvector GENERATED ALWAYS AS (to_tsvector('english', chunk_text)) STORED,
    created_at     TIMESTAMPTZ DEFAULT now()
);

-- Index for dense vector cosine similarity
CREATE INDEX IF NOT EXISTS idx_chunks_hnsw 
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- Index for fast keyword search (GIN)
CREATE INDEX IF NOT EXISTS idx_chunks_tsv 
    ON chunks USING gin (tsv);

-- Index for exact metadata lookups
CREATE INDEX IF NOT EXISTS idx_chunks_source_code 
    ON chunks ((metadata->>'code')) WHERE source_type = 'course';

CREATE TABLE IF NOT EXISTS crawl_cache (
    source_type   TEXT NOT NULL,
    doc_id        TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    updated_at    TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (source_type, doc_id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id          SERIAL PRIMARY KEY,
    query_text  TEXT,
    answer_text TEXT,
    rating      SMALLINT,
    model_used  TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);
"""

_pool = None

def get_pool():
    global _pool
    if _pool is None or _pool.closed:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=20,
            dsn=DATABASE_URL,
            cursor_factory=RealDictCursor
        )
    return _pool

@contextmanager
def get_db():
    p = get_pool()
    conn = p.getconn()
    try:
        yield conn
    finally:
        p.putconn(conn)

def init_db():
    with get_db() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
    print("Database initialized with pgvector, GIN index, and crawl_cache.")
```

#### 4. Verification
```bash
python -c "from core.db import init_db; init_db()"
```
Confirm `chunks`, `crawl_cache`, and `feedback` tables are created in Postgres.

---

### Step 4: Resilient HTTP Client & Dynamic Term Resolver (`scrapers/client.py`, `scrapers/terms.py`)

#### 1. Purpose
* `scrapers/client.py`: A unified `requests.Session` with automatic 3-retry backoff on rate limits and network drops.
* `scrapers/terms.py`: Automatically discovers the active academic year and quarter from De Anza API (eliminating hardcoded years).

#### 2. Code Draft (`scrapers/client.py`)
```python
"""Robust HTTP client session with automatic retries."""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

USER_AGENT = "DeAnza-AI-Bot/1.0 (Educational Assistant; contact: student-admin@deanza.edu)"

def get_session() -> requests.Session:
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session
```

#### 3. Code Draft (`scrapers/terms.py`)
```python
"""Dynamic academic term and quarter discovery."""
import datetime
import re
from scrapers.client import get_session

ELUMEN_API = "https://api-prod.elumenapp.com"
TENANT = "deanza.elumenapp.com"

def get_active_catalog_term() -> str:
    """Fetch the latest active catalog term from eLumen publish route."""
    session = get_session()
    try:
        resp = session.get(f"{ELUMEN_API}/catalog/sites/publish", params={"tenant": TENANT}, timeout=15)
        if resp.status_code == 200:
            html = resp.json().get("html", "")
            # Look for patterns like 2025-2026 or 2026-2027
            terms = re.findall(r"\b(20\d{2}-20\d{2})\b", html)
            if terms:
                return sorted(list(set(terms)))[-1]
    except Exception as e:
        print(f"Warning: Failed to fetch active term from eLumen: {e}")

    # Fallback to current year calculation
    now = datetime.datetime.now()
    year = now.year
    if now.month >= 8:  # Fall quarter or later
        return f"{year}-{year + 1}"
    return f"{year - 1}-{year}"

def get_current_quarter() -> str:
    """Determine current academic quarter based on month."""
    month = datetime.datetime.now().month
    if month in (9, 10, 11, 12):
        return "fall"
    elif month in (1, 2, 3):
        return "winter"
    elif month in (4, 5, 6):
        return "spring"
    return "summer"
```

#### 4. Verification
```python
from scrapers.terms import get_active_catalog_term, get_current_quarter

term = get_active_catalog_term()
quarter = get_current_quarter()
print(f"Detected Term: {term}, Quarter: {quarter}")
assert "-" in term and len(term) == 9
```

---

### Step 5: High-Reliability Scrapers (`scrapers/catalog.py`, `scrapers/schedule.py`, `scrapers/pages.py`)

#### 1. Purpose
Extract structured courses, sections, and policy pages using direct APIs and `BeautifulSoup4`.

#### 2. Code Draft (`scrapers/catalog.py`)
```python
"""Direct eLumen API catalog scraper."""
import concurrent.futures as cf
from typing import List, Dict, Any
from scrapers.client import get_session
from scrapers.terms import get_active_catalog_term

API_URL = "https://api-prod.elumenapp.com"
TENANT = "deanza.elumenapp.com"

def fetch_course_detail(session, term: str, course_id: str) -> Dict[str, Any] | None:
    url = f"{API_URL}/catalog/sites/publish/course/{term},{course_id}"
    try:
        r = session.get(url, params={"tenant": TENANT}, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def scrape_catalog(max_workers: int = 8) -> List[Dict[str, Any]]:
    term = get_active_catalog_term()
    session = get_session()
    print(f"Scraping catalog for term {term}...")
    
    # 1. Get course list
    list_url = f"{API_URL}/catalog/sites/publish/courses/{term}"
    resp = session.get(list_url, params={"tenant": TENANT}, timeout=30)
    resp.raise_for_status()
    course_items = resp.json().get("courses", [])
    print(f"Found {len(course_items)} catalog courses. Fetching details...")

    # 2. Parallel fetch course details
    courses = []
    with cf.ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_item = {
            pool.submit(fetch_course_detail, session, term, c.get("id")): c
            for c in course_items if c.get("id")
        }
        for future in cf.as_completed(future_to_item):
            detail = future.result()
            if detail:
                courses.append(detail)

    print(f"Successfully fetched {len(courses)} courses.")
    return courses
```

#### 3. Code Draft (`scrapers/schedule.py`)
```python
"""BeautifulSoup4 Class Schedule Parser."""
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from scrapers.client import get_session

SCHEDULE_BASE = "https://mobile.deanza.edu/schedule"
PAGES = ["online-classes.html", "gen-ed-classes.html", "late-start.html"]

def scrape_schedule() -> List[Dict[str, Any]]:
    session = get_session()
    sections = []
    
    for page in PAGES:
        url = f"{SCHEDULE_BASE}/{page}"
        print(f"Scraping schedule page {url}...")
        try:
            r = session.get(url, timeout=30)
            if r.status_code != 200:
                continue
            
            soup = BeautifulSoup(r.text, "lxml")
            rows = soup.select("table.table-schedule tr.mix")
            for row in rows:
                cols = [td.get_text(" ", strip=True) for td in row.find_all("td")]
                if len(cols) >= 9:
                    crn, course, sec, seats, title, days, times, instructor, loc = cols[:9]
                    sections.append({
                        "crn": crn,
                        "course": course,
                        "section": sec,
                        "seats": seats,
                        "title": title.split("View Footnote")[0].strip(),
                        "days": days,
                        "times": times,
                        "instructor": instructor,
                        "location": loc,
                        "source_url": url
                    })
        except Exception as e:
            print(f"Error scraping schedule page {page}: {e}")

    print(f"Total schedule sections scraped: {len(sections)}")
    return sections
```

#### 4. Code Draft (`scrapers/pages.py`)
```python
"""Policy and College Information Pages Parser."""
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from scrapers.client import get_session
from scrapers.terms import get_active_catalog_term

API_URL = "https://api-prod.elumenapp.com"
TENANT = "deanza.elumenapp.com"

def scrape_catalog_pages() -> List[Dict[str, Any]]:
    term = get_active_catalog_term()
    session = get_session()
    print(f"Scraping static policy pages for term {term}...")

    # Fetch navigation
    resp = session.get(f"{API_URL}/catalog/sites/publish/{term}", params={"tenant": TENANT}, timeout=30)
    resp.raise_for_status()
    html = resp.json().get("html", "")

    soup = BeautifulSoup(html, "lxml")
    slugs = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith(f"{term}/") and not href.startswith(f"{term}/#"):
            slug = href[len(term) + 1:].split("#")[0]
            if slug and slug not in slugs:
                slugs.append(slug)

    print(f"Found {len(slugs)} policy page slugs.")
    pages = []
    for slug in slugs:
        url = f"{API_URL}/catalog/sites/publish/content/{term},{slug}"
        try:
            r = session.get(url, params={"tenant": TENANT}, timeout=15)
            if r.status_code == 200:
                body_soup = BeautifulSoup(r.text, "lxml")
                # Remove scripts and style
                for tag in body_soup(["script", "style"]):
                    tag.decompose()
                text = body_soup.get_text("\n", strip=True)
                title = slug.replace("-", " ").title()
                pages.append({
                    "slug": slug,
                    "title": title,
                    "url": f"https://deanza.elumenapp.com/catalog/{term}/{slug}",
                    "content": text
                })
        except Exception as e:
            print(f"Error fetching page slug {slug}: {e}")

    return pages
```

#### 5. Verification
Run a quick test scraping run:
```bash
python -c "from scrapers.catalog import scrape_catalog; courses = scrape_catalog(); print('Sample course:', courses[0].get('code'))"
```

---

### Step 6: Chunking & Embeddings (`core/chunking.py`, `core/embed.py`)

#### 1. Purpose
* `core/embed.py`: API wrapper returning 1536-dim vectors.
* `core/chunking.py`: Preserves complete course descriptions in single chunks; splits prose on paragraphs.

#### 2. Code Draft (`core/embed.py`)
```python
"""Fast embeddings client."""
import os
from typing import List
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

def embed_text(text: str) -> List[float]:
    clean_text = text.replace("\n", " ").strip()
    resp = client.embeddings.create(input=[clean_text], model=EMBED_MODEL)
    return resp.data[0].embedding

def embed_batch(texts: List[str]) -> List[List[float]]:
    clean_texts = [t.replace("\n", " ").strip() for t in texts if t.strip()]
    if not clean_texts:
        return []
    resp = client.embeddings.create(input=clean_texts, model=EMBED_MODEL)
    return [d.embedding for d in resp.data]
```

#### 3. Code Draft (`core/chunking.py`)
```python
"""Document and course chunking logic."""
import re
from typing import List
from core.schemas import Chunk, ChunkMetadata

def chunk_course(c: dict) -> Chunk:
    code = (c.get("code") or c.get("course_code") or "").strip()
    title = (c.get("title") or c.get("name") or "").strip()
    units = c.get("units")
    desc = (c.get("description") or "").strip()
    prereqs = (c.get("prerequisites") or c.get("prereq_text") or "None").strip()
    dept = (c.get("department") or "").strip()
    url = c.get("url") or f"https://deanza.elumenapp.com/catalog/course/{code}"

    text = (
        f"Course Code: {code}\n"
        f"Title: {title}\n"
        f"Department: {dept}\n"
        f"Units: {units}\n"
        f"Prerequisites: {prereqs}\n"
        f"Description: {desc}"
    )

    meta = ChunkMetadata(
        source_type="course",
        code=code,
        title=title,
        units=float(units) if units and str(units).replace(".", "", 1).isdigit() else None,
        prereqs=prereqs,
        extra={"department": dept}
    )

    return Chunk(
        source_type="course",
        source_url=url,
        doc_id=code.lower().replace(" ", "-"),
        title=f"{code} - {title}",
        chunk_text=text,
        metadata=meta
    )

def chunk_page(p: dict, max_chars: int = 1500, overlap_chars: int = 200) -> List[Chunk]:
    url = p.get("url") or ""
    title = p.get("title") or "De Anza Policy"
    content = p.get("content") or ""
    
    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    paragraphs = content.split("\n\n")
    
    chunks: List[Chunk] = []
    current_text = ""
    chunk_idx = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current_text) + len(para) <= max_chars:
            current_text += ("\n\n" if current_text else "") + para
        else:
            if current_text:
                chunks.append(Chunk(
                    source_type="page",
                    source_url=url,
                    doc_id=f"{url}#part-{chunk_idx}",
                    title=f"{title} (Part {chunk_idx + 1})",
                    chunk_text=current_text,
                    metadata=ChunkMetadata(source_type="page", title=title)
                ))
                chunk_idx += 1
                current_text = current_text[-overlap_chars:] + "\n\n" + para
            else:
                current_text = para

    if current_text.strip():
        chunks.append(Chunk(
            source_type="page",
            source_url=url,
            doc_id=f"{url}#part-{chunk_idx}",
            title=f"{title} (Part {chunk_idx + 1})" if chunk_idx > 0 else title,
            chunk_text=current_text.strip(),
            metadata=ChunkMetadata(source_type="page", title=title)
        ))

    return chunks
```

---

### Step 7: Automated Scraping & Differential Ingest Pipeline (`scrapers/pipeline.py`)

#### 1. Purpose
The single orchestrator:
1. Scrapes live catalog, schedule, and pages.
2. Validates data quality.
3. Saves JSON backups to `data/`.
4. Computes SHA-256 hashes against `crawl_cache` in Postgres.
5. Re-embeds and updates ONLY changed or new chunks.

#### 2. Inputs & Outputs
* CLI invocation: `python -m scrapers.pipeline`
* Output: Database synchronized with fresh data; 0 unnecessary embedding API calls.

#### 3. Code Draft (`scrapers/pipeline.py`)
```python
"""Differential ingestion pipeline orchestrator."""
import hashlib
import json
import os
from typing import Dict, List, Tuple
from psycopg2.extras import execute_values
from core.db import get_db, init_db
from core.chunking import chunk_course, chunk_page
from core.embed import embed_batch
from scrapers.catalog import scrape_catalog
from scrapers.schedule import scrape_schedule
from scrapers.pages import scrape_catalog_pages

def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def run_pipeline():
    init_db()
    os.makedirs("data", exist_ok=True)
    
    print("\n--- Starting Scraping Phase ---")
    courses = scrape_catalog()
    pages = scrape_catalog_pages()
    schedule = scrape_schedule()

    # Safety assertions
    assert len(courses) > 100, f"Error: Scraped course count too low ({len(courses)})"
    assert len(pages) > 10, f"Error: Scraped page count too low ({len(pages)})"

    # Save local JSON snapshots
    with open("data/catalog_courses.json", "w", encoding="utf-8") as f:
        json.dump(courses, f, indent=2)
    with open("data/catalog_pages.json", "w", encoding="utf-8") as f:
        json.dump(pages, f, indent=2)
    with open("data/schedule.json", "w", encoding="utf-8") as f:
        json.dump(schedule, f, indent=2)
    print("Saved snapshots to data/ folder.")

    # Convert to Chunks
    all_chunks = [chunk_course(c) for c in courses]
    for p in pages:
        all_chunks.extend(chunk_page(p))
    print(f"Total generated chunks: {len(all_chunks)}")

    # Differential Check via crawl_cache
    print("\n--- Checking for Data Diffs ---")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT source_type, doc_id, content_hash FROM crawl_cache")
            cached = {(r["source_type"], r["doc_id"]): r["content_hash"] for r in cur.fetchall()}

        changed_chunks = []
        for ch in all_chunks:
            key = (ch.source_type, ch.doc_id)
            current_hash = compute_hash(ch.chunk_text)
            if cached.get(key) != current_hash:
                changed_chunks.append((ch, current_hash))

        print(f"Chunks requiring re-embedding / update: {len(changed_chunks)} of {len(all_chunks)}")
        if not changed_chunks:
            print("All content is up-to-date. Zero embeddings needed.")
            return

        # Embed & Update in Batches of 50
        BATCH_SIZE = 50
        with conn.cursor() as cur:
            for i in range(0, len(changed_chunks), BATCH_SIZE):
                batch_items = changed_chunks[i:i + BATCH_SIZE]
                chunks_batch = [item[0] for item in batch_items]
                hashes_batch = [item[1] for item in batch_items]

                # Delete existing rows
                for ch in chunks_batch:
                    cur.execute("DELETE FROM chunks WHERE source_type = %s AND doc_id = %s", (ch.source_type, ch.doc_id))

                # Batch embed
                embeddings = embed_batch([c.chunk_text for c in chunks_batch])

                records = []
                cache_records = []
                for ch, emb, h in zip(chunks_batch, embeddings, hashes_batch):
                    records.append((
                        ch.source_type,
                        ch.source_url,
                        ch.doc_id,
                        ch.title,
                        ch.chunk_text,
                        emb,
                        json.dumps(ch.metadata.model_dump())
                    ))
                    cache_records.append((ch.source_type, ch.doc_id, h))

                execute_values(
                    cur,
                    """
                    INSERT INTO chunks (source_type, source_url, doc_id, title, chunk_text, embedding, metadata)
                    VALUES %s
                    """,
                    records
                )
                execute_values(
                    cur,
                    """
                    INSERT INTO crawl_cache (source_type, doc_id, content_hash)
                    VALUES %s
                    ON CONFLICT (source_type, doc_id) DO UPDATE SET content_hash = EXCLUDED.content_hash, updated_at = now()
                    """,
                    cache_records
                )
                conn.commit()
                print(f"Updated {min(i + BATCH_SIZE, len(changed_chunks))}/{len(changed_chunks)} chunks.")

    print("Pipeline completed successfully.")

if __name__ == "__main__":
    run_pipeline()
```

#### 4. Verification
Run in terminal:
```bash
python -m scrapers.pipeline
```
Verify chunks are inserted and `crawl_cache` records the hashes.

---

### Step 8: Course Code Normalizer & Hybrid RRF Retrieval (`core/course_codes.py`, `core/retrieval.py`)

#### 1. Purpose
Sub-50ms hybrid retrieval:
* Normalizes course codes ("MATH-1A" $\rightarrow$ "MATH 1A").
* Runs GIN-indexed sparse search + HNSW dense vector search.
* Merges rankings with Reciprocal Rank Fusion.

#### 2. Code Draft (`core/course_codes.py`)
```python
"""Course code normalizer."""
import re
from typing import Optional

SUBJECTS = {
    "CIS", "MATH", "EWRT", "CHEM", "PHYS", "BIOL", "ACCT", "ECON",
    "PSYC", "SOC", "COMM", "HIST", "POLI", "ARTS", "MUSI", "ESL",
    "ASTR", "ANTH", "ES", "HART", "HLTH", "HUMI", "ICS", "JOUR"
}

COURSE_PATTERN = re.compile(
    r"\b([A-Za-z]{2,5})[\s\-_]?([0-9]{1,3}[A-Za-z]{0,2})\b",
    re.IGNORECASE
)

def resolve_code(text: str) -> Optional[str]:
    matches = COURSE_PATTERN.findall(text)
    for subj, num in matches:
        canonical_subj = subj.upper()
        if canonical_subj in SUBJECTS:
            return f"{canonical_subj} {num.upper()}"
    return None
```

#### 3. Code Draft (`core/retrieval.py`)
```python
"""Sub-50ms Hybrid RRF retrieval engine."""
from typing import Dict, List
from core.db import get_db
from core.embed import embed_text
from core.course_codes import resolve_code
from core.schemas import SearchResult

def _rrf_fuse(dense: List[dict], sparse: List[dict], k: int = 60) -> List[dict]:
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

def exact_course_lookup(code: str) -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, chunk_text, metadata, source_url
                FROM chunks
                WHERE source_type = 'course' AND metadata->>'code' = %s
                LIMIT 1
                """,
                (code,)
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

#### 4. Verification
```python
from core.retrieval import hybrid_search

results = hybrid_search("Prerequisites for CIS 22A", top_k=3)
assert results[0].meta.get("code") == "CIS 22A"
print("Hybrid search test passed.")
```

---

### Step 9: Formatted Prompt & Async Streaming Engine (`core/chat.py`)

#### 1. Purpose
Enforce clean markdown formatting (bullet points, short paragraphs, bold text, zero hallucinations) and stream tokens asynchronously.

#### 2. Code Draft
```python
"""Streaming Chat pipeline with formatting rules and source citations."""
import os
from typing import AsyncGenerator, List
from openai import AsyncOpenAI
from dotenv import load_dotenv
from core.retrieval import hybrid_search

load_dotenv()

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = """You are the official De Anza College AI Assistant.

RULES:
1. Answer the student's question based ONLY on the provided context below.
2. If the context does NOT contain the answer, politely state: "I don't have that official information in my current records" and direct them to deanza.edu. Do NOT fabricate information.
3. FORMATTING REQUIREMENTS:
   - Use clear markdown with short paragraphs (2-3 sentences max).
   - Use bullet points (*) for lists of requirements, prerequisites, steps, fees, or dates.
   - Use bold text for key terms, course codes, deadlines, and requirements.
   - Separate distinct topics with ### headers when answering multi-part questions.
4. CITATIONS: Always list the relevant official source URLs at the very end under a "### Sources" header.

Example response:
### CIS 22A — Beginning Programming Methodologies in C++
* **Units**: 4.5
* **Department**: Computer Information Systems

### Prerequisites
* **Prerequisite**: CIS 22A eligibility or MATH 114
* **Advisory**: EWRT 1A or ESL 5

### Sources
* https://deanza.elumenapp.com/catalog/course/CIS22A
"""

def build_prompt_context(chunks: list) -> str:
    parts = []
    for idx, c in enumerate(chunks, 1):
        url = c.url or "https://deanza.edu"
        parts.append(f"[Document {idx}] (Source: {url})\n{c.text}")
    return "\n\n---\n\n".join(parts)

async def stream_chat(message: str, history: List[dict] = None) -> AsyncGenerator[str, None]:
    chunks = hybrid_search(message, top_k=5)
    context_text = build_prompt_context(chunks)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        for h in history[-4:]:
            messages.append({"role": h["role"], "content": h["content"]})
            
    messages.append({
        "role": "user",
        "content": f"Context:\n{context_text}\n\nStudent Question: {message}"
    })

    response = await client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=0.0,
        stream=True
    )

    async for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
```

---

### Step 10: FastAPI Server & Minimalist UI (`api_server.py`, `public/index.html`, `public/app.js`)

#### 1. Code Draft (`api_server.py`)
```python
"""Production FastAPI server for De Anza Chatbot."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from core.schemas import ChatRequest, FeedbackRequest
from core.chat import stream_chat
from core.db import get_db

app = FastAPI(title="De Anza AI Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    return {"status": "ok", "db": "connected"}

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    async def event_generator():
        async for token in stream_chat(req.message, [h.model_dump() for h in req.history]):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/feedback")
def submit_feedback(req: FeedbackRequest):
    with get_db() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback (query_text, answer_text, rating, model_used)
                VALUES (%s, %s, %s, %s)
                """,
                (req.query_text, req.answer_text, req.rating, req.model_used)
            )
    return {"status": "recorded"}

app.mount("/", StaticFiles(directory="public", html=True), name="public")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server.py:app", host="0.0.0.0", port=8000, reload=True)
```

#### 2. Code Draft (`public/index.html`)
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>De Anza AI Assistant</title>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    :root {
      --primary: #800000;
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #1e293b;
      --border: #e2e8f0;
    }
    body {
      margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg); color: var(--text); display: flex; flex-direction: column; height: 100vh;
    }
    header {
      background: var(--primary); color: white; padding: 16px 24px; font-size: 1.2rem; font-weight: 600;
    }
    #chat-container {
      flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px;
    }
    .msg {
      max-width: 750px; padding: 14px 18px; border-radius: 10px; line-height: 1.6;
    }
    .msg.user {
      align-self: flex-end; background: var(--primary); color: white; border-bottom-right-radius: 2px;
    }
    .msg.bot {
      align-self: flex-start; background: var(--card-bg); border: 1px solid var(--border); border-bottom-left-radius: 2px;
    }
    .msg.bot ul { padding-left: 20px; margin: 8px 0; }
    .msg.bot li { margin-bottom: 4px; }
    .msg.bot h3 { margin: 12px 0 6px 0; color: var(--primary); font-size: 1.05rem; }
    #input-form {
      padding: 16px 24px; background: white; border-top: 1px solid var(--border); display: flex; gap: 12px;
    }
    #input-box {
      flex: 1; padding: 12px 16px; border: 1px solid var(--border); border-radius: 8px; font-size: 1rem; outline: none;
    }
    #input-box:focus { border-color: var(--primary); }
    button {
      padding: 12px 24px; background: var(--primary); color: white; border: none; border-radius: 8px; font-size: 1rem; cursor: pointer;
    }
    button:disabled { opacity: 0.5; }
  </style>
</head>
<body>
  <header>De Anza AI Student Assistant</header>
  <div id="chat-container">
    <div class="msg bot">Hello! Ask me anything about De Anza courses, prerequisites, registration dates, or campus policies.</div>
  </div>
  <form id="input-form">
    <input id="input-box" type="text" placeholder="e.g. What are the prerequisites for CIS 22A?" autocomplete="off" required />
    <button id="send-btn" type="submit">Send</button>
  </form>
  <script src="/app.js"></script>
</body>
</html>
```

#### 3. Code Draft (`public/app.js`)
```javascript
const chatContainer = document.getElementById("chat-container");
const inputForm = document.getElementById("input-form");
const inputBox = document.getElementById("input-box");
const sendBtn = document.getElementById("send-btn");

let chatHistory = [];

inputForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = inputBox.value.trim();
  if (!query) return;

  appendMessage("user", query);
  inputBox.value = "";
  sendBtn.disabled = true;

  const botDiv = appendMessage("bot", "...");
  let fullAnswer = "";

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: query, history: chatHistory })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split("\n\n");

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.replace("data: ", "");
          if (data === "[DONE]") break;
          fullAnswer += data;
          botDiv.innerHTML = marked.parse(fullAnswer);
          chatContainer.scrollTop = chatContainer.scrollHeight;
        }
      }
    }

    chatHistory.push({ role: "user", content: query });
    chatHistory.push({ role: "assistant", content: fullAnswer });

  } catch (err) {
    botDiv.innerHTML = "<em>Error connecting to assistant. Please try again.</em>";
  } finally {
    sendBtn.disabled = false;
  }
});

function appendMessage(role, text) {
  const msg = document.createElement("div");
  msg.className = `msg ${role}`;
  msg.innerHTML = role === "user" ? text : marked.parse(text);
  chatContainer.appendChild(msg);
  chatContainer.scrollTop = chatContainer.scrollHeight;
  return msg;
}
```

---

### Step 11: Automated GitHub Actions Quarterly Cron (`.github/workflows/quarterly_refresh.yml`)

#### 1. Purpose
Run the scraper and differential embedding pipeline automatically at the start of Fall, Winter, Spring, and Summer quarters.

#### 2. Code Draft
```yaml
name: Quarterly Data Refresh

on:
  schedule:
    # Runs at 00:00 UTC on the 1st of September, January, April, and June
    - cron: '0 0 1 1,4,6,9 *'
  workflow_dispatch: # Allows manual trigger button in GitHub UI

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install Dependencies
        run: |
          pip install -r requirements.txt

      - name: Run Scraper & Differential Ingest
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          python -m scrapers.pipeline

      - name: Commit Updated Data Snapshots
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/
          git diff --quiet && git diff --staged --quiet || (git commit -m "chore(data): auto-update quarterly snapshots" && git push)
```

---

### Step 12: Automated Benchmark & Evaluation (`run_eval.py`)

#### 1. Purpose
Verify accuracy, zero-hallucination rate, and response latency against the 150-question golden set.

#### 2. Code Draft
```python
"""Evaluation runner against golden Q&A dataset."""
import json
import time
from core.chat import hybrid_search, build_prompt_context, SYSTEM_PROMPT
from openai import OpenAI

client = OpenAI()

def run_eval():
    with open("data/golden_set.json", "r", encoding="utf-8") as f:
        golden = json.load(f)

    total = len(golden)
    correct = 0
    total_time = 0.0

    print(f"Running evaluation on {total} questions...\n")

    for i, item in enumerate(golden, 1):
        q = item["question"]
        expected = item.get("answer") or item.get("ground_truth", "")

        t0 = time.time()
        chunks = hybrid_search(q, top_k=5)
        ctx = build_prompt_context(chunks)

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{ctx}\n\nQuestion: {q}"}
            ],
            temperature=0.0
        )
        latency = time.time() - t0
        total_time += latency
        answer = resp.choices[0].message.content

        judge = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a strict grading judge. Grade if the actual answer accurately matches the expected answer facts. Reply with ONLY 'YES' or 'NO'."},
                {"role": "user", "content": f"Question: {q}\nExpected: {expected}\nActual: {answer}"}
            ],
            temperature=0.0
        )
        is_correct = "YES" in judge.choices[0].message.content.strip().upper()
        if is_correct:
            correct += 1

        print(f"[{i}/{total}] {'[PASS]' if is_correct else '[FAIL]'} ({latency:.2f}s) Q: {q[:50]}...")

    acc = (correct / total) * 100
    avg_latency = total_time / total
    print(f"\n=============================")
    print(f"Benchmark Accuracy: {acc:.1f}% ({correct}/{total})")
    print(f"Average Latency:    {avg_latency:.2f}s")
    print(f"=============================")

if __name__ == "__main__":
    run_eval()
```

#### 3. Verification
```bash
python run_eval.py
```
Verify benchmark achieves $\ge 90\%$ accuracy and average latency $\le 1.0\text{s}$.
