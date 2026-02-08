from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any
from model.price_utils import get_latest_price_usd

@dataclass
class OrderPlan:
    ticker: str
    budget_krw: int
    fx_krw_per_usd: int
    price_usd: float
    shares: float
    used_krw: int
    leftover_krw: int

def build_order_plan(ticker: str, budget_krw: int, fx_krw_per_usd: int = 1350, allow_fractional: bool = True) -> Dict[str, Any]:
    """
    예산(원) -> 환율 -> USD 가격 -> 살 수 있는 주 수 계산
    allow_fractional=True면 소수점 주식 허용(가정)
    """
    price = get_latest_price_usd(ticker)
    budget_usd = budget_krw / fx_krw_per_usd

    if allow_fractional:
        shares = budget_usd / price
        used_krw = int(round(shares * price * fx_krw_per_usd))
        leftover = max(0, budget_krw - used_krw)
    else:
        shares = int(budget_usd // price)
        used_krw = int(round(shares * price * fx_krw_per_usd))
        leftover = max(0, budget_krw - used_krw)

    return {
        "ticker": ticker,
        "budget_krw": int(budget_krw),
        "fx_krw_per_usd": int(fx_krw_per_usd),
        "price_usd": float(price),
        "shares": float(shares),
        "used_krw": int(used_krw),
        "leftover_krw": int(leftover),
    }
