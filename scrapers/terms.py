"""Automatically look for academic term and quarter"""
import datetime
import re 
from scrapers.client import get_session
ELUMEN_API = "https://api-prod.elumenapp.com"
TENANT = "deanza.elumenapp.com"

def get_active_catalog_term():
    """Fetch the latest catalog term from the ELUMEN route"""
    session = get_session()
    try:
        resp = session.get(
            f"{ELUMEN_API}/catalog/sites/publish", 
            params = {"tenant": TENANT}, 
            timeout = 15,
        )

        if resp.status_code == 200:
            html = resp.json().get("html", "")
            # Find patterns like 2025-2026
            terms = re.findall(r"\b(20\d{2}-20\d{2})\b", html)
            if terms:
                return sorted(list(set(terms)))[-1]
    except Exception as e:
        print (f"Warning: Failed to fetch active term from ELUMEN: {e}")

    #Fall back to current year calculation
    now = datetime.datetime.now()
    year = now.year
    return f"{year-1}-{year}"

def get_current_quarter(): 
    month = datetime.datetime.now().month
    if month in (9, 10, 11, 12):
        return "fall"
    elif month in (1, 2, 3): 
        return "winter"
    elif month in (4,5,6):
        return "spring"
    else:
        return "summer"
