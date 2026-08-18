"""Fast Embeddings using OpenAI API"""
import os 
from typing import List
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True) #override the local env variable with the global env variable

client = OpenAI (api_key=os.getenv("OPENAI_API_KEY"))
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

def embed_text(text: str):
    """This function is to embed a piece of text into 1,536 numbers vector"""
    clean_text = text.replace ("\n", " ").strip()
    resp = client.embeddings.create(
        input = [clean_text],
        model = EMBED_MODEL,
    )
    return resp.data[0].embedding

def embed_batch(texts: List[str]):
    """This function is to embed huge chunk of text, such as thousands lines of information from scraped data
    Truncate each text to maximnum 250000 chars"""

    clean_texts = [t.replace("\n", " ").strip()[:25000] for t in texts if t.strip()]
    if not clean_texts:
        return []
    resp = client.embeddings.create(
        input = clean_texts,
        model = EMBED_MODEL,
    )
    return [d.embedding for d in resp.data]