import streamlit as st
import time
from dotenv import load_dotenv
import os

# 환경변수 로드
load_dotenv()

from graph import build_app
from data.db import load_profile

# 페이지 설정
st.set_page_config(page_title="RulePilot AI", page_icon="🤖")

# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

if "rulepilot_state" not in st.session_state:
    st.session_state.rulepilot_state = {"user_id": "streamlit_user"} # 기본 사용자 ID
    st.session_state.rulepilot_state["user_text"] = "" # 초기 트리거용

if "app_instance" not in st.session_state:
    st.session_state.app_instance = build_app()
    # 첫 실행 시 봇의 초기 메시지 트리거
    initial_state = st.session_state.rulepilot_state.copy()
    out = st.session_state.app_instance.invoke(initial_state)
    
    if isinstance(out, dict):
        st.session_state.rulepilot_state.update(out)
        
    if st.session_state.rulepilot_state.get("output_text"):
         st.session_state.messages.append({"role": "assistant", "content": st.session_state.rulepilot_state["output_text"]})


# 사이드바
with st.sidebar:
    st.title("RulePilot 설정")
    
    # API Key 설정 (선택 사항)
    api_key = st.text_input("OpenAI API Key", type="password", help="비어있으면 .env 파일의 키를 사용합니다.")
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    
    st.divider()
    
    # ---------------------------------------------------------
    # 👤 사용자 관리 (JSON 파일 기반)
    # ---------------------------------------------------------
    import json
    USER_DATA_FILE = "user_data.json"

    def load_users():
        if os.path.exists(USER_DATA_FILE):
            try:
                with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return ["streamlit_user"]

    def save_users(ulist):
        with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(ulist, f, ensure_ascii=False, indent=2)

    user_list = load_users()
    current_uid = st.session_state.rulepilot_state.get("user_id", "streamlit_user")

    # 만약 현재 ID가 리스트에 없으면 추가 (초기화시 방어 로직)
    if current_uid not in user_list:
        user_list.append(current_uid)
        save_users(user_list)

    st.subheader("👤 사용자 선택")
    
    # Selectbox로 사용자 전환
    try:
        idx = user_list.index(current_uid)
    except ValueError:
        idx = 0
    
    selected_user = st.selectbox("접속할 사용자 ID", user_list, index=idx)

    # 사용자가 변경되었으면 상태 업데이트 & 리로드
    if selected_user != current_uid:
        # ✅ 상태 완전 초기화 (이전 사용자의 profile 등 데이터 잔존 방지)
        st.session_state.rulepilot_state = {
            "user_id": selected_user,
            "user_text": "",
            "interview_step": None,
            "output_text": "" 
        }
        st.session_state.messages = [] 
        
        st.session_state.app_instance = build_app()
        
        # ✅ 새 사용자 접속 시 봇이 먼저 말 걸기 (Welcome Message)
        # DB에 프로필이 있는지 확인
        existing_profile = load_profile(selected_user)
        
        if existing_profile and existing_profile.get("monthly_budget_krw"):
            # 이미 설정된 프로필이 있음 -> "돌아오셨군요!"
            welcome_msg = (
                f"돌아오셨군요, **{selected_user}**님! 👋\n"
                "지난 번에 세운 투자 계획을 기억하고 있어요.\n\n"
                "무엇을 도와드릴까요?\n"
                "- 📈 **종목 추천** 받기\n"
                "- 💰 **이번 달 투자 계획** 확인하기\n"
                "- ⚙️ **설정 변경**하기"
            )
        else:
            # 프로필 없음 (신규)
            welcome_msg = (
                f"안녕하세요, **{selected_user}**님! 👋\n"
                "저는 당신의 AI 투자 파트너 **RulePilot**입니다.\n\n"
                "투자를 시작하기 전에, 먼저 **맞춤형 투자 계획**을 세워야 해요.\n"
                "그래야 딱 맞는 종목을 추천해드릴 수 있거든요! 🧐\n\n"
                "👉 **'투자 계획 세워줘'**라고 말씀해주세요."
            )
            
        st.session_state.messages.append({"role": "assistant", "content": welcome_msg})
        
        st.rerun()

    # 사용자 추가/삭제 관리
    with st.expander("➕ / ➖ 사용자 관리"):
        new_name = st.text_input("새 사용자 이름 추가")
        if st.button("추가"):
            if new_name and new_name not in user_list:
                user_list.append(new_name)
                save_users(user_list)
                st.success(f"'{new_name}' 추가 완료!")
                time.sleep(1)
                
                # 추가 즉시 해당 유저로 전환하며 리로드
                # ✅ 상태 완전 초기화
                st.session_state.rulepilot_state = {
                    "user_id": new_name,
                    "user_text": "",
                    "interview_step": None,
                    "output_text": ""
                }
                st.session_state.messages = []
                st.session_state.app_instance = build_app()
                
                welcome_msg = (
                    f"반가워요, **{new_name}**님! 🎉\n"
                    "저와 함께 성공적인 투자를 시작해봐요!\n\n"
                    "가장 먼저 해야 할 일은 **[투자 계획 세우기]**예요.\n"
                    "👉 **'투자 계획 세워줘'**라고 말씀해주세요."
                )
                st.session_state.messages.append({"role": "assistant", "content": welcome_msg})
                
                st.rerun()
            elif new_name in user_list:
                st.warning("이미 존재하는 이름입니다.")
            else:
                st.warning("이름을 입력해주세요.")

        st.caption("---")
        st.caption("---")
        
        # 삭제 로직: 버튼 클릭 시 상태 토글 -> 확인 버튼 표시
        if "delete_confirm_mode" not in st.session_state:
            st.session_state.delete_confirm_mode = False

        if not st.session_state.delete_confirm_mode:
            if st.button("🗑️ 현재 사용자 삭제", type="primary"):
                st.session_state.delete_confirm_mode = True
                st.rerun()
        else:
            st.warning(f"⚠️ 정말 '{current_uid}' 사용자를 삭제하시겠습니까?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ 예, 삭제", type="primary"):
                    if len(user_list) <= 1:
                        st.error("최소 1명은 있어야 합니다.")
                        st.session_state.delete_confirm_mode = False
                    else:
                        user_list.remove(current_uid)
                        save_users(user_list)
                        # 삭제 후 첫 번째 사용자로 전환
                        st.session_state.rulepilot_state["user_id"] = user_list[0]
                        st.session_state.messages = []
                        st.session_state.delete_confirm_mode = False
                        st.rerun()
            with col2:
                if st.button("❌ 취소"):
                    st.session_state.delete_confirm_mode = False
                    st.rerun()

    # ---------------------------------------------------------
    # 📂 저장된 포트폴리오 불러오기
    # ---------------------------------------------------------
    st.divider()
    st.markdown("### 📂 저장된 포트폴리오")
    
    from data.db import list_saved_recommendations, load_active_profile
    profile_id, _ = load_active_profile(st.session_state.rulepilot_state["user_id"])
    saved_recs = list_saved_recommendations(st.session_state.rulepilot_state["user_id"], profile_id)
    
    if not saved_recs:
        st.caption("아직 저장된 포트폴리오가 없습니다.")
    else:
        # 셀렉트박스용 옵션 생성
        options = {f"{r['created_at'][:16]} ({r['summary']})": r for r in saved_recs}
        selected_key = st.selectbox("불러올 포트폴리오 선택", ["선택하세요"] + list(options.keys()))
        
        
        if selected_key != "선택하세요":
            col1, col2 = st.columns([3, 1])
            
            with col1:
                if st.button("📥 불러오기", key=f"load_portfolio_{selected_key}"):
                    target_rec = options[selected_key]["data"]
                    
                    # 상태 업데이트
                    st.session_state.rulepilot_state["recommended_portfolio"] = target_rec
                    st.session_state.rulepilot_state["interview_step"] = "SHOW_RESULT"
                    st.session_state.rulepilot_state["intent"] = "RECOMMEND_STOCK"
                    
                    # 포트폴리오 상세 내용 포함
                    rationale = target_rec.get("rationale", "추천 이유 없음")
                    tickers = target_rec.get("tickers", [])
                    
                    tickers_desc = "\n".join([
                        f"- **{t['symbol']}** ({float(t['weight'])*100:.1f}%): {t['reason']}"
                        for t in tickers
                    ])
                    
                    # 메시지 추가
                    load_msg = (
                        f"📂 **{selected_key}** 포트폴리오를 불러왔습니다.\n\n"
                        f"🚀 **추천 포트폴리오 제안**\n\n"
                        f"{rationale}\n\n"
                        f"{tickers_desc}\n\n"
                        "📊 **시뮬레이션**을 보시려면 '시뮬레이션 보여줘'라고 말씀해주세요."
                    )
                    st.session_state.messages.append({"role": "assistant", "content": load_msg})
                    st.rerun()
            
            with col2:
                if st.button("🗑️ 삭제", key=f"delete_portfolio_{selected_key}"):
                    # DB에서 삭제
                    rec_id = options[selected_key]["id"]
                    import sqlite3
                    from data.db import get_conn
                    with get_conn() as conn:
                        conn.execute("DELETE FROM portfolio_recommendations WHERE rec_id = ?", (rec_id,))
                        conn.commit()
                    st.success("✅ 포트폴리오가 삭제되었습니다.")
                    st.rerun()


    # ---------------------------------------------------------
    # 📄 저장된 리포트
    # ---------------------------------------------------------
    st.divider()
    st.markdown("### 📄 저장된 리포트")
    
    import os
    report_dir = "reports"
    if os.path.exists(report_dir):
        # 파일 목록 가져오기 (PDF만)
        files = [f for f in os.listdir(report_dir) if f.endswith(".pdf")]
        files.sort(reverse=True) # 최신순 정렬
        
        if not files:
            st.caption("저장된 리포트가 없습니다.")
        else:
            selected_report = st.selectbox("다운로드할 리포트 선택", ["선택하세요"] + files)
            
            if selected_report != "선택하세요":
                file_path = os.path.join(report_dir, selected_report)
                with open(file_path, "rb") as f:
                    file_bytes = f.read()
                
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.download_button(
                        label="💾 파일 다운로드",
                        data=file_bytes,
                        file_name=selected_report,
                        mime="application/pdf",
                        key=f"download_report_{selected_report}"
                    )
                
                with col2:
                    if st.button("🗑️ 삭제", key=f"delete_report_{selected_report}"):
                        os.remove(file_path)
                        st.success("✅ 리포트가 삭제되었습니다.")
                        st.rerun()
    else:
        st.caption("저장된 리포트가 없습니다.")


    # ---------------------------------------------------------
    # 대화 초기화
    # ---------------------------------------------------------
    st.caption("---")
    if st.button("🔄 대화 내용만 초기화"):
        st.session_state.messages = []
        # ✅ 상태 완전 초기화 (현재 유저 유지)
        uid = st.session_state.rulepilot_state.get("user_id", "streamlit_user")
        st.session_state.rulepilot_state = {
            "user_id": uid,
            "user_text": "",
            "interview_step": None,
            "output_text": ""
        }
        
        # 앱 인스턴스 재생성
        st.session_state.app_instance = build_app()
        
        # 초기화 메시지
        st.session_state.messages.append({"role": "assistant", "content": "대화가 초기화되었습니다. 처음부터 다시 시작할게요! 😊"})
        st.rerun()

    st.divider()
    with st.expander("🛠️ 디버그 정보"):
        st.json(st.session_state.rulepilot_state)

