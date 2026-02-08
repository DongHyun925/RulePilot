from __future__ import annotations
from typing import Optional, Tuple, Dict, Any, List

from data.db import get_plan, list_recent_plans, yyyymm_prev


def fetch_last_month_plan(user_id: str, profile_id: Optional[int]) -> Tuple[str, Optional[Dict[str, Any]]]:
    yyyymm = yyyymm_prev(1)
    plan = get_plan(user_id, profile_id, yyyymm)
    return yyyymm, plan


def fetch_recent_plans(user_id: str, profile_id: Optional[int], limit: int = 3) -> List[Dict[str, Any]]:
    return list_recent_plans(user_id, profile_id, limit=limit)
