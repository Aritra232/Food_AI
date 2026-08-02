from openai import OpenAI
from dotenv import load_dotenv

import os

load_dotenv()

try:
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY")
    )
except Exception:
    client = None


def generate_embedding(text):
    if client is None:
        return [0.0] * 1536

    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )

    embedding = response.data[0].embedding

    return embedding
