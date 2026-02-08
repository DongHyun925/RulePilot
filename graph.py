# graph.py
from __future__ import annotations

from typing import TypedDict, Dict, Any
from dataclasses import fields
from datetime import datetime, date
import re

from langgraph.graph import StateGraph, END

from state_schema import Profile, Policy, MonthSignal, PortfolioPlan, to_dict

from agents.router import route_intent
from agents.allocator import build_portfolio_plan
from agents.decision_validator import decide_now
from agents.tutor import answer_term_question
from model.monthly_model import run_monthly_model_from_market, simulate_portfolio_history, backtest_crisis_scenarios

from agents.intake import ask_next_question, apply_intake_answer
from agents.policy_writer import build_policy_from_profile, policy_to_text

from agents.order_planner import build_order_plan
from model.reason_explainer import explain_reason_codes

from agents.output_formatter import format_allocation_output

from data.db import (
    ensure_user,
    load_profile,
    load_active_profile,
    load_policy,
    save_policy,
    upsert_monthly_plan,
    yyyymm_now,
    update_active_profile,
    create_new_profile_and_activate,
    # ✅ 프로필 멀티 관리용 DB 함수(없으면 data/db.py에 추가해야 함)
    list_profiles,              # (user_id) -> list[dict]
    activate_profile_by_id,     # (user_id, profile_id) -> None
    rename_profile_by_id,       # (user_id, profile_id, new_label) -> None

    # ✅ 히스토리 조회용 DB 함수
    fetch_monthly_plans,        # (user_id, months:int) -> list[dict]  최근 n개월(최신부터)
)

# =========================================================
# State
# =========================================================
class AppState(TypedDict, total=False):
    user_text: str
    intent: str
    profile: Dict[str, Any]
    policy: Dict[str, Any]
    month_signal: Dict[str, Any]
    portfolio_plan: Dict[str, Any]
    output_text: str

    user_id: str

    profile_complete: bool
    pending_intake_field: str

    pending_confirm_reset: bool
    editing_settings: bool
    edit_mode: str  # "RESET" | "ADD"

    policy_text: str

    # ✅ 종목 추천 & 시뮬레이션용
    interview_step: str  # "ASK_GOAL" | "ASK_RISK" | "SHOW_RESULT" 등
    recommended_portfolio: Dict[str, Any]  # {tickers: [...], rationale: ...}
    simulation_data: Dict[str, Any]  # {history: [...], forecast: [...]}


def _filter_kwargs_for_dataclass(dc_cls, data: dict) -> dict:
    allowed = {f.name for f in fields(dc_cls)}
    return {k: v for k, v in (data or {}).items() if k in allowed}


def _extract_first_int(text: str) -> int | None:
    m = re.search(r"(\d+)", text or "")
    return int(m.group(1)) if m else None


def _extract_rename_target(text: str) -> tuple[int | None, str | None]:
    idx = _extract_first_int(text)
    qm = re.search(r"[\"']([^\"']+)[\"']", text or "")
    if qm:
        return idx, qm.group(1).strip()

    m = re.search(r"(?:이름을|이름)\s*([^\s]+)\s*(?:로|으로)\s*(?:바꿔|변경)", text or "")
    if m:
        return idx, m.group(1).strip()

    return idx, None


def _fmt_krw(x: Any) -> str:
    try:
        return f"{int(x):,}원"
    except Exception:
        return str(x)


