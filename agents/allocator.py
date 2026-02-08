from __future__ import annotations
from state_schema import Profile, MonthSignal, PortfolioPlan

def build_portfolio_plan(profile: Profile, signal: MonthSignal) -> PortfolioPlan:
    budget = int(profile.monthly_budget_krw)
    equity_amt = int(round(budget * float(signal.equity_weight)))
    safe_amt = budget - equity_amt
    return PortfolioPlan(
        equity_amount_krw=equity_amt,
        safe_amount_krw=safe_amt,
        equity_bucket="Broad Equity Basket",
        safe_bucket="Safe Asset Basket",
    )
