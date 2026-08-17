from pathlib import Path
import re

path = Path("nova_agent.py")
text = path.read_text(encoding="utf-8")

new_function = '''def _simple_open_goal(goal):
    """Recognize only a single-app open/launch/start goal.

    Compound requests such as "Open Settings and open Display & Brightness"
    must go through the adaptive planner instead of being treated as one app
    name.
    """
    normalized = re.sub(r"\s+", " ", str(goal or "").strip().lower())
    remainder = re.sub(r"^(?:open|launch|start)\s+", "", normalized)

    # If the remainder contains another action or a conjunction, this is a
    # multi-step goal and must be handled by Groq's planner.
    if re.search(
        r"\b(?:and|then|after|before|find|search|look|navigate|go|click|tap|"
        r"open|launch|start|change|enable|disable|turn|set|type|enter)\b",
        remainder,
    ):
        return ""

    match = re.fullmatch(
        r"(?:open|launch|start)\s+(.+?)(?:\s+app)?",
        normalized,
    )
    return match.group(1).strip() if match else ""


'''

pattern = re.compile(
    r"def _simple_open_goal\(goal\):.*?(?=def _observe_directly\(\):)",
    re.DOTALL,
)
match = pattern.search(text)
if not match:
    raise SystemExit("Could not locate _simple_open_goal in nova_agent.py")

updated = text[:match.start()] + new_function + text[match.end():]
path.write_text(updated, encoding="utf-8")
print("Updated _simple_open_goal safely.")
