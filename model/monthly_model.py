from __future__ import annotations
import numpy as np
import pandas as pd
from state_schema import MonthSignal
from model.data_loader import load_price_history

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def calc_trend_score(close: pd.Series) -> float:
    """
    간단 트렌드 점수:
    - 종가가 200일 이동평균 위면 +0.6
    - 아래면 -0.6
    """
    # ✅ 혹시 Series가 아니라 DataFrame으로 들어오면 마지막 컬럼/첫 컬럼을 Series로 강제
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    close = pd.to_numeric(close, errors="coerce").dropna()
    ma200 = close.rolling(200).mean().dropna()
    if ma200.empty:
        return 0.0

    latest = float(close.iloc[-1])
    latest_ma = float(ma200.iloc[-1])

    return 0.6 if latest > latest_ma else -0.6

def calc_vol_score(close: pd.Series) -> float:
    """
    변동성 점수(0~1):
    - 최근 20일 일간 수익률 표준편차를 이용해 스케일링
    """
    ret = close.pct_change().dropna()
    if len(ret) < 21:
        return 0.0
    vol20 = ret.tail(20).std()  # 대략 0.01~0.05 범위가 흔함
    # 0.01 -> 0.0, 0.05 -> 1.0 정도로 매핑(대충)
    score = (vol20 - 0.01) / (0.05 - 0.01)
    return float(clamp(score, 0.0, 1.0))

def run_monthly_model_from_market(ticker: str = "QQQ") -> MonthSignal:
    """
    월 1회 실행: 시장 데이터 기반으로 '이번 달 주식 비중' 산출
    """
    df = load_price_history(ticker=ticker, period="2y", interval="1d")

    # ✅ yfinance가 컬럼을 MultiIndex로 주는 경우가 있어 단일 컬럼으로 정리
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)

    # close 추출 (Series로 강제)
    if "Adj Close" in df.columns:
        close = df["Adj Close"]
    elif "Close" in df.columns:
        close = df["Close"]
    else:
        # 최후의 수단: 마지막 열
        close = df.iloc[:, -1]

    # 혹시라도 DataFrame이면 Series로
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    close = pd.to_numeric(close, errors="coerce").dropna()

    trend_score = calc_trend_score(close)
    vol_score = calc_vol_score(close)

    base = 0.7
    equity = base + 0.2 * trend_score - 0.4 * vol_score
    equity = clamp(equity, 0.2, 1.0)
    safe = 1.0 - equity

    reasons = []
    if vol_score >= 0.6:
        reasons.append("VOL_SPIKE")
    if trend_score >= 0.3:
        reasons.append("TREND_UP")
    if trend_score <= -0.3:
        reasons.append("TREND_DOWN")
    if not reasons:
        reasons = ["DEFAULT"]

    return MonthSignal(equity_weight=float(equity), safe_weight=float(safe), reason_codes=reasons)

