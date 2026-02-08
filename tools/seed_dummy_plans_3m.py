from __future__ import annotations

from data.db import ensure_user, load_active_profile, upsert_monthly_plan

def _make_plan(as_of: str, yyyymm: str, eq_w: float, sf_w: float, eq_qty: float, sf_qty: float, reasons: list[str]):
    return {
        "as_of": as_of,  # 사람이 보기 좋은 날짜(원하는 형식)
        "generated_at": f"{as_of}T12:00:00",

        "equity_weight": eq_w,
        "safe_weight": sf_w,

        "equity_ticker": "QQQ",
        "safe_ticker": "BIL",

        "fx_krw_per_usd": 1350,

        # (선택) 금액 예시
        "equity_amount_krw": 45000,
        "safe_amount_krw": 10000,

        # 주문 - history가 equity_order/safe_order 또는 orders 둘 다 읽을 수 있게 넣기
        "equity_order": {"ticker": "QQQ", "qty": eq_qty, "usd": 30.0},
        "safe_order": {"ticker": "BIL", "qty": sf_qty, "usd": 7.0},
        "orders": {
            "equity": {"ticker": "QQQ", "qty": eq_qty, "usd": 30.0},
            "safe": {"ticker": "BIL", "qty": sf_qty, "usd": 7.0},
        },

        "reason_codes": reasons,
        "note": "seed dummy plans for 3m history test",
    }

def main():
    user_id = ensure_user("local")
    profile_id, _ = load_active_profile(user_id)

    seeds = [
        # (as_of, yyyymm, eq_w, sf_w, eq_qty, sf_qty, reasons)
        ("2025-10-05", "202510", 0.70, 0.30, 0.0400, 0.0900, ["RISK_OFF", "VOL_HIGH"]),
        ("2025-11-05", "202511", 0.75, 0.25, 0.0450, 0.0850, ["TREND_UP"]),
        ("2025-12-05", "202512", 0.82, 0.18, 0.0500, 0.0800, ["TREND_UP", "VOL_OK"]),
    ]

    for as_of, yyyymm, eq_w, sf_w, eq_qty, sf_qty, reasons in seeds:
        plan = _make_plan(as_of, yyyymm, eq_w, sf_w, eq_qty, sf_qty, reasons)
        upsert_monthly_plan(
            user_id=user_id,
            profile_id=profile_id,
            yyyymm=yyyymm,
            plan=plan,
        )
        print(f"✅ Seeded {yyyymm} ({as_of})")

    print("🎉 Done. Now try: '지난 달 계획 보여줘' and '지난 3개월 투자 요약'")

if __name__ == "__main__":
    main()
