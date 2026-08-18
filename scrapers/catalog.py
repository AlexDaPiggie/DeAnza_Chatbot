"""Scraper that fetches catalog courses with local snapshot fallback."""
import concurrent.futures as cf
import json
import os
from typing import List, Dict, Any
from scrapers.client import get_session
from scrapers.terms import get_active_catalog_term

API_URL = "https://api-prod.elumenapp.com"
TENANT = "deanza.elumenapp.com"
LOCAL_CATALOG_FILE = "catalog_courses_full.json"

def fetch_course_detail(session, term: str, course_id: str):
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

    # 1/ Try live scraping
    try:
        list_url = f"{API_URL}/catalog/sites/publish/courses/{term}"
        resp = session.get(
            list_url, 
            params={"tenant": TENANT},
            timeout=15
        )
        resp.raise_for_status()
        course_items = resp.json().get("courses", [])
        
        if course_items:
            print(f"Found {len(course_items)} catalog courses. Fetching details...")
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
            if courses:
                print(f"Successfully fetched {len(courses)} courses from API.")
                return courses
    except Exception as e:
        print(f"Live catalog API unavailable ({e}). Falling back to local dataset...")

    # 2/ Fallback to local snapshot
    if os.path.exists(LOCAL_CATALOG_FILE):
        with open(LOCAL_CATALOG_FILE, "r", encoding="utf-8") as f:
            courses = json.load(f)
            print(f"Loaded {len(courses)} courses from {LOCAL_CATALOG_FILE}.")
            return courses

    return []