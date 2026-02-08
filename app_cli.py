from __future__ import annotations
from graph import build_app


def main():
    app = build_app()
    print("RulePilot CLI 시작! (종료: exit)")

    # ✅ state는 한 번 만들고 계속 유지
    state = {"user_id": "local"}

    # ✅ 시작하자마자 봇이 먼저 '첫 질문'을 하도록 트리거
    state["user_text"] = ""  # 빈 입력
    out = app.invoke(state)

    # ✅ out로 state를 통째로 갈아끼우지 말고 merge(안전)
    if isinstance(out, dict):
        state.update(out)

    # ✅ 디버그 출력(초기)
    print(
        "\n[DEBUG:init]",
        {
            "pending_confirm_reset": state.get("pending_confirm_reset"),
            "editing_settings": state.get("editing_settings"),
            "edit_mode": state.get("edit_mode"),
            "pending_intake_field": state.get("pending_intake_field"),
            "profile_complete": state.get("profile_complete"),
            "intent": state.get("intent"),
        },
    )

    if state.get("output_text"):
        print("\nBot>\n" + state["output_text"])

    while True:
        user = input("\nYou> ").strip()
        if user.lower() in ["exit", "quit"]:
            break

        state["user_text"] = user
        out = app.invoke(state)

        # ✅ merge
        if isinstance(out, dict):
            state.update(out)

        # ✅ 디버그 출력(매 턴)
        print(
            "\n[DEBUG:turn]",
            {
                "user_text": user,
                "pending_confirm_reset": state.get("pending_confirm_reset"),
                "editing_settings": state.get("editing_settings"),
                "edit_mode": state.get("edit_mode"),
                "pending_intake_field": state.get("pending_intake_field"),
                "profile_complete": state.get("profile_complete"),
                "intent": state.get("intent"),
            },
        )

        print("\nBot>\n" + state.get("output_text", "(no output)"))


if __name__ == "__main__":
    main()
