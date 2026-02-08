# agents/router.py
from __future__ import annotations
import re


def route_intent(user_text: str) -> str:
    t = (user_text or "").strip()

    if t == "":
        return "ONBOARD"

    # -------------------------
    # 1) 설정/프로필 관리
    # -------------------------
    if any(k in t for k in ["설정 바꿔", "설정 바꾸자", "설정 변경", "설정 수정", "프로필 바꿔", "프로필 변경"]):
        return "EDIT_SETTINGS"

    if any(k in t for k in ["내 설정 목록", "설정 목록", "프로필 목록", "내 설정 보여줘", "설정 리스트"]):
        return "PROFILE_LIST"

    if re.search(r"설정\s*\d+\s*번", t) and any(k in t for k in ["바꿔", "전환", "선택", "사용"]):
        return "PROFILE_SWITCH"

    if (("이 설정" in t) or ("설정 이름" in t) or ("이름을" in t)) and any(k in t for k in ["바꿔", "변경", "rename"]):
        if re.search(r"(이\s*설정\s*이름|설정\s*이름|이름)\s*을", t) or ("이 설정 이름" in t):
            return "PROFILE_RENAME"

    # -------------------------
    # 2) 과거 기록 조회 (강화)
    # -------------------------
    # "지난달"뿐 아니라 "지난 달/저번 달/이전 달/전 달" 등도 처리
    last_month_pat = r"(지난\s*달|지난달|저번\s*달|저번달|이전\s*달|이전달|전\s*달|전달)"
    # 사용자가 history를 요청할 때 자주 쓰는 동사/명사도 포함
    history_action = r"(보여|조회|확인|요약|정리|기록|내역)"
    plan_words = r"(계획|투자|비중|주문|리포트|가이드)?"

    if re.search(last_month_pat, t) and (re.search(history_action, t) or re.search(plan_words, t)):
        return "HISTORY_LAST_MONTH"

    # 3개월 요약도 "보여줘/조회"만 있어도 잡히게
    three_month_pat = r"(최근\s*3\s*개월|지난\s*3\s*개월|3\s*개월)"
    if re.search(three_month_pat, t) and re.search(r"(요약|정리|리포트|조회|보여|내역)", t):
        return "HISTORY_3M"

    # -------------------------
    # 3) 용어 설명(TERM_QA)
    # -------------------------
    term_markers = ["뭐야", "뜻", "의미", "설명", "용어", "란"]
    finance_terms = ["etf", "per", "pbr", "배당", "분산", "리밸런싱", "지수", "s&p", "나스닥", "qqq", "tqqq"]
    if any(m in t for m in term_markers) and any(ft.lower() in t.lower() or ft in t for ft in finance_terms):
        return "TERM_QA"

    if "?" in t and any(ft.lower() in t.lower() or ft in t for ft in finance_terms):
        return "TERM_QA"

    # -------------------------
    # 4) 지금 사도 되나? (DECIDE_NOW)
    # -------------------------
    decide_markers = ["지금 사", "지금 사도", "지금 매수", "추가로 사", "더 사", "급락", "급등", "불안", "무서", "조급"]
    if any(m in t for m in decide_markers):
        return "DECIDE_NOW"

    # -------------------------
    # 5) 이번 달 계획/얼마씩 사? (ALLOCATE)
    # -------------------------
    allocate_markers = ["얼마씩", "얼마 사", "비중", "포트폴리오", "이번 달", "투자 계획", "가이드", "분배"]
    if any(m in t for m in allocate_markers):
        return "ALLOCATE"

    # -------------------------
    # 6) 온보딩 (계획 수립/시작)
    # -------------------------
    # "세워줘", "만들어줘" 등이 포함된 계획 관련 발화는 ONBOARD로 처리
    onboard_markers = ["시작", "온보딩", "프로필", "설정 등록", "처음", "가입"]
    
    if any(m in t for m in onboard_markers):
        return "ONBOARD"
        
    if "계획" in t and any(v in t for v in ["세워", "수립", "만들", "짜"]):
        return "ONBOARD"

    return "ALLOCATE"
