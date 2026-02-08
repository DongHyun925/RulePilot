from __future__ import annotations
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from rag.retriever import get_retriever


SYSTEM = """너는 주식/ETF 왕초보(중학생도 이해할 수준)를 가르치는 튜터다.

규칙:
- 아주 쉬운 말로 설명한다.
- 한 문장은 짧게 쓴다.
- 비유를 꼭 넣는다.
- 어려운 단어는 바로 풀이한다.

⭐ 이모티콘 규칙(반드시 지켜):
- 각 항목 제목 앞에는 아래 이모티콘을 붙인다.
- 이모티콘은 항상 같은 것을 쓴다.

출력 형식(반드시 지켜):
📌 한줄 정의:
🧠 쉬운 예시:
❓ 왜 중요한가:
⚠️ 주의할 점:
📝 3줄 요약:
"""


def answer_term_question(question: str) -> str:
    load_dotenv()
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)

    retriever = get_retriever(k=4)
    docs = retriever.invoke(question)
    context = "\n\n---\n\n".join([f"[source={d.metadata.get('source','')}] {d.page_content}" for d in docs])

    prompt = f"""{SYSTEM}

[질문]
{question}

[RAG 컨텍스트]
{context}
"""
    resp = llm.invoke(prompt)
    return resp.content