def simulate_portfolio_history(portfolio: dict, months: int = 120) -> dict:
    """
    포트폴리오의 과거 성과(백테스트)와 미래 예측(몬테카를로)을 수행.
    portfolio: {ticker: weight, ...} 예: {"QQQ": 0.5, "SCHD": 0.5}
    months: 미래 예측 기간 (개월)
    """
    
    # 1. 과거 데이터 로드 (최대 10년)
    hist_prices = pd.DataFrame()
    
    for ticker in portfolio.keys():
        try:
            df = load_price_history(ticker=ticker, period="10y", interval="1d")
            # MultiIndex 정리
            if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
                 df.columns = df.columns.get_level_values(0)
            
            # Close 추출
            col = "Adj Close" if "Adj Close" in df.columns else "Close"
            if col in df.columns:
               s = df[col]
            else:
               s = df.iloc[:, -1]
            
            s = pd.to_numeric(s, errors="coerce")
            s.name = ticker
            hist_prices = pd.merge(hist_prices, s, left_index=True, right_index=True, how="outer") if not hist_prices.empty else s.to_frame()
            
        except Exception as e:
            print(f"Error loading {ticker}: {e}")

    if hist_prices.empty:
        return {"error": "No data found for tickers"}

    hist_prices = hist_prices.ffill().dropna()
    
    # 2. 백테스트 (일별 리밸런싱 가정 - 단순화)
    # 초기 자본 1.0
    daily_ret = hist_prices.pct_change().dropna()
    
    # 포트폴리오 수익률 = sum(개별수익률 * 비중)
    # 비중 정규화
    total_w = sum(portfolio.values())
    weights = {k: v/total_w for k, v in portfolio.items()}
    
    port_ret = calculate_portfolio_returns(daily_ret, weights)
    
    # 누적 수익률 (Base 100)
    cum_ret = (1 + port_ret).cumprod() * 100
    
    # 과거 데이터 JSON 변환 (날짜는 문자열로)
    history_data = []
    for date, val in cum_ret.items():
        history_data.append({"date": date.strftime("%Y-%m-%d"), "value": float(val)})

    # 3. 몬테카를로 시뮬레이션 (미래)
    # 연율화 수익률/변동성 (최근 1~2년 트렌드 반영을 위해 최근 데이터 가중할 수도 있으나 여기선 전체 평균)
    # "계속 상승" 요청을 반영하여, 과거 평균 수익률이 마이너스면 0으로 보정 (Structural Growth 가정)
    mu = port_ret.mean() * 252 # 연수익률
    sigma = port_ret.std() * np.sqrt(252) # 연변동성
    
    # 보정: 우상향 포트폴리오 가정 (최소 연 3% 성장 가정)
    mu = max(mu, 0.03)

    last_val = cum_ret.iloc[-1]
    last_date = cum_ret.index[-1]
    
    simulation_days = int(months * 30.5)
    num_simulations = 100
    dt = 1/252
    
    sim_paths = []
    
    for _ in range(num_simulations):
        path = [last_val]
        curr = last_val
        for _ in range(simulation_days):
            # GBM: dS = S * (mu*dt + sigma*dW)
            shock = np.random.normal(0, 1)
            drift = (mu - 0.5 * sigma**2) * dt
            diffusion = sigma * np.sqrt(dt) * shock
            curr *= np.exp(drift + diffusion)
            path.append(curr)
        sim_paths.append(path)
        
    sim_paths = np.array(sim_paths)
    
    # 분위수 계산 (Mean, Upper 95%, Lower 5%)
    mean_path = np.mean(sim_paths, axis=0)
    upper_path = np.percentile(sim_paths, 95, axis=0)
    lower_path = np.percentile(sim_paths, 5, axis=0)
    
    forecast_data = []
    future_dates = pd.date_range(start=last_date, periods=simulation_days+1, freq="B") # Business Day
    
    for i in range(len(future_dates)): # 첫날(과거 마지막날) 포함
        if i >= len(mean_path): break
        forecast_data.append({
            "date": future_dates[i].strftime("%Y-%m-%d"),
            "mean": float(mean_path[i]),
            "upper": float(upper_path[i]),
            "lower": float(lower_path[i])
        })
        
    return {
        "history": history_data,
        "forecast": forecast_data,
        "metrics": {
            "cagr_history": float((cum_ret.iloc[-1]/100)**(252/len(cum_ret)) - 1),
            "vol_history": float(sigma)
        }
    }

def calculate_portfolio_returns(daily_ret_df, weights_dict):
    """
    daily_ret_df: DataFrame of ticker returns
    weights_dict: {ticker: weight}
    """
    port_ret = pd.Series(0.0, index=daily_ret_df.index)
    for ticker, w in weights_dict.items():
        if ticker in daily_ret_df.columns:
            port_ret += daily_ret_df[ticker] * w
    return port_ret

