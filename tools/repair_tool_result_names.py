"""One-time repair: make Nova tool-result messages explicit for Gemini/OpenAI tools."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "nova_agent.py"

OLD = '''    return {
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": json.dumps(
            planner_result,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
'''

NEW = '''    return {
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "name": function_name,
        "content": json.dumps(
            planner_result,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
'''

text = TARGET.read_text()
if NEW in text:
    print("Tool-result name repair already applied to nova_agent.py")
elif OLD in text:
    TARGET.write_text(text.replace(OLD, NEW, 1))
    print("Applied explicit tool-result name repair to nova_agent.py")
else:
    raise SystemExit("Could not locate _tool_result_message() return block.")
