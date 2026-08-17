from pathlib import Path

path = Path("nova_agent.py")
text = path.read_text(encoding="utf-8")

start = text.find("def _simple_open_goal(goal):")
end = text.find("def _observe_directly():", start)
if start == -1 or end == -1:
    raise SystemExit("Could not locate the simple-open classifier boundaries in nova_agent.py")

new_function = '''def _simple_open_goal(goal):
    """Recognize only a standalone generic 'open/launch/start app' goal."""
    normalized = " ".join(str(goal or "").strip().lower().split())
    remainder = normalized
    for verb in ("open ", "launch ", "start "):
        if remainder.startswith(verb):
            remainder = remainder[len(verb):].strip()
            break

    action_words = {
        "and", "then", "after", "before", "find", "search", "look",
        "navigate", "go", "click", "tap", "open", "launch", "start",
        "change", "enable", "disable", "turn", "set", "type", "enter",
    }
    if set(remainder.split()) & action_words:
        return ""

    if normalized.startswith(("open ", "launch ", "start ")):
        app = remainder
        if app.endswith(" app"):
            app = app[:-4].rstrip()
        return app
    return ""


'''

path.write_text(text[:start] + new_function + text[end:], encoding="utf-8")
print("Updated _simple_open_goal safely.")
