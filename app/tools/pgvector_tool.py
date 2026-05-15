"""pgvector tool - vector search over call transcripts and guidance documents."""

import os
import logging
from langchain_openai import AzureOpenAIEmbeddings
from langchain_postgres.vectorstores import PGVector

_embeddings = None
_transcripts_store = None
_guidance_store = None


def _pg_conn() -> str:
    pg = os.environ["PG_CONNECTION_STRING"]
    parts = dict(p.split("=", 1) for p in pg.split() if "=" in p)
    return f"postgresql+psycopg://{parts['user']}:{parts['password']}@{parts['host']}:{parts['port']}/{parts['dbname']}?sslmode={parts.get('sslmode', 'require')}"


def _get_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = AzureOpenAIEmbeddings(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_KEY"],
            azure_deployment=os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
            api_version="2024-06-01",
        )
    return _embeddings


def _get_transcripts_store():
    global _transcripts_store
    if _transcripts_store is None:
        _transcripts_store = PGVector(
            connection=_pg_conn(),
            embeddings=_get_embeddings(),
            collection_name="call_transcripts",
        )
    return _transcripts_store


def _get_guidance_store():
    global _guidance_store
    if _guidance_store is None:
        _guidance_store = PGVector(
            connection=_pg_conn(),
            embeddings=_get_embeddings(),
            collection_name="guidance_docs",
        )
    return _guidance_store


def search_transcripts(query: str, k: int = 5) -> str:
    """Search call transcripts by semantic similarity."""
    try:
        docs = _get_transcripts_store().similarity_search(query, k=k)
        return "\n\n".join(d.page_content for d in docs)
    except Exception as e:
        logging.warning(f"Transcript search failed: {e}")
        return ""


def search_guidance(query: str, k: int = 4) -> str:
    """Search guidance documents by semantic similarity."""
    try:
        docs = _get_guidance_store().similarity_search(query, k=k)
        return "\n\n".join(d.page_content for d in docs)
    except Exception as e:
        logging.warning(f"Guidance search failed: {e}")
        return ""
