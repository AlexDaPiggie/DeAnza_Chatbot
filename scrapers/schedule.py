"""BeautifulSoup Class Schedule Parser."""
import json
import os
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from scrapers.client import get_session

SCHEDULE_BASE = "https://mobile.deanza.edu/schedule"
PAGES = ["online-classes.html", "gen-ed-classes.html", "late-start.html"]
LOCAL_SCHEDULE_FILE = "schedule_summer2026.json"

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
                        "sec": sec,
                        "seats": seats,
                        "title": title.split("View Footnote")[0].strip(),
                        "days": days,
                        "times": times,
                        "instructor": instructor,
                        "loc": loc,
                        "source_url": url,
                    })
        except Exception as e: 
            print(f"Error scraping schedule page {page}: {e}")

    if not sections and os.path.exists(LOCAL_SCHEDULE_FILE):
        print(f"Loading local schedule from {LOCAL_SCHEDULE_FILE}...")
        with open(LOCAL_SCHEDULE_FILE, "r", encoding="utf-8") as f:
            sections = json.load(f)

    print(f"Total schedule sections scraped: {len(sections)}")
    return sections