from typing import List

def explain_reason_codes(codes: List[str]) -> str:
    """
    TREND_UP / TREND_DOWN / VOL_SPIKE 등의 코드들을
    초보자용 설명 문장으로 변환
    """
    if not codes:
        return "이번 달은 특별한 신호가 없어서 기본 비중으로 설정했어요."

    lines = []

    for c in codes:
        if c == "TREND_UP":
            lines.append("최근 시장이 장기 평균보다 위에 있어서 긍정적인 추세예요.")
        elif c == "TREND_DOWN":
            lines.append("최근 시장이 장기 평균보다 아래에 있어서 조심할 필요가 있어요.")
        elif c == "VOL_SPIKE":
            lines.append("요즘 가격 흔들림(변동성)이 커서 위험이 조금 높아요.")
        elif c == "DEFAULT":
            lines.append("특별히 강한 신호가 없어서 기본 전략을 따랐어요.")
        else:
            lines.append(f"신호 코드: {c}")

    return "\n".join(f"- {l}" for l in lines)