# =========================================================
# ✅ Stock Recommendation & Simulation Nodes
# =========================================================
def node_stock_interview(state: AppState) -> AppState:
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage
    import json
    # 필요시 추가 import

    user_text = state.get("user_text", "")
    step = state.get("interview_step")
    
    # 1. 초기 진입 (step is None or empty)
    if not step:
        # ✅ 필수 조건 확인: 프로필(투자 계획)이 완성되어 있어야 함
        if not state.get("profile_complete"):
            state["output_text"] = (
                "🔒 **종목 추천 불가**\n\n"
                "고객님의 투자 성향과 목표를 모르면 맞춤 추천을 해드릴 수 없어요 😢\n"
                "먼저 **[투자 계획]**을 세워주시겠어요?\n\n"
                "👉 **'투자 계획 세울래'** 또는 **'시작해줘'**라고 말씀해주세요."
            )
            return state

        # ✅ 저장된 추천 내역 확인
        from data.db import load_latest_recommendation, load_active_profile
        user_id = state.get("user_id")
        profile_id, _ = load_active_profile(user_id)
        
        last_rec = load_latest_recommendation(user_id, profile_id)
        
        # 만약 저장된 추천이 있고, 사용자가 명시적으로 "새로"라고 안 했다면
        # "지난 번 추천을 보여드릴까요?" 라고 묻거나 바로 보여줌
        # 여기선 심플하게: "지난 추천이 있어요. 보시겠어요? 아니면 새로 추천해드릴까요?"
        if last_rec:
            # 추천 데이터 로드
            state["recommended_portfolio"] = last_rec
            created_at = last_rec.get("created_at", "")[:10]
            
            state["interview_step"] = "CHECK_EXISTING" # 신규 스텝
            state["output_text"] = (
                f"📋 **{created_at}**에 추천해드린 포트폴리오가 저장되어 있어요.\n\n"
                "이 내용을 다시 보시겠어요? 아니면 새로 추천을 받을까요?\n\n"
                "1. **기존 추천 보기** (네, 보여줘)\n"
                "2. **새로 추천 받기** (아니오, 새로 해줘)"
            )
            return state

        state["interview_step"] = "ASK_GOAL"
        state["output_text"] = (
            "📈 종목 추천을 해드릴게요.\n"
            "먼저 몇 가지 여쭤보겠습니다.\n\n"
            "가장 중요하게 생각하는 목표는 무엇인가요?\n"
            "1. 안정적인 배당 수익 (현금 흐름)\n"
            "2. 시장 평균 이상의 장기 성장 (S&P500, 나스닥 등)\n"
            "3. 공격적인 고수익 (개별 기술주, 레버리지 등)\n\n"
            "자유롭게 말씀해주세요!"
        )
        return state

    # 1.5 기존 추천 확인 단계
    if step == "CHECK_EXISTING":
        t = user_text
        if any(w in t for w in ["기존", "보기", "네", "응", "보여", "yes", "1"]):
            # 기존 추천 보여주기 -> 바로 SHOW_RESULT 로 점프하되, 출력 텍스트 구성 필요
            # recommended_portfolio는 이미 state에 로드됨
            rec = state["recommended_portfolio"]
            
            # 텍스트 재구성 (저장된 rationale 사용)
            rationale = rec.get('rationale', '')
            tickers_desc_list = []
            for tk in rec.get('tickers', []):
                r = tk['reason'].replace("\\n", "\n")
                tickers_desc_list.append(f"- **{tk['symbol']}** ({float(tk['weight'])*100:.0f}%): {r}")
            tickers_desc = "\n".join(tickers_desc_list)
            
            state["interview_step"] = "SHOW_RESULT"
            state["output_text"] = (
                f"📂 **저장된 포트폴리오를 불러왔습니다.**\n\n"
                f"{rationale}\n\n"
                f"{tickers_desc}\n\n"
                "📊 이 포트폴리오의 **미래 시뮬레이션**을 보시겠어요?\n"
                "(‘네’ 또는 ‘보여줘’라고 말해주세요)"
            )
            return state
        else:
            # 새로 추천
            state["interview_step"] = "ASK_GOAL"
            state["output_text"] = (
                "알겠습니다! 그럼 처음부터 다시 여쭤볼게요.\n\n"
                "가장 중요하게 생각하는 목표는 무엇인가요?\n"
                "1. 안정적인 배당 수익\n"
                "2. 시장 평균 이상의 장기 성장\n"
                "3. 공격적인 고수익"
            )
            return state

    # 2. 목표 답변 받음 -> 관심 분야 질문
    if step == "ASK_GOAL":
        # ... (기존 동일)
        # 편의상 state에 임시 저장
        state["profile"]["temp_goal"] = user_text
        
        state["interview_step"] = "ASK_SECTOR"
        state["output_text"] = (
            "좋습니다. 그렇다면 특별히 관심 있는 **산업 분야**나 **테마**가 있으신가요?\n\n"
            "예) 반도체, AI, 헬스케어, 소비재, 부동산, 딱히 없음 등\n\n"
            "말씀해주시면 해당 분야의 우량 ETF도 함께 찾아볼게요."
        )
        return state

    # 3. 관심 분야 답변 받음 -> 포트폴리오 생성
    if step == "ASK_SECTOR":
        goal = state["profile"].get("temp_goal", "장기 성장")
        sector = user_text
        state["interview_step"] = "SHOW_RESULT"
        
        # LLM 호출
        llm = ChatOpenAI(model="gpt-4", temperature=0.7)
        
        system_prompt = (
            "You are a professional portfolio manager named 'RulePilot'.\n"
            "Based on the user's investment goal and interested sectors, recommend a diversified portfolio of 3-5 US ETFs or stocks.\n"
            "The user wants a portfolio that will likely rise in the long term (Structural Growth).\n"
            "Output MUST be a JSON object with this structure:\n"
            "{\n"
            "  \"rationale\": \"Brief explanation of the portfolio strategy (Korean)\",\n"
            "  \"tickers\": [\n"
            "    {\"symbol\": \"QQQ\", \"weight\": 0.4, \"reason\": \"Detailed reason including sector fit...\"},\n"
            "    {\"symbol\": \"SCHD\", \"weight\": 0.3, \"reason\": \"...\"}\n"
            "  ]\n"
            "}\n"
            "Ensure the sum of weights is 1.0.\n"
            "Prioritize assets with strong historical uptrends (e.g., SPY, QQQ, VIG, NVDA, MSFT) if appropriate.\n"
            "Reflect the user's interested sector if valid (e.g., if 'AI', include SOXX or NVDA).\n"
            "Avoid extremely risky or obscure micro-caps.\n\n"
            "!!! IRON RULES (MUST FOLLOW) !!!\n"
            "1. The goal is NOT to make money, but NOT TO LOSE money.\n"
            "2. Keep Rule #1.\n"
            "Therefore, prioritize stability, maximum drawdown (MDD) management, and defensive assets (like SCHD, GLD, Bonds) or quality growth over high-risk speculation."
        )
        
        try:
            resp = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"User's goal: {goal}\nUser's interest: {sector}")
            ])
            
            content = resp.content.strip()
            # JSON 파싱 (마크다운 코드블록 제거)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            # 괄호 등 잘못된 문자열 정제 시도
            if content.startswith("{"):
                 portfolio_data = json.loads(content)
                 state["recommended_portfolio"] = portfolio_data
                 
                 # 줄바꿈 문자(\n)가 리터럴로 나오는 문제 해결 -> 실제 줄바꿈으로 변환
                 # JSON 파싱 되면 문자열 내부의 \n은 이미 제어문자가 되지만, 
                 # LLM이 \\n 이라고 줬을 수도 있으므로 replace
                 rationale = portfolio_data['rationale'].replace("\\n", "\n")
                 
                 # 티커 설명도 마찬가지
                 tickers_desc_list = []
                 for t in portfolio_data['tickers']:
                     r = t['reason'].replace("\\n", "\n")
                     tickers_desc_list.append(f"- **{t['symbol']}** ({float(t['weight'])*100:.0f}%): {r}")
                 
                 tickers_desc = "\n".join(tickers_desc_list)

                 # ✅ 추천 결과 DB 자동 저장 제거 -> 확인 단계 추가
                 
                 state["output_text"] = (
                     f"🚀 **추천 포트폴리오 제안**\n\n"
                     f"{rationale}\n\n"
                     f"{tickers_desc}\n\n"
                     "💾 **이 포트폴리오를 저장하시겠습니까?**\n"
                     "(‘네’라고 하면 저장하고, ‘아니오’라고 하면 저장하지 않아요)"
                 )
                 state["interview_step"] = "ASK_SAVE"
            else:
                 raise ValueError("Invalid JSON format")

        except Exception as e:
            state["output_text"] = f"죄송합니다. 포트폴리오 생성 중 오류가 발생했습니다.\n{str(e)}"
            state["interview_step"] = None # 리셋

        return state

    # 4. 저장 여부 확인
    if step == "ASK_SAVE":
        t = user_text
        if any(w in t for w in ["네", "응", "yes", "저장", "그래"]):
            from data.db import save_recommendation, load_active_profile
            user_id = state.get("user_id")
            profile_id, _ = load_active_profile(user_id)
            portfolio_data = state.get("recommended_portfolio")
            if portfolio_data:
                save_recommendation(user_id, profile_id, portfolio_data)
                state["output_text"] = (
                    "✅ **저장되었습니다!**\n\n"
                    "왼쪽 사이드바의 **[📂 저장된 포트폴리오]** 메뉴에서 언제든 다시 불러올 수 있어요.\n\n"
                    "📊 이제 이 포트폴리오의 **미래 시뮬레이션**을 보시겠어요?\n"
                    "(‘네’ 또는 ‘보여줘’라고 말해주세요)"
                )
            else:
                 state["output_text"] = "⚠️ 저장할 포트폴리오 정보가 없어요."
        else:
            state["output_text"] = (
                "알겠습니다. 저장하지 않고 넘어갈게요.\n\n"
                "📊 **미래 시뮬레이션**을 보시겠어요?\n"
                "(‘네’ 또는 ‘보여줘’라고 말해주세요)"
            )
        
        state["interview_step"] = "SHOW_RESULT"
        return state

    # 5. 결과 확인 후 시뮬레이션 요청 -> 라우팅에서 처리
    #    또는 질문 답변 처리
    if step == "SHOW_RESULT":
        # 이미 추천 결과가 있는 상태에서 질문이 들어옴
        port_data = state.get("recommended_portfolio")
        if not port_data:
            state["output_text"] = "⚠️ 추천 정보가 사라졌어요. 다시 추천해드릴까요?"
            state["interview_step"] = None
            return state

        # 단순 질문/답변 처리
        llm = ChatOpenAI(model="gpt-4", temperature=0.7)
        
        # 포트폴리오 정보를 컨텍스트로 제공
        context_str = json.dumps(port_data, ensure_ascii=False)
        
        system_prompt = (
            "You are a professional portfolio manager named 'RulePilot'.\n"
            "The user takes a look at the recommended portfolio and asks a question.\n"
            f"Current Portfolio Context: {context_str}\n"
            "Answer the user's question specifically regarding this portfolio.\n"
            "If the user asks for a comparison (e.g., VHT vs SPY), provide a logical investment perspective.\n"
            "Keep the answer concise and helpful (Korean).\n\n"
            "!!! IRON RULES (MUST FOLLOW) !!!\n"
            "1. The goal is NOT to make money, but NOT TO LOSE money.\n"
            "2. Keep Rule #1.\n"
            "Always advise caution and emphasize risk management (MDD) in your answers."
        )
        
        resp = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_text)
        ])
        
        state["output_text"] = (
            f"{resp.content}\n\n"
            "📊 **시뮬레이션**을 보시려면 '시뮬레이션 보여줘'라고 말씀해주세요."
        )
        return state
        
    return state


