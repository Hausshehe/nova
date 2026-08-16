from pathlib import Path

path = Path("nova_agent.py")
text = path.read_text(encoding="utf-8")
old = '        "parallel_tool_calls": False,\n        "service_tier": "auto",\n'
new = '        "parallel_tool_calls": False,\n'

if old not in text:
    raise SystemExit("Could not find the unsupported service_tier=auto setting in nova_agent.py")

path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("✅ Removed unsupported Groq service_tier=auto; Groq will use the standard on-demand tier.")
