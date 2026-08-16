from pathlib import Path
import re

path = Path("nova_agent.py")
text = path.read_text(encoding="utf-8")

new_function = '''def _simple_open_goal(goal):
    """Recognize only a single-app open/launch/start goal.

    Multi-step requests must stay in Nova's adaptive planner instead of being
    mistaken for an app name.
    """
    normalized = re.sub(r"\\s+", " ", str(goal or "").strip().lower())

    # If the request contains another action, it is not a simple open goal.
    remainder = re.sub(r"^(?:open|launch|start)\\s+", "", normalized)
    if re.search(
        r"\\b(?:and|then|after|before|find|search|look|navigate|go|click|tap|"
        r"open|launch|start|change|enable|disable|turn|set|type|enter)\\b",
        remainder,
    ):
        return ""

    match = re.fullmatch(
        r"(?:open|launch|start)\\s+(.+?)(?:\\s+app)?",
        normalized,
    )
    return match.group(1).strip() if match else ""


'''

pattern = r"def _simple_open_goal\(goal\):.*?(?=def _observe_directly\(\):)"
updated, count = re.subn(pattern, new_function, text, count=1, flags=re.DOTALL)

if count != 1:
    raise SystemExit("Could not locate _simple_open_goal in nova_agent.py")

path.write_text(updated, encoding="utf-8")
print("✅ Updated _simple_open_goal safely.")
