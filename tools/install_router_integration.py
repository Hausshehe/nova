"""Integrate Nova's existing multi-provider AI router into nova_agent.py."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "nova_agent.py"


def main():
    text = TARGET.read_text(encoding="utf-8")

    if "from ai_router import call_ai" not in text:
        marker = "from tools.registry import discover_tools\n"
        if marker not in text:
            raise SystemExit("Could not find the import section in nova_agent.py")
        text = text.replace(
            marker,
            marker + "from ai_router import call_ai\n",
            1,
        )

    router_function = '''def _call_groq(messages):
    """Compatibility wrapper: route planner calls through the multi-provider AI router."""
    return call_ai(messages, build_agent_tool_definitions())
'''

    pattern = re.compile(
        r"def _call_groq\(messages\):\n.*?(?=\ndef _unwrap_tool_result\()",
        re.DOTALL,
    )
    updated, count = pattern.subn(router_function + "\n", text, count=1)
    if count != 1:
        raise SystemExit("Could not find the existing _call_groq function")

    TARGET.write_text(updated, encoding="utf-8")
    print("✅ Nova planner is now permanently routed through ai_router.")
    print("   Groq remains one provider, not the planner itself.")


if __name__ == "__main__":
    main()
