"""Index guidance PDF documents from SharePoint into pgvector."""

import os
import sys
import logging
from langchain_openai import AzureOpenAIEmbeddings
from langchain_postgres.vectorstores import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader

logging.basicConfig(level=logging.INFO)


def _pg_conn() -> str:
    pg = os.environ["PG_CONNECTION_STRING"]
    parts = dict(p.split("=", 1) for p in pg.split() if "=" in p)
    return f"postgresql+psycopg://{parts['user']}:{parts['password']}@{parts['host']}:{parts['port']}/{parts['dbname']}?sslmode={parts.get('sslmode', 'require')}"


def index_pdf(pdf_path: str):
    """Load a PDF, chunk it, embed, and store in pgvector."""
    logging.info(f"Indexing: {pdf_path}")

    loader = PyPDFLoader(pdf_path)
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = splitter.split_documents(docs)
    logging.info(f"  {len(chunks)} chunks from {len(docs)} pages")

    embeddings = AzureOpenAIEmbeddings(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        azure_deployment=os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
        api_version="2024-06-01",
    )

    vectorstore = PGVector(
        connection=_pg_conn(),
        embeddings=embeddings,
        collection_name="guidance_docs",
    )

    vectorstore.add_documents(chunks)
    logging.info(f"  ✅ Indexed {len(chunks)} chunks into guidance_docs")


if __name__ == "__main__":
    pdf_dir = sys.argv[1] if len(sys.argv) > 1 else "docs/"
    if os.path.isfile(pdf_dir):
        index_pdf(pdf_dir)
    else:
        for f in os.listdir(pdf_dir):
            if f.endswith(".pdf"):
                index_pdf(os.path.join(pdf_dir, f))
