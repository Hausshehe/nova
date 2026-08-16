from pathlib import Path

path = Path("nova_agent.py")
text = path.read_text()

replacements = {
    'MAX_HISTORY_PAIRS = 3': 'MAX_HISTORY_PAIRS = 2',
    '"max_tokens": 800,': '"max_tokens": 500,',
    '"description": inspect.getdoc(function) or f"Use {name}.",': '"description": f"Use the {name} Android primitive.",',
}

for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f"Expected text not found: {old}")
    text = text.replace(old, new, 1)

old_prompt = '''9. Use back and scrolling when needed.\n10. For destructive, privacy-sensitive, financial, account, or otherwise\n'''
new_prompt = '''9. Use back and scrolling when needed. If the requested control is not in\n   visible_text but the current UI has a scrollable area, prefer scrolling in\n   the relevant direction before pressing Back. Press Back only when the current\n   screen is clearly the wrong screen or Back is the appropriate navigation step.\n10. For destructive, privacy-sensitive, financial, account, or otherwise\n'''
if old_prompt not in text:
    raise SystemExit("Expected scrolling prompt text not found")
text = text.replace(old_prompt, new_prompt, 1)

path.write_text(text)
print("✅ Optimized Nova planner token usage and strengthened scrolling behavior.")
