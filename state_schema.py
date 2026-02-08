from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any


@dataclass
class Profile:
    monthly_budget_krw: int | None = None
    horizon_months: int | None = None
    risk_level: str | None = None  # conservative|neutral|aggressive
    emergency_fund_ok: bool | None = None


@dataclass
class Policy:
    buy_rule: str = "매달 1회, 동일한 날짜에 정기매수"
    rebalance_rule: str = "분기 1회 점검"
    ban_rules: List[str] = field(default_factory=lambda: ["뉴스 보고 즉흥매수 금지", "레버리지/빚투 금지"])


@dataclass
class MonthSignal:
    equity_weight: float = 0.7
    safe_weight: float = 0.3
    reason_codes: List[str] = field(default_factory=lambda: ["DEFAULT"])


@dataclass
class PortfolioPlan:
    equity_amount_krw: int = 0
    safe_amount_krw: int = 0
    equity_bucket: str = "Broad Equity Basket"
    safe_bucket: str = "Safe Asset Basket"


def to_dict(obj) -> Dict[str, Any]:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    return dict(obj)