# =========================================================
# PDF 리포트 생성 함수
# =========================================================
def generate_pdf_report(user_name, portfolio, sim_result):
    from fpdf import FPDF
    import os

    class PDF(FPDF):
        def header(self):
            # 폰트 추가 (NanumGothic)
            # 폰트 파일이 같은 디렉토리에 있다고 가정
            font_path = os.path.join(os.getcwd(), "NanumGothic.ttf")
            if os.path.exists(font_path):
                self.add_font("NanumGothic", "", font_path, uni=True)
                self.set_font("NanumGothic", "", 10)
            else:
                self.set_font("Arial", "", 10) # Fallback
                
            self.cell(0, 10, f"RulePilot Investment Report - Prepared for {user_name}", 0, 1, 'R')
            self.ln(10)

        def footer(self):
            self.set_y(-15)
            self.set_font("Arial", "I", 8)
            self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    pdf = PDF()
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)
    pdf.add_page()
    
    # ========== Title Section with Background ==========
    pdf.set_fill_color(41, 128, 185)  # Blue background
    pdf.set_text_color(255, 255, 255)  # White text
    pdf.set_font("NanumGothic", "", 28)
    pdf.cell(0, 20, "RulePilot Portfolio Report", 0, 1, 'C', fill=True)
    
    # Subtitle
    pdf.set_font("NanumGothic", "", 12)
    pdf.set_fill_color(52, 152, 219)  # Lighter blue
    pdf.cell(0, 8, f"Prepared for {user_name}", 0, 1, 'C', fill=True)
    pdf.set_text_color(0, 0, 0)  # Reset to black
    pdf.ln(15)
    
    # ========== Section 1: Executive Summary ==========
    # Section header with background
    pdf.set_fill_color(236, 240, 241)  # Light gray background
    pdf.set_font("NanumGothic", "", 16)
    pdf.cell(0, 10, "1. Executive Summary", 0, 1, 'L', fill=True)
    pdf.ln(5)
    
    pdf.set_font("NanumGothic", "", 11)
    rationale_text = str(portfolio.get("rationale", "No rationale provided."))
    pdf.multi_cell(0, 7, rationale_text)
    pdf.ln(10)
    
    # Divider line
    pdf.set_draw_color(189, 195, 199)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(10)

    # ========== Section 2: Portfolio Allocation ==========
    pdf.set_fill_color(236, 240, 241)
    pdf.set_font("NanumGothic", "", 16)
    pdf.cell(0, 10, "2. Asset Allocation", 0, 1, 'L', fill=True)
    pdf.ln(5)
    
    pdf.set_font("NanumGothic", "", 10)
    for ticker in portfolio.get("tickers", []):
        symbol = ticker['symbol']
        weight = float(ticker['weight'])*100
        reason = ticker['reason']
        
        # Ticker symbol with highlight
        pdf.set_fill_color(255, 243, 205)  # Light yellow
        pdf.set_font("NanumGothic", "", 11)
        pdf.cell(40, 7, f"  {symbol}", 0, 0, 'L', fill=True)
        
        # Weight percentage
        pdf.set_fill_color(230, 247, 255)  # Light blue
        pdf.cell(25, 7, f"{weight:.1f}%", 0, 1, 'C', fill=True)
        
        # Reason (indented, smaller font)
        pdf.set_font("NanumGothic", "", 9)
        if len(reason) > 80:
            reason = reason[:77] + "..."
        pdf.set_x(25)
        pdf.multi_cell(0, 5, f"  → {reason}")
        pdf.ln(3)
    
    pdf.ln(5)
    # Divider line
    pdf.set_draw_color(189, 195, 199)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(10)

    # ========== Section 3: Crisis Stress Test ==========
    crisis_data = sim_result.get("crisis_test", [])
    if crisis_data:
        pdf.set_fill_color(236, 240, 241)
        pdf.set_font("NanumGothic", "", 16)
        pdf.cell(0, 10, "3. Crisis Stress Test (Historical)", 0, 1, 'L', fill=True)
        pdf.ln(5)
        
        pdf.set_font("NanumGothic", "", 10)
        for c in crisis_data:
            if c.get("msg") == "성공":
                res = "PASS" if c['my_mdd'] > c['market_mdd'] else "WARNING"
                name = c['name']
                
                # Box around each crisis test
                pdf.set_draw_color(189, 195, 199)
                y_start = pdf.get_y()
                
                # Crisis name
                pdf.set_font("NanumGothic", "", 11)
                pdf.cell(0, 6, f"[{name}]")
                pdf.ln()
                
                # MDD comparison
                pdf.set_font("NanumGothic", "", 9)
                pdf.set_x(pdf.l_margin + 5)
                pdf.cell(0, 5, f"  My MDD: {c['my_mdd']:.1%} vs Market: {c['market_mdd']:.1%}")
                pdf.ln()
                
                # Result with color
                pdf.set_x(pdf.l_margin + 5)
                if res == "PASS":
                    pdf.set_text_color(39, 174, 96)  # Green
                else:
                    pdf.set_text_color(231, 76, 60)  # Red
                pdf.set_font("NanumGothic", "", 10)
                pdf.cell(0, 5, f"  Result: {res}")
                pdf.set_text_color(0, 0, 0)  # Reset to black
                pdf.ln(5)
                
                # Draw border around the item
                y_end = pdf.get_y()
                pdf.rect(pdf.l_margin, y_start, 180, y_end - y_start)
                pdf.ln(3)
        
        pdf.ln(5)

    # ========== Disclaimer Box ==========
    pdf.set_draw_color(231, 76, 60)  # Red border
    pdf.set_fill_color(255, 235, 235)  # Light red background
    
    y_before = pdf.get_y()
    pdf.set_font("NanumGothic", "", 9)
    pdf.multi_cell(0, 5, "⚠️ Disclaimer: This report is generated by AI (RulePilot). Past performance is not indicative of future results. Investment involves risk.", border=1, fill=True)
    
    # Bytes return

    # Bytes 리턴 (파일 저장은 별도로 처리)
    # fpdf2 newer versions return bytes/bytearray directly
    output = pdf.output(dest='S')
    if isinstance(output, (bytes, bytearray)):
        return bytes(output)  # Convert to bytes if needed
    else:
        return output.encode('latin-1')

