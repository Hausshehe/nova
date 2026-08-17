"""One-time/idempotent repair for Gemini tool-result history compatibility."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "ai_router.py"


def repair():
    text = ROUTER.read_text()

    start = text.find("def _sanitize_messages(messages, provider):")
    end = text.find("\ndef _cross_provider_messages(messages):", start)
    if start < 0 or end < 0:
        raise SystemExit("Could not locate _sanitize_messages() boundaries.")

    new = '''def _sanitize_messages(messages, provider):
    """Return provider-safe copies of the OpenAI-compatible conversation."""
    sanitized = []
    tool_names = {}

    for original in messages:
        if not isinstance(original, dict):
            continue

        for call in original.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            function = call.get("function") or {}
            call_id = call.get("id")
            name = function.get("name")
            if call_id and name:
                tool_names[call_id] = name

        message = {
            key: copy.deepcopy(value)
            for key, value in original.items()
            if key in {"role", "content", "tool_calls", "tool_call_id", "name"}
        }

        if provider == "gemini" and message.get("role") == "tool":
            call_id = message.get("tool_call_id")
            if not message.get("name") and call_id in tool_names:
                message["name"] = tool_names[call_id]

        if provider == "gemini":
            for key in ("extra_content", "reasoning_content", "reasoning_details"):
                if key in original:
                    message[key] = copy.deepcopy(original[key])

        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            clean_calls = []
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                clean_call = copy.deepcopy(call)
                function = clean_call.get("function")
                if isinstance(function, dict):
                    clean_call["function"] = {
                        key: copy.deepcopy(value)
                        for key, value in function.items()
                        if key in {"name", "arguments"}
                    }
                clean_calls.append(clean_call)
            if provider == "gemini" and len(clean_calls) > 1:
                clean_calls = clean_calls[:1]
            message["tool_calls"] = clean_calls

        sanitized.append(message)

    return sanitized
'''

    ROUTER.write_text(text[:start] + new + text[end:])
    print("Repaired Gemini tool-result history handling in ai_router.py")
    print("Run: python -m py_compile ai_router.py")


if __name__ == "__main__":
    repair()
