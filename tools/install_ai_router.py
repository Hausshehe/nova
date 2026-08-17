"""Safely wire ai_router.py into nova_agent.py on the local checkout."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "nova_agent.py"

IMPORT_LINE = "from ai_router import call_ai"
START = "def _call_groq(messages):"
END = "def _unwrap_tool_result(result):"

NEW_FUNCTION = '''def _call_groq(messages):
    """Compatibility wrapper: use Nova's multi-provider AI router."""
    return call_ai(messages, build_agent_tool_definitions())


'''


def main():
    text = TARGET.read_text(encoding="utf-8")

    if IMPORT_LINE not in text:
        marker = "from tools.registry import discover_tools\n"
        if marker not in text:
            raise SystemExit("Could not find the import section in nova_agent.py")
        text = text.replace(marker, marker + IMPORT_LINE + "\n", 1)

    start = text.find(START)
    end = text.find(END, start if start >= 0 else 0)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("Could not locate the existing Groq planner function")

    text = text[:start] + NEW_FUNCTION + text[end:]
    TARGET.write_text(text, encoding="utf-8")
    print("✅ Nova now uses the multi-provider AI router.")
    print("Providers: Gemini, Cerebras, Groq, Mistral, OpenRouter")
    print("Only providers with configured API keys will be used.")


if __name__ == "__main__":
    main()