# 메인 채팅 인터페이스
st.title("RulePilot AI 🤖")

# 차트 그리기 함수
def draw_simulation_chart(data):
    import pandas as pd
    
    # 1. 과거 데이터
    hist_df = pd.DataFrame(data["history"])
    hist_df["date"] = pd.to_datetime(hist_df["date"])
    hist_df = hist_df.set_index("date")
    hist_df = hist_df.rename(columns={"value": "Historical"})
    
    # 2. 미래 데이터 (Mean, Upper, Lower)
    fore_df = pd.DataFrame(data["forecast"])
    fore_df["date"] = pd.to_datetime(fore_df["date"])
    fore_df = fore_df.set_index("date")
    
    st.subheader("📈 포트폴리오 가치 시뮬레이션")
    
    # 과거와 미래를 연결하여 시각화
    # 탭으로 구분
    tab1, tab2, tab3 = st.tabs(["전체 추세", "미래 예측 상세", "📉 위기 상황 스트레스 테스트"])
    
    with tab1:
        # 전체를 잇는 라인 차트 (Mean 기준)
        # 과거 마지막 값과 미래 첫 값이 연결되게
        # combined = pd.concat([hist_df["Historical"], fore_df["mean"].rename("Forecast (Mean)")], axis=1)
        # st.line_chart(combined)
        
        # ✅ Plotly를 이용한 인터랙티브 차트 구현
        import plotly.graph_objects as go
        
        hist_trace = go.Scatter(
            x=hist_df.index, 
            y=hist_df["Historical"],
            mode='lines',
            name='Historical (과거 성과)',
            line=dict(color='royalblue', width=2)
        )
        
        fore_trace = go.Scatter(
            x=fore_df.index,
            y=fore_df["mean"],
            mode='lines',
            name='Forecast (미래 예측)',
            line=dict(color='firebrick', dash='dash', width=2)
        )
        
        # 신뢰구간 (90%)
        upper_trace = go.Scatter(
            x=fore_df.index,
            y=fore_df["upper"],
            mode='lines',
            line=dict(width=0),
            showlegend=False,
            hoverinfo='skip'
        )
        
        lower_trace = go.Scatter(
            x=fore_df.index,
            y=fore_df["lower"],
            mode='lines',
            fill='tonexty', # fill area between trace0 and trace1
            fillcolor='rgba(255, 0, 0, 0.1)',
            line=dict(width=0),
            name='90% Range',
            hoverinfo='skip'
        )
        
        layout = go.Layout(
            title="포트폴리오 가치 변화 (과거 + 미래)",
            xaxis=dict(
                title="날짜", 
                showgrid=True,
                rangeslider=dict(visible=True), # 하단 범위 슬라이더
                type="date"
            ),
            yaxis=dict(title="가치 (Base=100)", showgrid=True),
            hovermode="x unified", # 마우스 오버 시 X축 기준 정보 표시
            legend=dict(x=0, y=1.1, orientation="h"),
            height=500
        )
        
        fig = go.Figure(data=[hist_trace, upper_trace, lower_trace, fore_trace], layout=layout)
        st.plotly_chart(fig, use_container_width=True)
        
    with tab3:
        st.markdown("### 🌪️ 과거 경제 위기 시뮬레이션")
        st.caption("만약 이 포트폴리오를 과거 위기 때 보유했다면 어땠을까요?")
        
        crisis_data = data.get("crisis_test", [])
        if not crisis_data:
            st.info("스트레스 테스트 데이터가 없습니다.")
        else:
            for item in crisis_data:
                msg = item.get("msg", "")
                if msg != "성공":
                    continue
                    
                name = item["name"]
                period = item["period"]
                my_mdd = item["my_mdd"]
                mkt_mdd = item["market_mdd"]
                my_ret = item["my_return"]
                mkt_ret = item["market_return"]
                
                # 방어율 계산 (시장이 덜 떨어졌으면 방어 성공 아님)
                # MDD는 음수. 예: 내꺼 -0.1, 시장 -0.5 -> 방어 성공
                is_safe = my_mdd > mkt_mdd
                
                st.markdown(f"#### **{name}** ({period})")
                
                c1, c2 = st.columns(2)
                with c1:
                    st.metric("내 포트폴리오 MDD", f"{my_mdd:.1%}", delta_color="normal")
                    st.metric("내 수익률", f"{my_ret:.1%}")
                with c2:
                    st.metric("시장 (S&P500) MDD", f"{mkt_mdd:.1%}", delta_color="inverse")
                    st.metric("시장 수익률", f"{mkt_ret:.1%}")
                    
                if is_safe:
                    st.success(f"✅ **방어 성공!** 시장이 {mkt_mdd:.1%} 하락할 때, {my_mdd:.1%}로 막아냈습니다.")
                else:
                    st.warning(f"⚠️ **주의**: 시장보다 변동성이 컸습니다. ({my_mdd:.1%} vs {mkt_mdd:.1%})")
                
    # ✅ PDF 리포트 다운로드 버튼
    st.divider()
    
    # 데이터 준비
    port_data = st.session_state.rulepilot_state.get("recommended_portfolio", {})
    if port_data:
         user = st.session_state.rulepilot_state.get("user_id", "User")
         pdf_bytes = generate_pdf_report(user, port_data, data)
         
         col1, col2 = st.columns(2)
         
         with col1:
             st.download_button(
                 label="📄 리포트 다운로드 (PDF)",
                 data=pdf_bytes,
                 file_name=f"RulePilot_Report_{user}.pdf",
                 mime="application/pdf",
             )
         
         with col2:
             if st.button("💾 리포트 저장하기"):
                 # 파일 저장 로직
                 import datetime
                 import os
                 report_dir = "reports"
                 if not os.path.exists(report_dir):
                     os.makedirs(report_dir)
                     
                 # 파일명: YYYYMMDD_HHMM_User.pdf
                 filename = f"{datetime.datetime.now().strftime('%Y%m%d_%H%M')}_{user}.pdf"
                 filepath = os.path.join(report_dir, filename)
                 
                 with open(filepath, "wb") as f:
                     f.write(pdf_bytes)
                 
                 st.success(f"✅ 리포트가 저장되었습니다: {filename}")
                 st.rerun()
        
    with tab2:
        # 미래 예측 범위 (Area chart)
        # 상/하단 범위를 보여주기 위해 데이터 가공
        # Streamlit area chart는 stack되므로 주의. 
        # 여기선 간단히 3개 라인으로 표시
        st.line_chart(fore_df[["upper", "mean", "lower"]])
        
        st.info("""
        **📊 그래프 보는 법**
        
        * **Mean (가운데 선)**: 가장 가능성이 높은 **'평균적인 예상 경로'**입니다.
        * **Upper (위쪽 선)**: 시장 상황이 **아주 좋을 때** 기대할 수 있는 수익입니다. (상위 5%)
        * **Lower (아래쪽 선)**: 시장 상황이 **아주 나쁠 때** 방어할 수 있는 하한선입니다. (하위 5%)
        
        👉 즉, 미래의 내 자산은 **90%의 확률로 이 두 선(Upper ~ Lower) 사이**에서 움직일 것으로 예상됩니다.
        """)