def node_portfolio_simulation(state: AppState) -> AppState:
    port_data = state.get("recommended_portfolio")
    if not port_data:
        state["output_text"] = "⚠️ 추천된 포트폴리오가 없습니다. 먼저 종목 추천을 받아주세요."
        return state

    portfolio = {t['symbol']: t['weight'] for t in port_data['tickers']}
    
    # 투자 기간 (기본 120개월)
    horizon = 120
    if state.get("profile") and state["profile"].get("horizon_months"):
        try:
            horizon = int(state["profile"]["horizon_months"])
        except:
            pass

    state["output_text"] = "⏳ 과거 데이터 분석 및 미래 시뮬레이션 중입니다... 잠시만 기다려주세요."
    
    try:
        # 시뮬레이션 실행
        # 1. 일반 시뮬레이션 (과거 + 미래)
        sim_result = simulate_portfolio_history(portfolio, months=horizon)
        
        # 2. 위기 상황 스트레스 테스트 (New)
        try:
            crisis_result = backtest_crisis_scenarios(portfolio)
            sim_result["crisis_test"] = crisis_result
        except Exception as e:
            print(f"Crisis test failed: {e}")
            sim_result["crisis_test"] = []
        
        if "error" in sim_result:
            state["output_text"] = f"데이터 로드 실패: {sim_result['error']}"
            return state
            
        state["simulation_data"] = sim_result
        
        metrics = sim_result.get("metrics", {})
        cagr = metrics.get('cagr_history', 0) * 100
        vol = metrics.get('vol_history', 0) * 100
        
        state["output_text"] = (
            f"✅ **시뮬레이션 완료!**\n\n"
            f"📊 **과거 성과 분석 (Backtest)**\n"
            f"- 연평균 수익률 (CAGR): **{cagr:.1f}%**\n"
            f"- 연 변동성 (Risk): {vol:.1f}%\n\n"
            f"🔮 **미래 예측 (Monte Carlo, {horizon}개월)**\n"
            f"- 아래 차트에서 예상되는 자산 가치 범위를 확인하세요.\n"
            f"- 점선 영역은 90% 확률 범위입니다.\n\n"
            f"> *주의: 과거의 성과가 미래의 수익을 보장하지 않습니다.*"
        )
        
    except Exception as e:
        state["output_text"] = f"시뮬레이션 중 오류 발생: {str(e)}"

    return state



