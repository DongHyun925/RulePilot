from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter


SUPPORTED_EXTS = {".md", ".txt"}  # 필요하면 ".log" 같은 것도 추가 가능


def _read_text_file(p: Path) -> str:
    # UTF-8 우선, 실패 시 cp949(한국 윈도우에서 자주 나옴)로 fallback
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="cp949", errors="replace")


def load_text_docs(docs_dir: Path, recursive: bool = True) -> List[Document]:
    if not docs_dir.exists():
        raise RuntimeError(f"문서 폴더가 없습니다: {docs_dir}")

    pattern = "**/*" if recursive else "*"
    files = [p for p in docs_dir.glob(pattern) if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]

    docs: List[Document] = []
    for p in sorted(files):
        text = _read_text_file(p).strip()
        if not text:
            continue
        docs.append(
            Document(
                page_content=text,
                metadata={
                    "source": str(p.relative_to(docs_dir)).replace("\\", "/"),
                    "ext": p.suffix.lower(),
                },
            )
        )
    return docs


def ensure_openai_key() -> None:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY 환경변수가 없습니다.\n"
            "PowerShell에서 예:\n"
            '  $env:OPENAI_API_KEY="sk-..."\n'
            "또는 .env 파일에 OPENAI_API_KEY=sk-... 를 추가하세요."
        )


def build_index(
    docs_dir: Path,
    store_dir: Path,
    chunk_size: int,
    chunk_overlap: int,
    recursive: bool,
    model: str,
) -> None:
    store_dir.mkdir(parents=True, exist_ok=True)

    raw_docs = load_text_docs(docs_dir, recursive=recursive)
    if not raw_docs:
        raise RuntimeError(
            f"{docs_dir}에 인덱싱할 문서가 없습니다. (.md/.txt)\n"
            "예: rag_docs/intro.md 같은 파일을 최소 1개 넣어주세요."
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_documents(raw_docs)

    # 최신 LangChain 표준: OpenAIEmbeddings(model=...)
    embeddings = OpenAIEmbeddings(model=model)

    # 벡터스토어 생성
    vs = FAISS.from_documents(chunks, embeddings)

    # 저장
    vs.save_local(str(store_dir))

    print("[OK] Indexed documents:", len(raw_docs))
    print("[OK] Total chunks:", len(chunks))
    print("[OK] Vector store saved to:", store_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build FAISS vector store from rag_docs.")
    parser.add_argument("--docs", default=None, help="Docs directory (default: <project_root>/rag_docs)")
    parser.add_argument("--out", default=None, help="Output store dir (default: <project_root>/data/vector_store)")
    parser.add_argument("--chunk-size", type=int, default=600)
    parser.add_argument("--chunk-overlap", type=int, default=100)
    parser.add_argument("--no-recursive", action="store_true", help="Do not search subfolders in rag_docs")
    parser.add_argument(
        "--emb-model",
        default="text-embedding-3-small",
        help="OpenAI embedding model (default: text-embedding-3-small)",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()  # .env 지원
    ensure_openai_key()

    args = parse_args()

    project_root = Path(__file__).resolve().parents[1]
    docs_dir = Path(args.docs) if args.docs else (project_root / "rag_docs")
    store_dir = Path(args.out) if args.out else (project_root / "data" / "vector_store")

    build_index(
        docs_dir=docs_dir,
        store_dir=store_dir,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        recursive=not args.no_recursive,
        model=args.emb_model,
    )


if __name__ == "__main__":
    main()
