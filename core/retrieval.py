from typing import Dict, List, Optional
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

def exact_course_lookup(code: str) -> Optional[dict]:
    """Look up exact course in the database (handles 'CIS 22A' and 'CIS D022A')."""
    import re
    norm_code = re.sub(r'([A-Za-z]+)\s*D0*(\d+[A-Za-z]*)', r'\1 \2', code).strip()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, chunk_text, metadata, source_url 
                FROM chunks 
                WHERE source_type = 'course' AND (
                    metadata->>'code' = %s OR
                    metadata->>'code' = %s OR
                    metadata->'extra'->>'code' = %s OR
                    doc_id = %s OR
                    doc_id = %s
                )
                ORDER BY id LIMIT 1
                """,
                (
                    code,
                    norm_code,
                    code,
                    code.lower().replace(" ", "-"),
                    norm_code.lower().replace(" ", "-"),
                )
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "text": row["chunk_text"],
                    "meta": row["metadata"],
                    "url": row["source_url"],
                    "score": 1.0,
                }
    return None

def dense_search(
    query_vec: List[float],
    limit: int = 30,
):
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

def sparse_search(
    query: str,
    limit: int = 30
):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, chunk_text, metadata, source_url
                FROM chunks
                WHERE tsv@@ plainto_tsquery('english', %s)
                ORDER BY ts_rank_cd(tsv, plainto_tsquery('english', %s)) DESC

                LIMIT %s
                """,
                (query, query, limit)
            )
            return [
                {
                    "id": r["id"], 
                    "text": r["chunk_text"],
                    "meta": r["metadata"],
                    "url": r["source_url"]
                }
                for r in cur.fetchall()
            ]

def hybrid_search(
    query: str,
    top_k: int = 5,
):
    query_vec = embed_text(query)
    dense_results = dense_search(query_vec, limit = 30)
    sparse_results = sparse_search(query, limit = 30)
    fused = _rrf_fuse(dense_results, sparse_results)

    code = resolve_code(query)
    if code:
        exact = exact_course_lookup(code)
        if exact:
            fused = [r for r in fused if r["id"] != exact["id"]]
            fused.insert(0, exact)

    return [
        SearchResult(
            id = r["id"],
            text = r["text"],
            meta = r.get("meta") or {},
            url = r.get("url"),
            score = r.get("score", 0.0)
        )
        for r in fused[:top_k]
    ]