from pathlib import Path

PATH = Path("nova_agent.py")
text = PATH.read_text(encoding="utf-8")
original = text

# The current Groq organization does not support the optional auto service tier.
text = text.replace('        "service_tier": "auto",\n', '')

# Keep less stale planner history. The newest observation is ground truth, so
# retaining fewer old action/observation pairs reduces token pressure without
# turning the agent into a hard-coded procedure.
text = text.replace("MAX_HISTORY_PAIRS = 3", "MAX_HISTORY_PAIRS = 2")

old_rules = '''9. Use back and scrolling when needed.\n10. For destructive, privacy-sensitive, financial, account, or otherwise\n    consequential final actions, ask the user for confirmation immediately\n'''
new_rules = '''9. Use back and scrolling when needed.\n10. When the goal names a destination screen or setting, reaching the parent\n    app is not enough: continue navigating until that destination is visible\n    or the agent has reliable evidence that it cannot be reached. If a named\n    destination is not visible in a scrollable list, prefer scrolling and then\n    observing again before deciding to go back. Do not use Back merely because\n    the target is below the current viewport. When the destination control\n    becomes visible, activate it using its current semantic node and observe\n    the resulting screen.\n11. For destructive, privacy-sensitive, financial, account, or otherwise\n    consequential final actions, ask the user for confirmation immediately\n'''
if old_rules not in text:
    raise SystemExit("Expected navigation rule block was not found; no changes made.")
text = text.replace(old_rules, new_rules, 1)

# The formatted summary duplicates visible_text and interactive labels already
# present in the structured observation. Removing it saves input tokens while
# preserving the decision-relevant state.
old_observe_return = '''        return {\n            "success": True,\n            "verified": bool(result.get("verified")),\n            "summary": result.get("summary", ""),\n            "state": compact_state,\n            "foreground_package": foreground_package,\n        }\n'''
new_observe_return = '''        return {\n            "success": True,\n            "verified": bool(result.get("verified")),\n            "state": compact_state,\n            "foreground_package": foreground_package,\n        }\n'''
if old_observe_return not in text:
    raise SystemExit("Expected observation block was not found; no changes made.")
text = text.replace(old_observe_return, new_observe_return, 1)

if text == original:
    raise SystemExit("No changes were necessary.")

PATH.write_text(text, encoding="utf-8")
print("Updated Nova's adaptive Android planner: less stale history, less duplicate observation text, stronger generic navigation behavior, and no unsupported Groq service_tier.")
