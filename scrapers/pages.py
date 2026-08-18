"""Policy and College Information Pages Parser with fallback."""
import json
import os
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from scrapers.client import get_session
from scrapers.terms import get_active_catalog_term

API_URL = "https://api-prod.elumenapp.com"
TENANT = "deanza.elumenapp.com"
LOCAL_PAGES_FILE = "catalog_pages_full.json"

def scrape_catalog_pages() -> List[Dict[str, Any]]:
    term = get_active_catalog_term()
    session = get_session()
    print(f"Scraping static policy pages for term {term}...")

    try:
        resp = session.get(
            f"{API_URL}/catalog/sites/publish/{term}", 
            params={"tenant": TENANT},
            timeout=15
        )
        if resp.status_code == 200:
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
                        for tag in body_soup(["script", "style"]):
                            tag.decompose()
                        text = body_soup.get_text("\n", strip=True)
                        title = slug.replace("-", " ").title()
                        pages.append({
                            "slug": slug,
                            "title": title,
                            "url": f"https://deanza.elumenapp.com/catalog/{term}/{slug}",
                            "content": text,
                        })
                except Exception as e:
                    print(f"Error fetching page {slug}: {e}")
            if pages:
                return pages
    except Exception as e:
        print(f"Live pages API unavailable ({e}). Falling back to local dataset...")

    # Fallback to local snapshot
    if os.path.exists(LOCAL_PAGES_FILE):
        with open(LOCAL_PAGES_FILE, "r", encoding="utf-8") as f:
            pages = json.load(f)
            print(f"Loaded {len(pages)} pages from {LOCAL_PAGES_FILE}.")
            return pages

    return []