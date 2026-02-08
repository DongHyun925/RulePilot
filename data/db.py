# data/db.py
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "rulepilot.sqlite3"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def migrate() -> None:
    """
    DB 테이블 생성/업데이트(간단 마이그레이션).
    - users: 유저 존재 보장
    - profiles: 여러 개 프로필 + active 관리
    - monthly_plans: 월별 계획 히스토리
    """
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
        )

        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS profiles (
            profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '기본 설정',
            is_active INTEGER NOT NULL DEFAULT 0,
            profile_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
        """
        )

        cur.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_profiles_user_active
        ON profiles(user_id, is_active)
        """
        )

        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS monthly_plans (
            plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            profile_id INTEGER,
            yyyymm TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, yyyymm, profile_id),
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(profile_id) REFERENCES profiles(profile_id)
        )
        """
        )

        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS portfolio_recommendations (
            rec_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            profile_id INTEGER,
            rec_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(profile_id) REFERENCES profiles(profile_id)
        )
        """
        )

        conn.commit()


def ensure_user(user_id: str) -> str:
    migrate()
    uid = user_id or "local"
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (uid,))
        conn.commit()
    return uid


# ... (Existing Utils) ...

# ---------------------------
# Recommendation Persistence
# ---------------------------
def save_recommendation(user_id: str, profile_id: Optional[int], rec_data: Dict[str, Any]) -> None:
    rec_json = json.dumps(rec_data, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO portfolio_recommendations(user_id, profile_id, rec_json)
            VALUES (?, ?, ?)
            """,
            (user_id, profile_id, rec_json),
        )
        conn.commit()


def load_latest_recommendation(user_id: str, profile_id: Optional[int]) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        # profile_id가 있으면 우선적으로 해당 프로필의 추천을 찾고, 없으면 그냥 유저의 최근 추천을 찾을 수도 있음
        # 여기서는 profile_id가 명시되면 strict하게 찾자.
        query = """
            SELECT rec_json, created_at
            FROM portfolio_recommendations
            WHERE user_id = ?
        """
        params = [user_id]
        
        if profile_id is not None:
            query += " AND profile_id = ?"
            params.append(profile_id)
            
        query += " ORDER BY rec_id DESC LIMIT 1"
        
        row = conn.execute(query, tuple(params)).fetchone()
        
    if not row:
        return None
        
    data = json.loads(row["rec_json"])
    data["created_at"] = row["created_at"]
    return data

def list_saved_recommendations(user_id: str, profile_id: Optional[int] = None) -> list[dict]:
    with get_conn() as conn:
        query = "SELECT rec_id, rec_json, created_at FROM portfolio_recommendations WHERE user_id = ?"
        params = [user_id]
        
        if profile_id is not None:
            query += " AND profile_id = ?"
            params.append(profile_id)
            
        query += " ORDER BY rec_id DESC"
        
        rows = conn.execute(query, tuple(params)).fetchall()
        
    results = []
    for r in rows:
        try:
            d = json.loads(r["rec_json"])
            # 요약 정보 추출 (티커 등)
            tickers = [t["symbol"] for t in d.get("tickers", [])]
            summary = ", ".join(tickers[:3])
            if len(tickers) > 3: summary += "..."
            
            results.append({
                "id": r["rec_id"],
                "created_at": r["created_at"],
                "summary": summary,
                "data": d
            })
        except:
            continue
            
    return results


# ---------------------------
# Utils: YYYYMM <-> YYYY-MM
# ---------------------------
def _to_yyyymm(as_of_or_yyyymm: str) -> str:
    """
    입력이 "YYYY-MM" 이면 "YYYYMM"로,
    이미 "YYYYMM"이면 그대로 반환.
    """
    s = (as_of_or_yyyymm or "").strip()
    if len(s) == 7 and s[4] == "-":
        return s.replace("-", "")
    return s


def _to_as_of(yyyymm: str) -> str:
    """
    "YYYYMM" -> "YYYY-MM"
    """
    s = (yyyymm or "").strip()
    if len(s) == 6 and s.isdigit():
        return f"{s[:4]}-{s[4:]}"
    return s


# ---------------------------
# YYYYMM helpers
# ---------------------------
def yyyymm_now() -> str:
    """현재 월을 yyyymm 문자열로 반환 (예: 202601)"""
    return datetime.now().strftime("%Y%m")


def yyyymm_prev(months_back: int) -> str:
    """
    현재 기준으로 months_back개월 전 yyyymm 반환
    예: months_back=1 → 지난달
    """
    try:
        from dateutil.relativedelta import relativedelta
        dt = datetime.now() - relativedelta(months=months_back)
    except Exception:
        dt = datetime.now() - timedelta(days=30 * months_back)

    return dt.strftime("%Y%m")


# ---------------------------
# Profile (여러 개) 관리
# ---------------------------
def create_profile(
    user_id: str,
    profile: Dict[str, Any],
    name: str = "새 설정",
    make_active: bool = True,
) -> int:
    profile_json = json.dumps(profile, ensure_ascii=False)
    with get_conn() as conn:
        cur = conn.cursor()

        if make_active:
            cur.execute("UPDATE profiles SET is_active=0 WHERE user_id=?", (user_id,))

        cur.execute(
            """
            INSERT INTO profiles(user_id, name, is_active, profile_json)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, name, 1 if make_active else 0, profile_json),
        )
        pid = int(cur.lastrowid)
        conn.commit()
    return pid


