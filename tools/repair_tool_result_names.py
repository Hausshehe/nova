"""One-time repair: make Nova tool-result messages explicit and improve fallback order."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "nova_agent.py"
ROUTER = ROOT / "ai_router.py"

OLD_TOOL = '''    return {
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": json.dumps(
            planner_result,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
'''

NEW_TOOL = '''    return {
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

OLD_ORDER = 'DEFAULT_ORDER = ["groq", "gemini", "cloudflare", "mistral", "openrouter"]'
NEW_ORDER = 'DEFAULT_ORDER = ["groq", "gemini", "mistral", "openrouter", "cloudflare"]'

agent = AGENT.read_text()
if NEW_TOOL in agent:
    print("Tool-result name repair already applied to nova_agent.py")
elif OLD_TOOL in agent:
    AGENT.write_text(agent.replace(OLD_TOOL, NEW_TOOL, 1))
    print("Applied explicit tool-result name repair to nova_agent.py")
else:
    raise SystemExit("Could not locate _tool_result_message() return block in nova_agent.py")

router = ROUTER.read_text()
if NEW_ORDER in router:
    print("Fallback provider order already hardened")
elif OLD_ORDER in router:
    ROUTER.write_text(router.replace(OLD_ORDER, NEW_ORDER, 1))
    print("Fallback order changed to Groq -> Gemini -> Mistral -> OpenRouter -> Cloudflare")
else:
    raise SystemExit("Could not locate DEFAULT_ORDER in ai_router.py")