def backtest_crisis_scenarios(portfolio: dict) -> list[dict]:
    """
    주요 경제 위기 구간에서의 포트폴리오 vs 시장(SPY) 성과 비교
    """
    scenarios = [
        {"name": "2008 금융위기", "start": "2007-10-01", "end": "2009-03-09"},
        {"name": "2020 코로나 팬데믹", "start": "2020-02-19", "end": "2020-03-23"},
        {"name": "2022 고금리 하락장", "start": "2022-01-03", "end": "2022-10-14"},
    ]
    
    results = []
    
    # SPY 데이터 로드 (벤치마크)
    spy_df = load_price_history("SPY", period="20y", interval="1d")
    if hasattr(spy_df.columns, "nlevels") and spy_df.columns.nlevels > 1:
        spy_df.columns = spy_df.columns.get_level_values(0)
    
    col = "Adj Close" if "Adj Close" in spy_df.columns else "Close"
    spy_close = pd.to_numeric(spy_df[col], errors="coerce").ffill().dropna()

    # 포트폴리오 티커 데이터 로드 (캐싱된 것 활용 전제하거나 다시 로드)
    # 여기선 편의상 다시 로드 (효율화 필요시 개선)
    port_closes = pd.DataFrame()
    for ticker in portfolio.keys():
        try:
            # 기간을 넉넉히 20년 잡음
            df = load_price_history(ticker, period="20y", interval="1d")
            if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
                 df.columns = df.columns.get_level_values(0)
            c = df["Adj Close" if "Adj Close" in df.columns else "Close"]
            port_closes[ticker] = pd.to_numeric(c, errors="coerce")
        except:
            pass
            
    port_closes = port_closes.ffill().dropna()
    
    # 비중 정규화
    total_w = sum(portfolio.values())
    weights = {k: v/total_w for k, v in portfolio.items()}

    for sc in scenarios:
        s_date = sc["start"]
        e_date = sc["end"]
        
        # 해당 구간 데이터 슬라이싱
        sub_spy = spy_close.loc[s_date:e_date]
        sub_port = port_closes.loc[s_date:e_date]
        
        if sub_spy.empty or sub_port.empty:
            results.append({
                "name": sc["name"],
                "period": f"{s_date}~{e_date}",
                "my_return": 0.0, "market_return": 0.0,
                "my_mdd": 0.0, "market_mdd": 0.0,
                "msg": "데이터 부족"
            })
            continue
            
        # 1. 시장 성과
        spy_ret = sub_spy.iloc[-1] / sub_spy.iloc[0] - 1
        # MDD
        roll_max = sub_spy.cummax()
        drawdown = sub_spy / roll_max - 1
        spy_mdd = drawdown.min()
        
        # 2. 내 포트폴리오 성과
        # 일별 수익률 계산 후 가중합
        # 데이터가 없는 티커가 있을 수 있음 (예: 2008년에 없는 ETF)
        # 이 경우 해당 티커 비중만큼 현금 보유(수익률 0) 가정하거나, 
        # 가능한 티커끼리만 리스케일링. 여기선 '가능한 티커 리스케일링' 방식 적용.
        valid_tickers = [t for t in weights.keys() if t in sub_port.columns]
        
        if not valid_tickers:
             results.append({
                "name": sc["name"],
                "period": f"{s_date}~{e_date}",
                "my_return": 0.0, "market_return": spy_ret,
                "my_mdd": 0.0, "market_mdd": spy_mdd,
                "msg": "데이터 부족 (상장 전)"
            })
             continue
             
        # 유효 티커 비중 재산정
        sub_total_w = sum(weights[t] for t in valid_tickers)
        sub_weights = {t: weights[t]/sub_total_w for t in valid_tickers}
        
        daily_ret = sub_port[valid_tickers].pct_change().dropna()
        p_ret_series = calculate_portfolio_returns(daily_ret, sub_weights)
        
        # 누적 수익률
        cum_p = (1 + p_ret_series).cumprod()
        my_return = cum_p.iloc[-1] - 1
        
        # MDD
        roll_max_p = cum_p.cummax()
        dd_p = cum_p / roll_max_p - 1
        my_mdd = dd_p.min()
        
        results.append({
            "name": sc["name"],
            "period": f"{s_date}~{e_date}",
            "my_return": float(my_return),
            "market_return": float(spy_ret),
            "my_mdd": float(my_mdd),
            "market_mdd": float(spy_mdd),
            "msg": "성공"
        })
        
    return results