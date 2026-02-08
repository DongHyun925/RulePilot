import re
from data.db import list_profiles, set_active_profile, rename_profile, load_active_profile

def node_profile_list(state):
    user_id = state["user_id"]
    items = list_profiles(user_id)
    if not items:
        state["output_text"] = "📭 아직 저장된 설정이 없어요. 먼저 설정을 만들어볼까요?"
        return state

    lines = ["📚 내 설정 목록"]
    for i, p in enumerate(items, start=1):
        mark = "✅" if p["is_active"] else "  "
        lines.append(f"{mark} {i}) (id={p['profile_id']}) {p['name']}")
    lines.append("\n원하면 이렇게 말해줘:\n- '설정 2번으로 바꿔'\n- '이 설정 이름을 은퇴모드로 바꿔줘'")
    state["output_text"] = "\n".join(lines)
    return state

def node_profile_switch(state):
    user_id = state["user_id"]
    t = state.get("user_text", "")
    m = re.search(r"설정\s*(\d+)\s*번", t)
    if not m:
        state["output_text"] = "❗ '설정 2번으로 바꿔' 처럼 번호로 말해줘."
        return state

    idx = int(m.group(1))
    items = list_profiles(user_id)
    if not (1 <= idx <= len(items)):
        state["output_text"] = f"❗ {idx}번 설정은 없어요. '내 설정 목록 보여줘'로 확인해줘."
        return state

    target = items[idx - 1]["profile_id"]
    set_active_profile(user_id, int(target))
    state["output_text"] = f"✅ 설정 {idx}번으로 전환했어요. 이제 이 설정 기준으로 답할게요."
    return state

def node_profile_rename(state):
    user_id = state["user_id"]
    t = state.get("user_text", "")

    # 예: "이 설정 이름을 은퇴모드로 바꿔줘"
    m = re.search(r"이\s*설정\s*이름을\s*['\"]?(.+?)['\"]?\s*(로|으로)\s*(바꿔|변경)", t)
    if not m:
        state["output_text"] = "❗ 예: '이 설정 이름을 은퇴모드로 바꿔줘'처럼 말해줘."
        return state

    new_name = m.group(1).strip()
    active_id, _ = load_active_profile(user_id)
    if not active_id:
        state["output_text"] = "❗ 활성 설정이 없어요. 먼저 설정을 만들어줘."
        return state

    rename_profile(user_id, int(active_id), new_name)
    state["output_text"] = f"✅ 설정 이름을 '{new_name}'로 바꿨어요."
    return state
