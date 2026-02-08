from typing import Dict, Any

def format_allocation_output(base_output: Dict[str, Any], user_level: str) -> str:
    """
    user_level에 따라 같은 정보도 다르게 표현
    base_output에는 allocate 노드에서 만든 raw 데이터가 들어옴
    """

    plan = base_output["plan"]
    signal = base_output["signal"]
    orders = base_output["orders"]
    reason_text = base_output["reason_text"]

    equity = orders["equity"]
    safe = orders["safe"]

    if user_level == "advanced":
        return f"""
📊 [Advanced View] 이번 달 투자 계획

💰 비중 요약
- 주식 비중: {signal.equity_weight:.1%}
- 안전자산 비중: {signal.safe_weight:.1%}

🧮 주문 세부
- {equity['ticker']} : {equity['shares']:.4f}주 (${equity['price_usd']:.2f})
- {safe['ticker']} : {safe['shares']:.4f}주 (${safe['price_usd']:.2f})

📈 모델 근거
{reason_text}

⚙️ 해석
- 모델이 계산한 위험/추세 기반 조정 결과입니다.
- 변동성이 높아질 경우 다음 달 비중이 자동 축소됩니다.
""".strip()

    elif user_level == "intermediate":
        return f"""
📊 이번 달 투자 가이드

💰 이렇게 나눠서 사세요
- 주식: {plan.equity_amount_krw:,}원
- 안전자산: {plan.safe_amount_krw:,}원

🤔 왜 이렇게 정했을까요?
{reason_text}

💡 요약
- 시장 상황을 반영해 자동으로 계산된 비중이에요.
""".strip()

    # default = beginner
    return f"""
📊 이번 달 투자 계획이에요!

💰 주식: {plan.equity_amount_krw:,}원  
🛡️ 안전자산: {plan.safe_amount_krw:,}원

🤔 왜 이렇게 나눴나요?
{reason_text}

💡 Tip  
복잡하게 고민하지 말고  
정해진 날짜에 위 금액만 사면 충분해요 😊
""".strip()