def list_profiles(user_id: str) -> List[Dict[str, Any]]:
    """
    ✅ 호환 확장:
    - 기존 키: profile_id, name, is_active, created_at, updated_at 유지
    - 앱 코드 호환 키: id, label 추가
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT profile_id, name, is_active, created_at, updated_at
            FROM profiles
            WHERE user_id=?
            ORDER BY profile_id ASC
            """,
            (user_id,),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["id"] = d["profile_id"]          # app compat
        d["label"] = d["name"]             # app compat
        d["is_active"] = bool(d.get("is_active", 0))
        out.append(d)
    return out


def set_active_profile(user_id: str, profile_id: int) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE profiles SET is_active=0 WHERE user_id=?", (user_id,))
        cur.execute(
            """
            UPDATE profiles
            SET is_active=1, updated_at=CURRENT_TIMESTAMP
            WHERE user_id=? AND profile_id=?
            """,
            (user_id, profile_id),
        )
        conn.commit()


def rename_profile(user_id: str, profile_id: int, new_name: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE profiles
            SET name=?, updated_at=CURRENT_TIMESTAMP
            WHERE user_id=? AND profile_id=?
            """,
            (new_name, user_id, profile_id),
        )
        conn.commit()


def load_active_profile(user_id: str) -> Tuple[Optional[int], Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT profile_id, profile_json
            FROM profiles
            WHERE user_id=? AND is_active=1
            ORDER BY profile_id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

    if not row:
        return None, {}
    return int(row["profile_id"]), json.loads(row["profile_json"])


def update_active_profile(user_id: str, profile: Dict[str, Any]) -> None:
    """
    active 프로필이 있으면 덮어쓰기(RESET 모드),
    없으면 새로 생성.
    """
    pid, _ = load_active_profile(user_id)
    if pid is None:
        create_profile(user_id, profile, name="기본 설정", make_active=True)
        return

    profile_json = json.dumps(profile, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE profiles
            SET profile_json=?, updated_at=CURRENT_TIMESTAMP
            WHERE user_id=? AND profile_id=?
            """,
            (profile_json, user_id, pid),
        )
        conn.commit()


def create_new_profile_and_activate(user_id: str, profile: Dict[str, Any], name: str = "새 설정") -> int:
    """
    ADD 모드: 새 프로필 만들고 active로 전환
    """
    return create_profile(user_id, profile, name=name, make_active=True)


# ---------------------------
# ✅ App-code compat aliases
# ---------------------------
def activate_profile_by_id(user_id: str, profile_id: int) -> None:
    return set_active_profile(user_id, profile_id)


def rename_profile_by_id(user_id: str, profile_id: int, new_label: str) -> None:
    return rename_profile(user_id, profile_id, new_label)


