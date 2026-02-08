from __future__ import annotations
from typing import Dict, Any

# 온보딩에서 채워야 할 필드(순서대로 질문)
FIELDS = [
    "monthly_budget_krw",
    "horizon_months",
    "risk_level",
    "emergency_fund_ok",
    "user_level",  # ✅ 추가: beginner/intermediate/advanced
]

# 각 필드별 질문 텍스트
QUESTIONS = {
    "monthly_budget_krw": "🧾 프로필을 먼저 만들게요!\n💰 매달 투자할 수 있는 금액이 얼마야? (예: 50000)",
    "horizon_months": "⏳ 투자 기간은 몇 개월로 볼까? (예: 120 = 10년)",
    "risk_level": "🎚️ 위험 감수 성향은?\n1) 보수적  2) 중립  3) 공격적\n(숫자로 답해도 돼)",
    "emergency_fund_ok": "🛟 비상금(생활비 몇 달치)이 따로 준비돼 있어? (예/아니오)",
    "user_level": "🧾 마지막 질문!\n당신의 투자 경험 레벨은?\n1) beginner(완전 초보)\n2) intermediate(기본은 앎)\n3) advanced(지표/수치/가정까지 OK)\n(숫자 또는 단어로 답해도 돼)",
}


def _find_next_field(profile: Dict[str, Any]) -> str | None:
    """profile에서 아직 채워지지 않은 다음 필드를 반환"""
    for f in FIELDS:
        if profile.get(f) in [None, ""]:
            return f
    return None


def ask_next_question(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    아직 프로필이 완성되지 않았다면 다음 질문을 output_text에 넣어 반환.
    이미 완성되었다면 완료 메시지를 반환.
    """
    profile = state.get("profile", {})
    nxt = _find_next_field(profile)

    if nxt is None:
        state["profile_complete"] = True
        state["pending_intake_field"] = ""
        state["output_text"] = "✅ 프로필 작성 완료! 이제 포트폴리오/루틴을 만들 수 있어요."
        return state

    state["pending_intake_field"] = nxt
    state["output_text"] = QUESTIONS[nxt]
    return state


def apply_intake_answer(state: Dict[str, Any], user_text: str) -> Dict[str, Any]:
    """
    pending_intake_field에 해당하는 질문의 답을 profile에 반영하고,
    이어서 다음 질문(또는 완료 메시지)을 output_text로 반환.
    """
    profile = state.get("profile", {})
    field = state.get("pending_intake_field")
    t = (user_text or "").strip().lower()

    if field == "monthly_budget_krw":
        profile["monthly_budget_krw"] = int(t.replace(",", ""))

    elif field == "horizon_months":
        profile["horizon_months"] = int(t.replace(",", ""))

    elif field == "risk_level":
        if t in ["1", "보수", "보수적", "conservative"]:
            profile["risk_level"] = "conservative"
        elif t in ["2", "중립", "neutral"]:
            profile["risk_level"] = "neutral"
        elif t in ["3", "공격", "공격적", "aggressive"]:
            profile["risk_level"] = "aggressive"
        else:
            profile["risk_level"] = "neutral"  # default

    elif field == "emergency_fund_ok":
        if t in ["예", "네", "y", "yes", "있어", "있습니다"]:
            profile["emergency_fund_ok"] = True
        else:
            profile["emergency_fund_ok"] = False

    elif field == "user_level":
        if t in ["1", "beginner", "초보", "완전초보"]:
            profile["user_level"] = "beginner"
        elif t in ["2", "intermediate", "중급", "보통"]:
            profile["user_level"] = "intermediate"
        elif t in ["3", "advanced", "고급", "숙련"]:
            profile["user_level"] = "advanced"
        else:
            profile["user_level"] = "beginner"  # default

    # 반영 저장
    state["profile"] = profile

    # 다음 질문/완료 처리
    nxt = _find_next_field(profile)
    if nxt is None:
        state["profile_complete"] = True
        state["pending_intake_field"] = ""
        state["output_text"] = "✅ 프로필 작성 완료! 이제 포트폴리오/루틴을 만들 수 있어요."
    else:
        state["profile_complete"] = False
        state["pending_intake_field"] = nxt
        state["output_text"] = QUESTIONS[nxt]

    return state
