"""Scraper for official student service pages, calendars, and policies on deanza.edu."""
import os
import re
import subprocess
from typing import Dict, List
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Curated list of high-value student services and operational hubs on deanza.edu
SEED_URLS = [
    # Academic Calendar & Deadlines
    "https://www.deanza.edu/calendar/",
    "https://www.deanza.edu/calendar/final-exams.html",
    
    # Registration & Admissions
    "https://www.deanza.edu/apply-and-register/",
    "https://www.deanza.edu/admissions/",
    "https://www.deanza.edu/admissions/residency.html",
    "https://www.deanza.edu/assessment/",

    # Tuition, Fees, Cashier & Parking
    "https://www.deanza.edu/cashier/fees.html",
    "https://www.deanza.edu/cashier/refunds.html",
    "https://www.deanza.edu/cashier/payment-methods.html",
    "https://www.deanza.edu/parking/",

    # Financial Aid & De Anza Promise
    "https://www.deanza.edu/financialaid/",
    "https://www.deanza.edu/financialaid/types.html",
    "https://www.deanza.edu/financialaid/apply.html",
    "https://www.deanza.edu/promise/",

    # Counseling, Transfer & Articulation
    "https://www.deanza.edu/counseling/",
    "https://www.deanza.edu/counseling/career/",
    "https://www.deanza.edu/transfercenter/",
    "https://www.deanza.edu/articulation/",
    "https://www.deanza.edu/academics/degrees-and-certificates.html",

    # International Student Programs (ISP)
    "https://www.deanza.edu/international/",
    "https://www.deanza.edu/international/future-students/",

    # Academic Support & Student Services
    "https://www.deanza.edu/dsps/",
    "https://www.deanza.edu/studentsuccess/",
    "https://www.deanza.edu/healthservices/",
    "https://www.deanza.edu/resources/food-pantry.html",

    # Academic Policies & Standards
    "https://www.deanza.edu/policies/",
    "https://www.deanza.edu/policies/probation.html",
]


def fetch_page_html(url: str) -> str:
    """Fetch raw HTML using curl.exe with browser headers to bypass Cloudflare bot checks."""
    cmd = [
        "curl.exe",
        "-s",
        "-L",
        "--max-time", "12",
        url,
        "-H", f"User-Agent: {USER_AGENT}",
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H", "Accept-Language: en-US,en;q=0.9",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        return res.stdout or ""
    except Exception as e:
        print(f"Warning: Failed to fetch {url}: {e}")
        return ""


def clean_page_content(url: str, html: str) -> Dict[str, str] | None:
    """Extract clean title and body text from deanza.edu CMS HTML."""
    if not html or "Attention Required! | Cloudflare" in html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # Extract title
    raw_title = soup.title.string.strip() if soup.title else ""
    title = raw_title.replace(" - De Anza College", "").replace("De Anza College - ", "").strip()
    if not title or title == "404 File Not Found":
        return None

    # Remove script, style, nav, and footer tags
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
        tag.decompose()

    # Find primary content container in OmniUpdate CMS
    content_div = (
        soup.find("div", class_="user-editable") or
        soup.find("div", class_="container user-editable") or
        soup.find("div", id="main-content") or
        soup.find("main") or
        soup.body
    )

    if not content_div:
        return None

    text = content_div.get_text(separator="\n", strip=True)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if len(text) < 100:
        return None

    slug = url.replace("https://www.deanza.edu/", "").rstrip("/").replace("/", "-") or "home"

    return {
        "url": url,
        "title": title,
        "slug": slug,
        "text": f"# {title}\nSource: {url}\n\n{text}"
    }


def scrape_deanza_web() -> List[Dict[str, str]]:
    """Scrape all curated student service and calendar hubs from deanza.edu."""
    print("Scraping official deanza.edu student services & calendar hubs...")
    pages = []
    for url in SEED_URLS:
        html = fetch_page_html(url)
        page = clean_page_content(url, html)
        if page:
            pages.append(page)
            print(f"  + Scraped: {page['title']} ({url})")
        else:
            print(f"  - Skipped/Unavailable: {url}")

    print(f"Total live deanza.edu pages scraped: {len(pages)}")
    return pages


if __name__ == "__main__":
    results = scrape_deanza_web()
    print(f"\nSuccessfully scraped {len(results)} pages from deanza.edu.")
