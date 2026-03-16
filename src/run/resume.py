_STATUS_ICON = {
    "COMPLETED": "✓", "TIMED_OUT": "✗", "FAILED": "✗",
    "IN_PROGRESS": "~", "PENDING": "○", "SKIPPED": "-",
}


def display_run_summary(state: dict) -> None:
    print(f'\nRun summary for: "{state["topic"]}" ({state["run_id"]})')
    for sub in state.get("subtopics", []):
        icon = _STATUS_ICON.get(sub["status"], "?")
        error = f' [{sub.get("error", "")}]' if sub.get("error") else ""
        print(f"  {icon} Subtopic {sub['id']}: {sub['topic']:30s} — {sub['status']}{error}")
    for stage in ["synthesis", "pdf", "email"]:
        st = state.get(stage, {})
        icon = _STATUS_ICON.get(st.get("status", "PENDING"), "?")
        print(f"  {icon} {stage.capitalize():35s} — {st.get('status', 'PENDING')}")


def choose_resume_option(state: dict) -> dict:
    failed = [s for s in state.get("subtopics", []) if s["status"] in ("TIMED_OUT", "FAILED")]
    print("\nResume options:")
    if failed:
        print(f"  [1] Retry {len(failed)} failed subtopic(s), then continue")
        print(f"  [2] Skip failed subtopic(s), continue with completed results")
    else:
        print("  [1] Continue from last completed stage")
        print("  [2] Continue from last completed stage (same as 1)")
    print("  [3] Restart entire run from scratch")
    print("  [4] Abort and discard\n")

    while True:
        choice = input("Choice: ").strip()
        if choice == "1":
            return {"action": "retry_failed", "failed_subtopics": failed}
        elif choice == "2":
            return {"action": "skip_failed", "failed_subtopics": failed}
        elif choice == "3":
            return {"action": "restart"}
        elif choice == "4":
            return {"action": "abort"}
        else:
            print("Please enter 1, 2, 3, or 4.")