# 채팅 기록 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        # 차트 데이터가 있으면 그리기
        if message.get("type") == "chart" and "data" in message:
            draw_simulation_chart(message["data"])

# 사용자 입력 처리
if prompt := st.chat_input("메시지를 입력하세요..."):
    # 사용자 메시지 표시
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 봇 응답 처리
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        # RulePilot 실행
        current_state = st.session_state.rulepilot_state
        current_state["user_text"] = prompt
        
        # 시뮬레이션 데이터 초기화 (이번 턴에 새로 생기는지 확인 위함)
        if "simulation_data" in current_state:
            del current_state["simulation_data"]

        try:
            # ✅ 오래 걸리는 작업(LLM, 시뮬레이션) 시 스피너 표시
            with st.spinner("AI가 생각 중입니다... 🧠"):
                out = st.session_state.app_instance.invoke(current_state)
            
            if isinstance(out, dict):
                st.session_state.rulepilot_state.update(out)
                bot_response = st.session_state.rulepilot_state.get("output_text", "(응답 없음)")
            else:
                bot_response = "(시스템 오류: 응답 형식이 올바르지 않습니다.)"

        except Exception as e:
            bot_response = f"오류가 발생했습니다: {str(e)}"
            st.error(bot_response)

        # 응답 표시
        message_placeholder.markdown(bot_response)
        
        # 메시지 저장
        msg_obj = {"role": "assistant", "content": bot_response}
        
        # 시뮬레이션 데이터가 새로 생성되었으면 차트 추가
        if "simulation_data" in st.session_state.rulepilot_state:
            sim_data = st.session_state.rulepilot_state["simulation_data"]
            # 바로 그리기
            draw_simulation_chart(sim_data)
            # 저장용 메시지에 데이터 추가
            msg_obj["type"] = "chart"
            msg_obj["data"] = sim_data
            
        st.session_state.messages.append(msg_obj)
