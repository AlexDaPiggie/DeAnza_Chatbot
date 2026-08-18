import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

USER_AGENT = "DeAnza-AI-bot/1.0 (Educational Assistant; contact: student-admin@deanza.edu)"
def get_session():
    session = requests.Session()
    retry_strategy = Retry(
        total = 3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    session.headers.update({'User-Agent': USER_AGENT})
    return session