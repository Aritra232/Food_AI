from pinecone import Pinecone
from dotenv import load_dotenv

import os
import json

load_dotenv()

pc = Pinecone(
    api_key=os.getenv("PINECONE_API_KEY")
)

INDEX_NAME = "food-ai-index"


if INDEX_NAME not in pc.list_indexes().names():

    pc.create_index(
        name=INDEX_NAME,
        dimension=1536,
        metric="cosine",
        spec={
            "serverless": {
                "cloud": "aws",
                "region": "us-east-1"
            }
        }
    )

index = pc.Index(INDEX_NAME)


def _ensure_index():
    global index
    try:
        index.describe_index_stats()
    except Exception:
        # try to recreate
        if INDEX_NAME not in pc.list_indexes().names():
            pc.create_index(
                name=INDEX_NAME,
                dimension=1536,
                metric="cosine"
            )
        index = pc.Index(INDEX_NAME)


def _clean_metadata_value(value):
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, list):
        cleaned = []
        for item in value:
            if isinstance(item, (str, int, float, bool)):
                cleaned.append(str(item) if not isinstance(item, bool) else item)
        return cleaned

    if isinstance(value, dict):
        return json.dumps(value)

    return str(value)


def _sanitize_metadata(metadata):
    sanitized = {}
    for key, value in (metadata or {}).items():
        cleaned = _clean_metadata_value(value)
        if cleaned is not None:
            sanitized[key] = cleaned
    return sanitized


def upsert_vectors(vectors):
    """Upsert a list of tuples: (id, vector, metadata)"""
    if not vectors:
        return None

    items = []
    for vid, vec, meta in vectors:
        items.append({
            "id": str(vid),
            "values": vec,
            "metadata": _sanitize_metadata(meta)
        })

    index.upsert(vectors=items)


def query_vector(vector, top_k=5, filter=None):
    try:
        res = index.query(vector=vector, top_k=top_k, include_metadata=True, filter=filter)
        return res
    except Exception as e:
        # try alternative args
        return index.query(queries=[vector], top_k=top_k, include_metadata=True, filter=filter)
