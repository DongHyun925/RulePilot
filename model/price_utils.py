from __future__ import annotations
import yfinance as yf

def get_latest_price_usd(ticker: str) -> float:
    """
    최근 종가(USD)를 가져옴. (간단/안정)
    """
    t = yf.Ticker(ticker)
    hist = t.history(period="5d", interval="1d")
    if hist is None or hist.empty:
        raise RuntimeError(f"가격을 못 가져왔어요: {ticker}")
    price = float(hist["Close"].iloc[-1])
    return price