# =========================================================
# Nodes
# =========================================================
def node_ensure_defaults(state: AppState) -> AppState:
    user_id = state.get("user_id") or "local"
    state["user_id"] = ensure_user(user_id)

    state.setdefault("profile", {})
    state.setdefault("policy", {})

    if state.get("pending_confirm_reset"):
        state["profile_complete"] = False
        return state

    if state.get("editing_settings"):
        state["profile_complete"] = False
        return state

    db_profile = load_profile(state["user_id"]) or {}
    db_policy = load_policy(state["user_id"]) or {}

    state["profile"] = {**db_profile, **state["profile"]}
    state["policy"] = {**db_policy, **state["policy"]}

    required = ["monthly_budget_krw", "horizon_months", "risk_level", "emergency_fund_ok", "user_level"]
    state["profile_complete"] = all(
        (k in state["profile"]) and (state["profile"][k] is not None)
        for k in required
    )
    return state


def node_intake(state: AppState) -> AppState:
    return ask_next_question(state)


def node_intake_answer(state: AppState) -> AppState:
    state = apply_intake_answer(state, state.get("user_text", ""))

    user_id = state.get("user_id", "local")
    state["user_id"] = ensure_user(user_id)

    if not state.get("profile_complete"):
        return state

    mode = state.get("edit_mode", "")  # "RESET" | "ADD" | ""
    prof = state.get("profile", {})

    if mode == "ADD":
        create_new_profile_and_activate(
            user_id=state["user_id"],
            profile=prof,
            label=prof.get("label", "추가 설정"),
        )
    else:
        update_active_profile(
            user_id=state["user_id"],
            profile=prof,
        )

    state["editing_settings"] = False
    state["edit_mode"] = ""
    state["pending_intake_field"] = ""

    state["policy"] = {}
    state["output_text"] = (
        "✅ 설정 저장 완료!\n"
        "이제 새 설정 기준으로 답변할게요.\n\n"
        "원하는 걸 말해줘!\n"
        "예) '이번 달 얼마씩 사야 해?', '지금 사도 돼?', 'ETF가 뭐야?'"
    )
    return state


def node_build_policy(state: AppState) -> AppState:
    user_id = state.get("user_id", "local")
    state["user_id"] = ensure_user(user_id)

    if state.get("profile_complete") and not state.get("policy"):
        pol = build_policy_from_profile(state["profile"])
        state["policy"] = pol
        state["policy_text"] = policy_to_text(pol)
        save_policy(state["user_id"], pol)

    return state


def node_route(state: AppState) -> AppState:
    if state.get("pending_confirm_reset"):
        state["intent"] = "EDIT_CONFIRM"
        return state

    text = state.get("user_text", "")
    
    # ✅ 시뮬레이션 직행 (인터뷰 완료 상태에서 '보여줘' 등)
    if state.get("interview_step") == "SHOW_RESULT":
        if any(w in text for w in ["보여줘", "시뮬레이션", "예", "응", "그래"]):
            state["intent"] = "RUN_SIMULATION"
            return state
    
    # ✅ 인터뷰 진행 중 (기존 추천 확인 포함)
    if state.get("interview_step") in ["ASK_GOAL", "ASK_RISK", "ASK_SECTOR", "CHECK_EXISTING", "SHOW_RESULT", "ASK_SAVE"]:
         state["intent"] = "RECOMMEND_STOCK"
         return state

    # ✅ 시장 브리핑 (RAG)
    market_keywords = [
        "시장", "뉴스", "시황", "분위기", "전망", "trend", "market",
        "경제", "증시", "지수", "장세", "나스닥", "다우", "S&P", "에스앤피",
        "장이", "장 상황", "장 흐름"
    ]
    if any(w in text for w in market_keywords) or "어때" in text:
        if "추천" not in text: # 추천 요청과 겹치지 않게
            state["intent"] = "MARKET_INFO"
            return state

    # 기본 라우팅
    intent = route_intent(text)
    
    # "추천해줘", "어떤 종목" 등이면 RECOMMEND_STOCK으로 오버라이드
    if "추천" in text or "종목" in text or "살까" in text:
        intent = "RECOMMEND_STOCK"

    state["intent"] = intent
    return state


def node_term_qa(state: AppState) -> AppState:
    state["output_text"] = answer_term_question(state.get("user_text", ""))
    return state


def node_onboard(state: AppState) -> AppState:
    if not state.get("profile_complete"):
        return ask_next_question(state)

    prof = state.get("profile", {})
    user_level = prof.get("user_level", "beginner")
    budget = prof.get("monthly_budget_krw")
    horizon = prof.get("horizon_months")
    risk = prof.get("risk_level")

    state["output_text"] = (
        "👋 저장된 설정을 불러왔어요!\n\n"
        f"🧾 내 설정 요약\n"
        f"- 월 투자금: {budget:,}원\n"
        f"- 기간: {horizon}개월\n"
        f"- 위험성향: {risk}\n"
        f"- 레벨: {user_level}\n\n"
        "원하는 걸 말해줘!\n"
        "✅ 예시) '이번 달 얼마씩 사야 해?', '지금 사도 돼?', 'ETF가 뭐야?'\n"
        "⚙️ 설정 변경은 '설정 바꿀래' 라고 말하면 돼."
    )
    return state


def node_run_model_if_needed(state: AppState) -> AppState:
    if "month_signal" not in state:
        signal = run_monthly_model_from_market(ticker="QQQ")
        state["month_signal"] = to_dict(signal)
    return state


