from __future__ import annotations

from pprint import pprint

# ✅ 실행 위치에 따라 모듈이 안 잡히면 -m로 실행하세요:
# python -m tools.verify_dummy_history

import data.db as db
from data.db import ensure_user, load_active_profile, upsert_monthly_plan, fetch_monthly_plans

def main():
    print("[DEBUG] data.db module file =", db.__file__)
    # db.py에 DB 경로 상수가 있으면 같이 찍힘 (없으면 None)
    print("[DEBUG] DB_PATH attr =", getattr(db, "DB_PATH", None))

    user_id = ensure_user("local")
    profile_id, _ = load_active_profile(user_id)

    # 1) 더미 1건 upsert
    payload = {
        "as_of": "2025-12-05",
        "equity_weight": 0.82,
        "safe_weight": 0.18,
        "equity_ticker": "QQQ",
        "safe_ticker": "BIL",
        "equity_order": {"ticker": "QQQ", "qty": 0.05, "usd": 33.33},
        "safe_order": {"ticker": "BIL", "qty": 0.08, "usd": 6.67},
        "orders": {
            "equity": {"ticker": "QQQ", "qty": 0.05, "usd": 33.33},
            "safe": {"ticker": "BIL", "qty": 0.08, "usd": 6.67},
        },
        "reason_codes": ["TREND_UP", "VOL_OK"],
    }

    upsert_monthly_plan(
        user_id=user_id,
        profile_id=profile_id,
        yyyymm="202512",
        plan=payload,
    )
    print("✅ upsert done")

    # 2) 즉시 조회
    rows = fetch_monthly_plans(user_id=user_id, months=12) or []
    print("[DEBUG] fetch_monthly_plans len =", len(rows))
    print("[DEBUG] yyyymm list =", [r.get("yyyymm") for r in rows])

    target = next((r for r in rows if str(r.get("yyyymm")) == "202512"), None)
    print("[DEBUG] 202512 row =")
    from pprint import pprint
    pprint(target)

if __name__ == "__main__":
    main()
