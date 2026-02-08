from __future__ import annotations
from typing import Dict, Any, List

def build_policy_from_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    risk = profile.get("risk_level", "neutral")
    emergency_ok = bool(profile.get("emergency_fund_ok", True))

    ban_rules: List[str] = ["뉴스 보고 즉흥매수 금지", "레버리지/빚투 금지"]

    # 초보 안전장치(옵션)
    if risk == "conservative":
        ban_rules.append("단기 매매(단타) 금지")
    if not emergency_ok:
        ban_rules.append("비상금 준비 전에는 공격적 비중 확대 금지")

    buy_rule = "매달 1회, 정해진 날짜에 ‘계획된 금액’만 매수"
    rebalance_rule = "분기 1회(3개월에 1번) 비중 점검"

    policy = {
        "buy_rule": buy_rule,
        "rebalance_rule": rebalance_rule,
        "ban_rules": ban_rules,
        "notes": {
            "risk_level": risk,
            "emergency_fund_ok": emergency_ok,
        },
    }
    return policy

def policy_to_text(policy: Dict[str, Any]) -> str:
    bans = "\n".join([f"  - 🚫 {x}" for x in policy.get("ban_rules", [])])
    return (
        "📜 내 투자 규칙(Policy)\n"
        f"⏰ 매수 규칙: {policy.get('buy_rule')}\n"
        f"🔁 점검 규칙: {policy.get('rebalance_rule')}\n"
        "🧱 금지 규칙:\n"
        f"{bans if bans else '  - (없음)'}\n"
    )