def node_allocate(state: AppState) -> AppState:
    # 0) user_id 보장
    user_id = state.get("user_id") or "local"
    state["user_id"] = ensure_user(user_id)

    # 1) Profile 생성 (state에 user_level 같은 부가키가 섞여도 안전하게 필터링)
    base_profile = to_dict(Profile())
    merged_profile: Dict[str, Any] = {**base_profile, **(state.get("profile") or {})}

    allowed_keys = set(Profile().__dict__.keys())
    merged_profile = {k: v for k, v in merged_profile.items() if k in allowed_keys}
    
    # ✅ 필수값 검증 (None이 있으면 계산 불가)
    if not state.get("profile_complete"):
        state["output_text"] = (
            "⚠️ 투자 계획이 아직 설정되지 않았어요.\n"
            "먼저 투자 목표와 예산을 설정해드릴까요?\n\n"
            "👉 **'투자 계획 세워줘'**라고 말씀해주세요."
        )
        # 또는 바로 질문을 시작하려면:
        # return ask_next_question(state)
        return state

    prof = Profile(**merged_profile)

    # 2) 월간 시그널/계획 생성
    sig = MonthSignal(**state["month_signal"])
    plan = build_portfolio_plan(prof, sig)
    state["portfolio_plan"] = to_dict(plan)

    # 3) 주문 계획(예시)
    equity_ticker = "QQQ"
    safe_ticker = "BIL"
    fx = 1350  # MVP 고정 환율(원/달러)

    equity_order = build_order_plan(
        equity_ticker,
        plan.equity_amount_krw,
        fx_krw_per_usd=fx,
        allow_fractional=True,
    )
    safe_order = build_order_plan(
        safe_ticker,
        plan.safe_amount_krw,
        fx_krw_per_usd=fx,
        allow_fractional=True,
    )

    # 4) 이유 텍스트(설명용)
    reason_text = explain_reason_codes(getattr(sig, "reason_codes", []))

    # 5) 출력 포맷(초보/숙련 스타일 분기)
    user_level = (state.get("profile") or {}).get("user_level", "beginner")
    base_output = {
        "plan": plan,
        "signal": sig,
        "orders": {"equity": equity_order, "safe": safe_order},
        "reason_text": reason_text,
    }
    state["output_text"] = format_allocation_output(base_output, user_level)

    # 6) ✅ 히스토리 저장(딱 1번만, plan_json에 다 넣기)
    profile_id, _ = load_active_profile(state["user_id"])

    plan_payload: Dict[str, Any] = {
        **to_dict(plan),
        "as_of": yyyymm_now(),  # 예: "202601"
        "equity_ticker": equity_ticker,
        "safe_ticker": safe_ticker,
        "fx_krw_per_usd": fx,
        "orders": {"equity": equity_order, "safe": safe_order},
        "reason_codes": getattr(sig, "reason_codes", []),
        "equity_weight": float(sig.equity_weight),
        "safe_weight": float(sig.safe_weight),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    upsert_monthly_plan(
        user_id=state["user_id"],
        profile_id=profile_id,
        yyyymm=yyyymm_now(),
        plan=plan_payload,
    )

    return state


def node_maybe_decide(state: AppState) -> AppState:
    user_id = state.get("user_id", "local")
    state["user_id"] = ensure_user(user_id)

    if state.get("intent") != "DECIDE_NOW":
        return state

    pol_dict = _filter_kwargs_for_dataclass(Policy, state.get("policy", {}))
    sig_dict = _filter_kwargs_for_dataclass(MonthSignal, state.get("month_signal", {}))
    plan_dict = _filter_kwargs_for_dataclass(PortfolioPlan, state.get("portfolio_plan", to_dict(PortfolioPlan())))

    pol = Policy(**pol_dict)
    sig = MonthSignal(**sig_dict)
    plan = PortfolioPlan(**plan_dict)

    decision = decide_now(state.get("user_text", ""), pol, sig, plan)

    state["output_text"] = (
        f"🚦 지금 할 행동\n"
        f"👉 결정: {decision.action}\n\n"
        f"📌 이유:\n{decision.reason}\n\n"
        f"➡️ 다음 할 일:\n{decision.next_step}"
    )
    return state


# -------------------------
# 설정 변경(confirm) 플로우
# -------------------------
def node_edit_settings_request(state: AppState) -> AppState:
    return {
        "pending_confirm_reset": True,
        "output_text": (
            "⚙️ 설정을 바꾸려면 먼저 확인할게요.\n"
            "기존 설정을 삭제하고 새로 시작할까요?\n\n"
            "✅ 예: 기존 설정을 덮어쓰기(삭제/초기화)\n"
            "❌ 아니오: 기존 설정은 유지하고 ‘새 설정’을 추가\n\n"
            "(예/아니오로 답해줘)"
        ),
    }


def node_edit_settings_confirm(state: AppState) -> AppState:
    t = (state.get("user_text") or "").strip().lower()
    yes = t in ["예", "네", "y", "yes", "응", "삭제", "초기화"]

    next_state = {
        "pending_confirm_reset": False,
        "edit_mode": "RESET" if yes else "ADD",
        "editing_settings": True,
        "profile_complete": False,
        "pending_intake_field": "",
        "profile": {},
        "policy": {},
        "month_signal": {},
        "portfolio_plan": {},
    }
    return ask_next_question({**state, **next_state})


# =========================================================
# ✅ Profile multi-management nodes
# =========================================================
def node_profile_list(state: AppState) -> AppState:
    user_id = ensure_user(state.get("user_id") or "local")
    state["user_id"] = user_id

    profiles = list_profiles(user_id) or []
    if not profiles:
        state["output_text"] = (
            "📭 저장된 설정이 아직 없어요.\n"
            "먼저 온보딩을 완료하거나 '설정 바꿀래'로 새 설정을 만들어주세요."
        )
        return state

    lines = ["📋 내 설정 목록", ""]
    for i, p in enumerate(profiles, start=1):
        label = p.get("label") or f"설정 {i}"
        active = " (현재)" if p.get("is_active") else ""
        lines.append(f"{i}. {label}{active}")

    lines += [
        "",
        "바꾸기:  \"설정 2번으로 바꿔줘\"",
        "이름변경: \"2번 설정 이름을 '은퇴모드'로 바꿔줘\"",
    ]
    state["output_text"] = "\n".join(lines)
    return state


def node_profile_switch(state: AppState) -> AppState:
    user_id = ensure_user(state.get("user_id") or "local")
    state["user_id"] = user_id

    profiles = list_profiles(user_id) or []
    if not profiles:
        state["output_text"] = "📭 바꿀 설정이 없어요. 먼저 설정을 만들어주세요."
        return state

    idx = _extract_first_int(state.get("user_text", ""))
    if idx is None:
        state["output_text"] = (
            "몇 번 설정으로 바꿀지 숫자를 같이 말해주세요.\n"
            "예) '설정 2번으로 바꿔줘'"
        )
        return state

    if idx < 1 or idx > len(profiles):
        state["output_text"] = f"설정 번호가 범위를 벗어났어요. (1 ~ {len(profiles)})"
        return state

    target = profiles[idx - 1]
    profile_id = target.get("id")
    if not profile_id:
        state["output_text"] = "프로필 ID를 찾지 못했어요. DB 스키마를 확인해주세요."
        return state

    activate_profile_by_id(user_id, profile_id)

    # 다음 턴 ensure_defaults가 DB에서 새 active를 로드하도록 비움
    state["profile"] = {}
    state["policy"] = {}
    state["month_signal"] = {}
    state["portfolio_plan"] = {}
    state["profile_complete"] = False

    label = target.get("label") or f"설정 {idx}"
    state["output_text"] = f"✅ '{label}'로 설정을 전환했어요."
    return state


def node_profile_rename(state: AppState) -> AppState:
    user_id = ensure_user(state.get("user_id") or "local")
    state["user_id"] = user_id

    profiles = list_profiles(user_id) or []
    if not profiles:
        state["output_text"] = "📭 이름을 바꿀 설정이 없어요. 먼저 설정을 만들어주세요."
        return state

    idx, new_label = _extract_rename_target(state.get("user_text", ""))

    if idx is None:
        active = next((p for p in profiles if p.get("is_active")), None) or profiles[0]
        profile_id = active.get("id")
        old_label = active.get("label") or "현재 설정"
    else:
        if idx < 1 or idx > len(profiles):
            state["output_text"] = f"설정 번호가 범위를 벗어났어요. (1 ~ {len(profiles)})"
            return state
        target = profiles[idx - 1]
        profile_id = target.get("id")
        old_label = target.get("label") or f"설정 {idx}"

    if not profile_id:
        state["output_text"] = "프로필 ID를 찾지 못했어. DB 스키마를 확인해주세요."
        return state

    if not new_label:
        state["output_text"] = (
            "바꿀 이름을 같이 말해주세요.\n"
            "예) \"2번 설정 이름을 '은퇴모드'로 바꿔줘\""
        )
        return state

    rename_profile_by_id(user_id, profile_id, new_label.strip())
    state["output_text"] = f"✅ '{old_label}' 이름을 '{new_label.strip()}'로 바꿨어요."
    return state


# =========================================================
# ✅ Helpers (weights / history)
# =========================================================
def _to_float_or_none(x):
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _normalize_weights(eq_w, sf_w, default_eq=0.6, default_sf=0.4):
    eq = _to_float_or_none(eq_w)
    sf = _to_float_or_none(sf_w)

    if eq is None and sf is None:
        return default_eq, default_sf

    if eq is None and sf is not None:
        sf = max(0.0, min(1.0, sf))
        return 1.0 - sf, sf

    if sf is None and eq is not None:
        eq = max(0.0, min(1.0, eq))
        return eq, 1.0 - eq

    eq = max(0.0, eq)
    sf = max(0.0, sf)
    s = eq + sf
    if s <= 0:
        return default_eq, default_sf
    return eq / s, sf / s


def _pct(x):
    try:
        return f"{float(x):.0%}"
    except (TypeError, ValueError):
        return "N/A"


def _show(x, fallback="(저장되지 않음)"):
    return x if x not in (None, "", []) else fallback


def _norm_yyyymm(as_of: Any) -> str:
    """
    as_of가 '202601', '2026-01', '2026/01', '2026-01-01' 등으로 와도
    비교 가능한 'YYYYMM' 형태로 정규화.
    """
    s = str(as_of or "").strip()
    digits = re.sub(r"[^0-9]", "", s)
    if len(digits) >= 6:
        return digits[:6]
    return ""


def _fmt_as_of(as_of: Any) -> str:
    yyyymm = _norm_yyyymm(as_of)
    if len(yyyymm) == 6:
        return f"{yyyymm[:4]}-{yyyymm[4:6]}"
    return str(as_of or "")


def _is_empty_plan_row(r: dict) -> bool:
    fields = [
        r.get("equity_ticker"),
        r.get("safe_ticker"),
        r.get("equity_order"),
        r.get("safe_order"),
        r.get("reason_codes"),
        # 혹시 orders 구조로만 저장한 경우도 대비
        (r.get("orders") or {}).get("equity") if isinstance(r.get("orders"), dict) else None,
        (r.get("orders") or {}).get("safe") if isinstance(r.get("orders"), dict) else None,
    ]
    return all((v is None or v == "" or v == []) for v in fields)


def _pick_last_month_row(rows: list[dict]) -> dict | None:
    """
    fetch_monthly_plans는 '최근 N건'을 주는 경우가 많아서,
    전월(=현재월 제외 가장 최신)을 여기서 골라준다.
    """
    cur = _norm_yyyymm(yyyymm_now())
    for r in rows or []:
        a = _norm_yyyymm(r.get("as_of"))
        if not a:
            continue
        # 현재월 제외
        if cur and a == cur:
            continue
        return r
    return None


# =========================================================
# ✅ History nodes
# =========================================================
def node_history_last_month(state: AppState) -> AppState:
    user_id = ensure_user(state.get("user_id") or "local")
    state["user_id"] = user_id

    # ✅ 전월을 고르기 위해 여유 있게 가져옴(이번달 포함 가능성 때문에)
    rows = fetch_monthly_plans(user_id=user_id, months=6) or []
    if not rows:
        state["output_text"] = "📭 지난달 기록이 아직 없어요. 먼저 한 번 '이번 달 계획'을 생성해주세요."
        return state

    r = _pick_last_month_row(rows)
    if not r or _is_empty_plan_row(r):
        state["output_text"] = "📭 지난달 기록이 아직 없어요. 먼저 한 번 '이번 달 계획'을 생성해주세요."
        return state

    # 🔎 필요하면 디버그(원하면 True로 바꿔서 사용)
    DEBUG_HISTORY = False
    if DEBUG_HISTORY:
        print("[DEBUG fetch_monthly_plans len]", len(rows))
        print("[DEBUG picked row]", r)

    as_of = _fmt_as_of(r.get("as_of", ""))

    eq_w_raw = r.get("equity_weight")
    sf_w_raw = r.get("safe_weight")
    eq_w, sf_w = _normalize_weights(eq_w_raw, sf_w_raw)

    # 컬럼/구조가 다를 수 있으니 orders도 fallback로 활용
    orders = r.get("orders") if isinstance(r.get("orders"), dict) else {}
    eq_t = r.get("equity_ticker") or r.get("equity_symbol") or "QQQ"
    sf_t = r.get("safe_ticker") or r.get("safe_symbol") or "BIL"
    reasons = r.get("reason_codes") or []
    eq_order = r.get("equity_order") or orders.get("equity")
    sf_order = r.get("safe_order") or orders.get("safe")

    state["output_text"] = (
        f"🗓️ 지난달 투자 계획 요약 ({as_of})\n\n"
        f"- 비중: 주식 {_pct(eq_w)} / 안전 {_pct(sf_w)}\n"
        f"- 티커: {_show(eq_t)} / {_show(sf_t)}\n"
        f"- 주문(주식): {_show(eq_order)}\n"
        f"- 주문(안전): {_show(sf_order)}\n"
        f"- 이유코드: {', '.join(reasons) if reasons else '없음'}"
    )
    return state


def node_history_3m(state: AppState) -> AppState:
    user_id = ensure_user(state.get("user_id") or "local")
    state["user_id"] = user_id

    # 최근 넉넉히 가져와서 "현재월 제외" 후 3개 뽑기
    rows = fetch_monthly_plans(user_id=user_id, months=12) or []
    if not rows:
        state["output_text"] = "📭 최근 3개월 기록이 아직 없어요. 먼저 한 번 '이번 달 계획'을 생성해주세요."
        return state

    cur = _norm_yyyymm(yyyymm_now())
    filtered: list[dict] = []
    for r in rows:
        a = _norm_yyyymm(r.get("as_of"))
        if cur and a == cur:
            continue
        if _is_empty_plan_row(r):
            continue
        filtered.append(r)
        if len(filtered) >= 3:
            break

    if not filtered:
        state["output_text"] = "📭 최근 3개월 기록이 아직 없어요. 먼저 한 번 '이번 달 계획'을 생성해주세요."
        return state

    lines = ["📊 지난 3개월 투자 요약", ""]
    for r in filtered:
        as_of = _fmt_as_of(r.get("as_of", ""))

        eq_w_raw = r.get("equity_weight")
        sf_w_raw = r.get("safe_weight")
        eq_w, sf_w = _normalize_weights(eq_w_raw, sf_w_raw)

        orders = r.get("orders") if isinstance(r.get("orders"), dict) else {}
        eq_t = r.get("equity_ticker") or r.get("equity_symbol") or "QQQ"
        sf_t = r.get("safe_ticker") or r.get("safe_symbol") or "BIL"
        eq_order = r.get("equity_order") or orders.get("equity")
        sf_order = r.get("safe_order") or orders.get("safe")

        lines.append(f"• {as_of} | 주식 {_pct(eq_w)}({_show(eq_t)}) / 안전 {_pct(sf_w)}({_show(sf_t)})")
        lines.append(f"  - 주문: {_show(eq_order)} / {_show(sf_order)}")

    state["output_text"] = "\n".join(lines)
    return state



# =========================================================
# ✅ RAG Node: Market Briefing
# =========================================================
def node_market_briefing(state: AppState) -> AppState:
    from langchain_community.tools import DuckDuckGoSearchRun
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    state["output_text"] = "🔍 최신 시장 뉴스를 검색하고 있습니다... 잠시만 기다려주세요."
    
    # 1. 검색어 설정 (사용자 질문에 따라 동적 변경)
    user_text = state.get("user_text", "")
    
    # 단순 시장 질문인지, 특정 종목 질문인지 판단
    target_ticker = None
    # 대문자로 변환하여 티커 찾기 (간단한 로직)
    import re
    # 영어 대문자 2~5글자 혹은 한글 종목명 추정
    # 여기서는 간단히 사용자 텍스트를 그대로 쿼리에 반영
    
    if "시장" in user_text or "장" in user_text:
        query = "최신 미국 증시 전망 및 주요 뉴스 latest US stock market news"
        focus = "market"
    else:
        # "TQQQ 어때?" -> "TQQQ 전망 분석"
        query = f"{user_text} 주가 전망 분석 news analysis"
        focus = "stock"

    try:
        search = DuckDuckGoSearchRun()
        search_result = search.invoke(query)
    except Exception as e:
        search_result = f"검색 중 오류 발생: {str(e)}"

    # 2. LLM 요약 및 인사이트 도출
    try:
        llm = ChatOpenAI(model="gpt-4", temperature=0.7)
        
        if focus == "market":
            system_prompt = (
                "You are a professional financial analyst named 'RulePilot'.\n"
                "Analyze the provided search results about the US stock market.\n"
                "Summarize the key trends, risks, and opportunities in 3 bullet points.\n"
                "Finally, give a brief investment advice based on the 'Iron Rule': 'Don't lose money'.\n"
                "Answer in Korean, friendly and professional tone."
            )
        else:
            system_prompt = (
                "You are a professional financial analyst named 'RulePilot'.\n"
                "The user asked about a specific stock/ETF.\n"
                "Analyze the provided search results to summarize:\n"
                "1. Recent Performance & Trend\n"
                "2. Key News or Catalysts\n"
                "3. Risk Factors (Iron Rules perspective)\n"
                "Conclude with a cautious stance emphasized on downside protection.\n"
                "Answer in Korean, friendly and professional tone."
            )
        
        resp = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"User Question: {user_text}\n\nSearch Result:\n{search_result}")
        ])
        
        state["output_text"] = (
            f"📰 **최신 시장 브리핑**\n\n"
            f"{resp.content}\n\n"
            "💡 이 정보를 바탕으로 **[종목 추천]**을 받아보시겠어요?"
        )
    except Exception as e:
        state["output_text"] = f"시장 브리핑 생성 중 오류가 발생했습니다.\n{str(e)}"

    return state

