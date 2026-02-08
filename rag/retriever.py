from __future__ import annotations
from pathlib import Path
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS


def get_retriever(k: int = 4):
    load_dotenv()
    project_root = Path(__file__).resolve().parents[1]
    store_dir = project_root / "data" / "vector_store"

    embeddings = OpenAIEmbeddings()
    vs = FAISS.load_local(str(store_dir), embeddings, allow_dangerous_deserialization=True)
    return vs.as_retriever(search_kwargs={"k": k})