# ---------------------------
# Monthly plan history
# ---------------------------
def _upsert_monthly_plan_raw(user_id: str, profile_id: Optional[int], yyyymm: str, plan: Dict[str, Any]) -> None:
    plan_json = json.dumps(plan, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO monthly_plans(user_id, profile_id, yyyymm, plan_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, yyyymm, profile_id)
            DO UPDATE SET plan_json=excluded.plan_json, created_at=CURRENT_TIMESTAMP
            """,
            (user_id, profile_id, yyyymm, plan_json),
        )
        conn.commit()


def upsert_monthly_plan(user_id: str, profile_id: int | None, yyyymm: str, plan: Dict[str, Any]) -> None:
    """
    monthly_plans에 (user_id, profile_id, yyyymm) 단위로 plan_json을 upsert한다.
    plan dict를 절대 가공하지 않고 그대로 JSON으로 저장한다.
    """
    conn = get_conn()  # ✅ 너 db.py에 맞게
    cur = conn.cursor()

    plan_json = json.dumps(plan or {}, ensure_ascii=False)

    cur.execute(
        """
        INSERT INTO monthly_plans (user_id, profile_id, yyyymm, plan_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, yyyymm, profile_id)
        DO UPDATE SET
            plan_json = excluded.plan_json,
            created_at = CURRENT_TIMESTAMP
        """,
        (user_id, profile_id, str(yyyymm), plan_json),
    )

    conn.commit()


def get_plan(user_id: str, profile_id: Optional[int], yyyymm: str) -> Optional[Dict[str, Any]]:
    yyyymm = _to_yyyymm(yyyymm)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT plan_json FROM monthly_plans
            WHERE user_id=? AND profile_id IS ? AND yyyymm=?
            """,
            (user_id, profile_id, yyyymm),
        ).fetchone()

    if not row:
        return None
    return json.loads(row["plan_json"])


def list_recent_plans(user_id: str, profile_id: Optional[int], limit: int = 3) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT yyyymm, plan_json, created_at
            FROM monthly_plans
            WHERE user_id=? AND profile_id IS ?
            ORDER BY yyyymm DESC
            LIMIT ?
            """,
            (user_id, profile_id, limit),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "yyyymm": r["yyyymm"],
                "plan": json.loads(r["plan_json"]),
                "created_at": r["created_at"],
            }
        )
    return out


def fetch_monthly_plans(user_id: str, months: int = 3) -> list[dict[str, Any]]:
    """
    monthly_plans에서 최근 months건을 가져오고,
    plan_json(JSON 문자열)을 파싱해 plan dict를 반환한다.
    """
    conn = get_conn()  # ✅ 여기만 네 db.py에 맞게
    cur = conn.cursor()

    cur.execute(
        """
        SELECT yyyymm, plan_json, created_at
        FROM monthly_plans
        WHERE user_id = ?
        ORDER BY yyyymm DESC
        LIMIT ?
        """,
        (user_id, months),
    )

    rows = cur.fetchall()
    out: list[dict[str, Any]] = []

    for yyyymm, plan_json, created_at in rows:
        try:
            plan = json.loads(plan_json) if plan_json else {}
        except Exception:
            plan = {}

        # meta 보강
        plan["yyyymm"] = str(yyyymm)
        plan["created_at"] = created_at

        # 표시용 as_of 보정
        if not plan.get("as_of"):
            s = str(yyyymm)
            plan["as_of"] = f"{s[:4]}-{s[4:6]}" if len(s) >= 6 else s

        plan.setdefault("reason_codes", [])
        out.append(plan)

    return out

# ---------------------------
# Backward compatible helpers
# ---------------------------
def load_profile(user_id: str) -> Dict[str, Any]:
    _, prof = load_active_profile(user_id)
    return prof


def save_profile(user_id: str, profile: Dict[str, Any]) -> None:
    update_active_profile(user_id, profile)


def load_policy(user_id: str) -> Dict[str, Any]:
    return {}


def save_policy(user_id: str, policy: Dict[str, Any]) -> None:
    return