# =========================================================
# Gates / Routers
# =========================================================
def gate_after_defaults(state: AppState) -> str:
    if state.get("pending_confirm_reset"):
        return "EDIT_CONFIRM"
    if state.get("pending_intake_field"):
        return "INTAKE_ANSWER"
    if not state.get("profile_complete"):
        return "INTAKE"
    return "READY"


def gate_after_intake_answer(state: AppState) -> str:
    return "READY" if state.get("profile_complete") else "MORE"


def route_by_intent(state: AppState) -> str:
    return state.get("intent", "ALLOCATE")


# =========================================================
# Build graph
# =========================================================
def build_app():
    g = StateGraph(AppState)

    # Nodes
    g.add_node("ensure_defaults", node_ensure_defaults)

    g.add_node("intake", node_intake)
    g.add_node("intake_answer", node_intake_answer)
    g.add_node("build_policy", node_build_policy)

    g.add_node("route", node_route)
    g.add_node("term_qa", node_term_qa)
    g.add_node("onboard", node_onboard)

    g.add_node("run_model_if_needed", node_run_model_if_needed)
    g.add_node("allocate", node_allocate)
    g.add_node("maybe_decide", node_maybe_decide)

    # 설정 변경(confirm) 플로우
    g.add_node("edit_settings_request", node_edit_settings_request)
    g.add_node("edit_settings_confirm", node_edit_settings_confirm)

    # Profile multi management
    g.add_node("profile_list", node_profile_list)
    g.add_node("profile_switch", node_profile_switch)
    g.add_node("profile_rename", node_profile_rename)

    # ✅ History nodes
    g.add_node("history_last_month", node_history_last_month)
    g.add_node("history_3m", node_history_3m)

    # ✅ Stock & Simulation
    g.add_node("stock_interview", node_stock_interview)
    g.add_node("portfolio_simulation", node_portfolio_simulation)
    g.add_node("market_briefing", node_market_briefing)

    # Entry
    g.set_entry_point("ensure_defaults")

    # Gate after defaults
    g.add_conditional_edges(
        "ensure_defaults",
        gate_after_defaults,
        {
            "EDIT_CONFIRM": "edit_settings_confirm",
            "INTAKE": "intake",
            "INTAKE_ANSWER": "intake_answer",
            "READY": "build_policy",
        },
    )

    # Onboarding loop
    g.add_edge("intake", END)

    g.add_conditional_edges(
        "intake_answer",
        gate_after_intake_answer,
        {
            "MORE": END,
            "READY": "build_policy",
        },
    )

    # Policy -> route
    g.add_edge("build_policy", "route")

    # Intent routing
    g.add_conditional_edges(
        "route",
        route_by_intent,
        {
            "ONBOARD": "onboard",

            "EDIT_SETTINGS": "edit_settings_request",
            "EDIT_CONFIRM": "edit_settings_confirm",

            "PROFILE_LIST": "profile_list",
            "PROFILE_SWITCH": "profile_switch",
            "PROFILE_RENAME": "profile_rename",

            "HISTORY_LAST_MONTH": "history_last_month",
            "HISTORY_3M": "history_3m",

            "TERM_QA": "term_qa",
            "ALLOCATE": "run_model_if_needed",
            "DECIDE_NOW": "run_model_if_needed",
            
            # ✅ 추가된 라우팅
            "RECOMMEND_STOCK": "stock_interview",
            "RUN_SIMULATION": "portfolio_simulation",
            "MARKET_INFO": "market_briefing",
        },
    )

    # Terminal nodes
    g.add_edge("term_qa", END)
    g.add_edge("onboard", END)
    g.add_edge("market_briefing", END)

    g.add_edge("edit_settings_request", END)
    g.add_edge("edit_settings_confirm", END)

    g.add_edge("profile_list", END)
    g.add_edge("profile_switch", END)
    g.add_edge("profile_rename", END)

    # ✅ History terminal edges
    g.add_edge("history_last_month", END)
    g.add_edge("history_3m", END)
    
    # ✅ Stock terminal edges
    g.add_edge("stock_interview", END)
    g.add_edge("portfolio_simulation", END)

    # Allocate flow
    g.add_edge("run_model_if_needed", "allocate")
    g.add_edge("allocate", "maybe_decide")
    g.add_edge("maybe_decide", END)

    return g.compile()
