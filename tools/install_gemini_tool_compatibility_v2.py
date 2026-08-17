"""Install robust Gemini/OpenAI-compatibility handling for Nova.

Gemini 3 requires thought signatures from function calls to be returned exactly
on the next turn. The router must preserve Gemini's extra_content.google field
when sending history back to Gemini, while stripping it for other providers.
Tool results also need a function name for Gemini.
"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "ai_router.py"
AGENT = ROOT / "nova_agent.py"


def update_router():
    text = ROUTER.read_text()

    # Make sanitizer provider-aware if the earlier compatibility installer exists.
    text = text.replace(
        "def _sanitize_messages(messages):",
        "def _sanitize_messages(messages, provider=None):",
        1,
    )

    # Preserve Gemini's encrypted thought signature on tool calls. It is required
    # for Gemini 3 multi-turn function calling. Other providers should not receive
    # Google's provider-specific extra_content.
    old = '''                    clean_calls.append({
                        "id": call.get("id") or f"call_{len(clean_calls)}",
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": function.get("arguments") or "{}",
                        },
                    })'''
    new = '''                    clean_call = {
                        "id": call.get("id") or f"call_{len(clean_calls)}",
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": function.get("arguments") or "{}",
                        },
                    }
                    if provider == "gemini" and call.get("extra_content"):
                        clean_call["extra_content"] = call["extra_content"]
                    clean_calls.append(clean_call)'''
    if old in text:
        text = text.replace(old, new, 1)
    elif "clean_call = {" not in text:
        raise SystemExit("Could not locate tool-call sanitizer block")

    # Ensure the provider reaches the sanitizer.
    text = text.replace(
        "messages = _sanitize_messages(messages)",
        "messages = _sanitize_messages(messages, provider)",
        1,
    )

    # If the previous installer was not applied, install a complete sanitizer.
    if "def _sanitize_messages(messages, provider=None):" not in text:
        raise SystemExit("Router sanitizer was not installed")

    ROUTER.write_text(text)


def update_agent():
    text = AGENT.read_text()

    # Add the tool function name to every tool-result message. Gemini requires
    # function_response.name; other OpenAI-compatible providers accept it too.
    if '"name": function_name' not in text:
        pattern = r'(def _tool_result_message\(tool_call, result, function_name\):\s*return \{\s*"role": "tool",\s*"tool_call_id": tool_call\["id"\],\s*)'
        replacement = r'\1"name": function_name,\n        '
        text, count = re.subn(pattern, replacement, text, count=1)
        if count == 0:
            raise SystemExit("Could not locate _tool_result_message")

    AGENT.write_text(text)


if __name__ == "__main__":
    update_router()
    update_agent()
    print("✅ Installed Gemini thought-signature compatibility v2.")
    print("   Gemini tool-call signatures are preserved for Gemini turns.")
    print("   Google-specific metadata is stripped before other providers.")
    print("   Tool results include their function name.")
