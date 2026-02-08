from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from state_schema import Policy, MonthSignal, PortfolioPlan


@dataclass
class Decision:
    action: str          # "WAIT" | "BUY_SCHEDULED"
    reason: str
    next_step: str


def decide_now(
    user_text: str,
    policy: Union[Policy, Dict[str, Any]],
    signal: Union[MonthSignal, Dict[str, Any]],
    plan: Union[PortfolioPlan, Dict[str, Any], None],
) -> Decision:
    """
    '지금 사도 돼?' 같은 즉흥/충동 질문에 대해:
    - 정책/신호/계획을 바탕으로 WAIT vs BUY_SCHEDULED를 반환
    - policy/signal/plan이 dict로 들어와도 자동으로 dataclass로 변환(안전)
    """

    # ✅ dict -> dataclass 변환(그래프에서 어떤 형태로 넘겨도 안전)
    if isinstance(policy, dict):
        policy = Policy(**policy)
    if isinstance(signal, dict):
        signal = MonthSignal(**signal)
    if plan is None:
        plan = PortfolioPlan()
    elif isinstance(plan, dict):
        plan = PortfolioPlan(**plan)

    t = (user_text or "").strip()

    # 즉흥/충동 마커: 지금/추가매수/급등락/불안 등
    impulsive_markers = ["지금", "더", "추가", "급등", "급락", "불안", "무서", "조급", "몰빵", "손절", "익절"]
    is_impulsive = any(m in t for m in impulsive_markers)

    # 정책 문구 안전 처리
    ban_rule = "정해둔 날짜 외 추가매수 금지"
    if getattr(policy, "ban_rules", None):
        if len(policy.ban_rules) > 0 and policy.ban_rules[0]:
            ban_rule = policy.ban_rules[0]

    # 계획 금액(없을 수도 있으니 방어)
    equity_amt = getattr(plan, "equity_amount_krw", None)
    if equity_amt is None:
        equity_amt = 0

    if is_impulsive:
        return Decision(
            action="WAIT",
            reason=(
                f"정책상 즉흥 매수는 금지입니다. ({ban_rule}) "
                f"이번 달 비중은 이미 모델로 결정됨: 주식 {signal.equity_weight:.0%}."
            ),
            next_step=(
                "다음 정기매수일에 계획된 금액만 매수하세요.\n"
                "원하면: (1) 지금 사고 싶은 이유를 1문장으로 적고\n"
                "(2) 그 이유가 정책을 위반하는지(정해둔 날짜/예산/규칙) 체크해보세요."
            ),
        )

    # 그 외에는 정기매수만 허용
    return Decision(
        action="BUY_SCHEDULED",
        reason=(
            f"정기매수 루틴을 따릅니다. "
            f"이번 달 주식 비중 {signal.equity_weight:.0%}, 주식 바스켓 {equity_amt:,}원."
        ),
        next_step="정해진 날짜에 계획된 금액만 매수하고, 그 외에는 추가 행동을 하지 않습니다.",
    )
