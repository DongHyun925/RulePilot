from __future__ import annotations
import pandas as pd
import yfinance as yf

def load_price_history(ticker: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    """
    yfinance로 가격 데이터 다운로드.
    반환: Date index, columns: Open, High, Low, Close, Adj Close, Volume
    """
    df = yf.download(ticker, period=period, interval=interval, auto_adjust=False, progress=False)
    if df is None or df.empty:
        raise RuntimeError(f"가격 데이터를 못 가져왔어요: {ticker}")
    df = df.dropna()
    return df
