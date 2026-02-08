from __future__ import annotations

from data.db import load_active_profile
from managers.history_manager import fetch_last_month_plan, fetch_recent_plans


def node_history_last_month(state):
    user_id = state["user_id"]
    profile_id, _ = load_active_profile(user_id)

    yyyymm, plan = fetch_last_month_plan(user_id, profile_id)

    if not plan:
        state["output_text"] = f"📭 {yyyymm} 기록이 없어요. 이번 달 계획을 먼저 만들면 자동으로 쌓여요."
        return state

    state["output_text"] = (
        f"🗓️ 지난달({yyyymm}) 투자 계획\n\n"
        f"💰 주식: {plan.get('equity_amount_krw', 0):,}원\n"
        f"🛡️ 안전자산: {plan.get('safe_amount_krw', 0):,}원\n"
        f"📌 메모: 지난달 기록은 저장된 계획 기준이에요."
    )
    return state


def node_history_3m(state):
    user_id = state["user_id"]
    profile_id, _ = load_active_profile(user_id)

    items = fetch_recent_plans(user_id, profile_id, limit=3)

    if not items:
        state["output_text"] = "📭 최근 기록이 없어요. '이번 달 얼마씩 사야 해?'로 시작하면 기록이 쌓여요."
        return state

    lines = ["📈 최근 3개월 투자 요약"]
    for it in items:
        yyyymm = it["yyyymm"]
        p = it["plan"]
        lines.append(f"- {yyyymm}: 주식 {p.get('equity_amount_krw', 0):,}원 / 안전자산 {p.get('safe_amount_krw', 0):,}원")

    lines.append("\n원하면: '3개월 중 주식 비중이 가장 높았던 달은?' 같은 질문도 만들 수 있어.")
    state["output_text"] = "\n".join(lines)
    return state
